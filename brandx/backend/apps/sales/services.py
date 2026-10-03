"""
Sales services - one place that computes the numbers.

Owner sees the full picture (revenue, cost, gross profit, expenses, net profit).
Manager/cashier get an operational subset; profit is never computed for them.
"""
from decimal import Decimal

from django.db.models import Count, Q, Sum

from apps.finance.models import FinanceEntry

from .models import Sale, SaleItem, SaleReturn, SaleReturnItem

COUNTED_STATUSES = (Sale.STATUS_COMPLETED, Sale.STATUS_PARTIALLY_REFUNDED, Sale.STATUS_REFUNDED)


def _money(value):
    return Decimal(value or 0)


def sales_in_range(start=None, end=None, *, store):
    qs = Sale.objects.filter(store=store, status__in=COUNTED_STATUSES)
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(store.timezone)
    if start:
        qs = qs.filter(created_at__gte=datetime.combine(start, time.min, tzinfo=tz))
    if end:
        qs = qs.filter(created_at__lt=datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz))
    return qs


def returns_in_range(start=None, end=None, *, store):
    qs = SaleReturn.objects.filter(sale__store=store).exclude(sale__status='cancelled')
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo(store.timezone)
    if start:
        qs = qs.filter(created_at__gte=datetime.combine(start, time.min, tzinfo=tz))
    if end:
        qs = qs.filter(created_at__lt=datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz))
    return qs


def operational_stats(start=None, end=None, *, store):
    """Revenue / payment split / counts - safe for manager and owner."""
    qs = sales_in_range(start, end, store=store)
    agg = qs.aggregate(
        sales_count=Count('id'),
        revenue=Sum('total_amount'),
        cash=Sum('cash_amount'),
        card=Sum('card_amount'),
        discount=Sum('discount_amount'),
    )
    items = SaleItem.objects.filter(sale__in=qs).aggregate(
        units=Sum('quantity'), lines=Count('id')
    )
    refunds = returns_in_range(start, end, store=store)
    refund_totals = refunds.aggregate(total=Sum('total_amount'), cash=Sum('cash_amount'), card=Sum('card_amount'))
    returns_total = _money(refund_totals['total'])
    returned_units = SaleReturnItem.objects.filter(sale_return__in=refunds).aggregate(n=Sum('quantity'))['n'] or 0

    revenue = _money(agg['revenue'])
    count = agg['sales_count'] or 0

    return {
        'sales_count': count,
        'units_sold': (items['units'] or 0) - returned_units,
        'revenue': revenue,
        'returns_total': returns_total,
        'net_revenue': revenue - returns_total,
        'cash_total': _money(agg['cash']) - _money(refund_totals['cash']),
        'card_total': _money(agg['card']) - _money(refund_totals['card']),
        'discount_total': _money(agg['discount']),
        'average_check': ((revenue - returns_total) / count).quantize(Decimal('0.01')) if count else Decimal('0.00'),
    }


def _cost_of_goods(start=None, end=None, *, store):
    """Purchase cost of everything sold in the period, minus returned goods."""
    qs = sales_in_range(start, end, store=store)
    cogs = Decimal('0')
    for row in SaleItem.objects.filter(sale__in=qs).values('quantity', 'unit_cost'):
        cogs += _money(row['unit_cost']) * row['quantity']

    returned_cost = Decimal('0')
    for row in SaleReturnItem.objects.filter(
        sale_return__in=returns_in_range(start, end, store=store)
    ).values('quantity', 'sale_item__unit_cost'):
        returned_cost += _money(row['sale_item__unit_cost']) * row['quantity']

    return cogs - returned_cost


def financial_stats(start=None, end=None, *, store):
    """
    Full P&L for the period - OWNER ONLY.

    revenue       : money taken at the till (net of returns)
    cost_of_goods : purchase cost of the units sold
    gross_profit  : revenue - cost of goods
    expenses      : rent, salary, ... from FinanceEntry
    other_income  : non-sale income
    net_profit    : gross_profit + other_income - expenses
    """
    ops = operational_stats(start, end, store=store)

    entries = FinanceEntry.objects.filter(store=store)
    if start:
        entries = entries.filter(entry_date__gte=start)
    if end:
        entries = entries.filter(entry_date__lte=end)
    finance = entries.aggregate(
        income=Sum('amount', filter=Q(entry_type=FinanceEntry.TYPE_INCOME)),
        expense=Sum('amount', filter=Q(entry_type=FinanceEntry.TYPE_EXPENSE)),
    )

    cost_of_goods = _cost_of_goods(start, end, store=store)
    revenue = ops['net_revenue']
    gross_profit = revenue - cost_of_goods
    other_income = _money(finance['income'])
    expenses = _money(finance['expense'])

    return {
        **ops,
        'cost_of_goods': cost_of_goods,
        'gross_profit': gross_profit,
        'other_income': other_income,
        'expenses': expenses,
        'net_profit': gross_profit - expenses,
    }


