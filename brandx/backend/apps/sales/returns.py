from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction, models
from django.db.models import Sum
from apps.inventory.services import return_stock
from .models import Sale, SaleReturn, SaleReturnItem

CENT = Decimal('0.01')


@transaction.atomic
def process_return(sale, data, user):
    sale = Sale.objects.select_for_update().get(pk=sale.pk, store=user.store)
    if sale.status in ('cancelled', 'refunded'):
        raise ValidationError('Sale cannot be returned again.')
    items = {item.pk: item for item in sale.items.select_for_update().order_by('pk')}
    seen = set()
    for row in data['items']:
        item = items.get(row['sale_item'])
        if not item or item.pk in seen or row['quantity'] > item.quantity - item.returned_quantity:
            raise ValidationError('Invalid or duplicate return line/quantity.')
        seen.add(item.pk)
    document = SaleReturn.objects.create(sale=sale, created_by=user,
        reason=data.get('reason', 'other'), notes=data.get('notes', ''))
    amount = Decimal('0')
    # Allocate sale-wide discount/tax proportionally to original net line totals.
    line_sum = sum(item.total_price for item in items.values())
    paid_lines = {}
    remaining_paid = sale.total_amount
    ordered_items = list(items.values())
    for index, item in enumerate(ordered_items):
        paid = ((sale.total_amount * item.total_price / line_sum).quantize(CENT)
                if line_sum else Decimal('0'))
        if index == len(ordered_items) - 1:
            paid = remaining_paid
        paid_lines[item.pk] = paid
        remaining_paid -= paid
    for row in data['items']:
        item = items[row['sale_item']]
        paid_line = paid_lines[item.pk]
        before = (paid_line * item.returned_quantity / item.quantity).quantize(CENT)
        after = (paid_line * (item.returned_quantity + row['quantity']) / item.quantity).quantize(CENT)
        refund = after - before
        entry = SaleReturnItem(sale_return=document, sale_item=item, quantity=row['quantity'],
                              unit_price=(refund / row['quantity']).quantize(CENT), total_price=refund)
        # Preserve the exact allocated cents instead of recomputing rounded unit × qty.
        models.Model.save(entry)
        item.returned_quantity += row['quantity']
        item.save(update_fields=['returned_quantity'])
        return_stock(item.product_variant, row['quantity'], sale=sale, user=user,
                     notes=data.get('notes', ''))
        amount += refund
    previous = sale.returns.exclude(pk=document.pk).aggregate(total=Sum('total_amount'))['total'] or Decimal('0')
    amount = min(amount, max(Decimal('0'), sale.total_amount - previous))
    cash_before = (previous * sale.cash_amount / sale.total_amount).quantize(CENT) if sale.total_amount else Decimal('0')
    cash_after = ((previous + amount) * sale.cash_amount / sale.total_amount).quantize(CENT) if sale.total_amount else Decimal('0')
    document.total_amount = amount
    document.cash_amount = cash_after - cash_before
    document.card_amount = amount - document.cash_amount
    document.save(update_fields=['total_amount', 'cash_amount', 'card_amount'])
    sale.status = 'refunded' if all(i.returned_quantity == i.quantity for i in items.values()) else 'partially_refunded'
    sale.save(update_fields=['status', 'updated_at'])
    return document