def profit_block(start=None, end=None, *, store):
    """The owner-only slice of ``financial_stats``."""
    stats = financial_stats(start, end, store=store)
    return {
        'cost_of_goods': stats['cost_of_goods'],
        'gross_profit': stats['gross_profit'],
        'other_income': stats['other_income'],
        'expenses': stats['expenses'],
        'net_profit': stats['net_profit'],
    }


class PaymentError(Exception):
    """Raised when a payment cannot be completed (e.g. not enough cash)."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def resolve_payment(payment_method, total, received_amount=0, card_amount=0):
    """
    Validate a payment and work out the cash/card split and the change.

    Returns ``(cash_amount, card_amount, received, change)``.
    Raises ``PaymentError`` when the amounts do not add up.
    """
    total = _money(total)
    received = _money(received_amount)
    card = _money(card_amount)

    if total < 0:
        raise PaymentError('invalid_total', 'Total amount cannot be negative.')

    if payment_method == Sale.PAYMENT_CASH:
        if received and received < total:
            raise PaymentError('insufficient_cash',
                               'Received amount is less than the total. Cash payment cannot be completed.')
        received = received or total
        return total, Decimal('0'), received, received - total

    if payment_method == Sale.PAYMENT_CARD:
        if card and card != total:
            raise PaymentError('invalid_card', 'Card amount must equal the total amount.')
        return Decimal('0'), total, total, Decimal('0')

    if payment_method == Sale.PAYMENT_MIXED:
        paid = received + card
        if paid < total:
            raise PaymentError('insufficient_total',
                               'Cash + card is less than the total amount.')
        change = paid - total
        cash_part = received - change
        if cash_part < 0:
            raise PaymentError('invalid_mixed',
                               'Card amount is greater than the total amount.')
        return cash_part, card, received, change

    raise PaymentError('invalid_method', 'Unsupported payment method.')


def top_products(start=None, end=None, limit=10, *, store):
    rows = {}
    def add(item, qty, revenue):
        key = item.product_variant.product_id
        row = rows.setdefault(key, {'product_id': key, 'product_name': item.product_name, 'units': 0, 'revenue': Decimal('0')})
        row['units'] += qty
        row['revenue'] += revenue
    for item in SaleItem.objects.filter(sale__in=sales_in_range(start, end, store=store)).select_related('sale', 'product_variant'):
        line_sum = item.sale.subtotal
        paid = (item.total_price * item.sale.total_amount / line_sum).quantize(Decimal('0.01')) if line_sum else Decimal('0')
        add(item, item.quantity, paid)
    for returned in SaleReturnItem.objects.filter(sale_return__in=returns_in_range(start, end, store=store)).select_related('sale_item__product_variant'):
        add(returned.sale_item, -returned.quantity, -returned.total_price)
    return sorted(rows.values(), key=lambda r: (-r['units'], -r['revenue']))[:limit]


def sales_by_day(start, end, *, store):
    """Daily revenue series used by the dashboard chart."""
    from datetime import datetime, time, timedelta
    from zoneinfo import ZoneInfo
    from django.db.models.functions import TruncDay, TruncHour, TruncWeek
    tz = ZoneInfo(store.timezone)
    duration = (end - start).days + 1
    trunc = TruncHour if duration == 1 else TruncWeek if duration > 90 else TruncDay
    step = timedelta(hours=1) if duration == 1 else timedelta(days=7 if duration > 90 else 1)
    points = {}
    first = datetime.combine(start, time.min, tzinfo=tz)
    if duration > 90:
        first -= timedelta(days=first.weekday())
    cursor = first
    until = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
    while cursor < until:
        key = cursor.isoformat()
        points[key] = {'date': key, 'revenue': Decimal('0'), 'count': 0}
        cursor += step
    for queryset, field, amount, sign in [
        (sales_in_range(start, end, store=store), 'created_at', 'total_amount', 1),
        (returns_in_range(start, end, store=store), 'created_at', 'total_amount', -1),
    ]:
        for row in queryset.annotate(bucket=trunc(field, tzinfo=tz)).values('bucket').annotate(total=Sum(amount), n=Count('id')):
            key = row['bucket'].isoformat()
            point = points.setdefault(key, {'date': key, 'revenue': Decimal('0'), 'count': 0})
            point['revenue'] += sign * _money(row['total'])
            if sign > 0:
                point['count'] += row['n']
    return [points[k] for k in sorted(points)]
