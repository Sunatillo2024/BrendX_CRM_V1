"""Reports - Excel (.xlsx) and CSV exports.

Plain function-based Django views (no DRF): the server-rendered Reports and
Finance pages call them directly via ``apps.web.views.money.report_export``.
"""
from django.http import Http404, HttpResponse
from django.utils import timezone

from apps.common.filters import resolve_period
from apps.common.tenancy import active_store
from apps.finance.models import FinanceEntry
from apps.inventory.models import StockReceiptItem
from apps.products.models import ProductVariant
from apps.sales import services as sales_services
from apps.sales.models import SaleItem

from .exporters import CSV_MIME, XLSX_MIME, rows_to_csv, rows_to_xlsx

HEADERS = {
    'uz': {
        'sale_no': 'Chek №', 'date': 'Sana', 'cashier': 'Kassir', 'customer': 'Mijoz',
        'product': 'Mahsulot', 'color': 'Rang', 'size': "O'lcham", 'qty': 'Soni',
        'price': 'Narx', 'discount': 'Chegirma', 'total': 'Summa',
        'payment': "To'lov turi", 'status': 'Holati',
        'category': 'Kategoriya', 'barcode': 'Shtrix-kod', 'stock': 'Ostatka',
        'cost': 'Zakup narxi', 'value': 'Qiymati',
        'vendor': 'Yetkazib beruvchi', 'comment': 'Izoh', 'created_by': 'Kim kiritdi',
        'receipt_no': "Kirim №", 'income': 'Kirim', 'expense': 'Chiqim',
        'indicator': "Ko'rsatkich", 'amount': 'Miqdor',
        'item': 'Ko\u2019rsatkich',
    },
    'ru': {
        'sale_no': 'Чек №', 'date': 'Дата', 'cashier': 'Кассир', 'customer': 'Клиент',
        'product': 'Товар', 'color': 'Цвет', 'size': 'Размер', 'qty': 'Кол-во',
        'price': 'Цена', 'discount': 'Скидка', 'total': 'Сумма',
        'payment': 'Способ оплаты', 'status': 'Статус',
        'category': 'Категория', 'barcode': 'Штрих-код', 'stock': 'Остаток',
        'cost': 'Закупочная цена', 'value': 'Стоимость',
        'vendor': 'Поставщик', 'comment': 'Комментарий', 'created_by': 'Кто внёс',
        'receipt_no': 'Поступление №', 'income': 'Доход', 'expense': 'Расход',
        'indicator': 'Показатель', 'amount': 'Сумма',
        'item': 'Показатель',
    },
}

PAYMENT_LABELS = {
    'uz': {'cash': 'Naqd', 'card': 'Karta', 'mixed': 'Aralash'},
    'ru': {'cash': 'Наличные', 'card': 'Карта', 'mixed': 'Смешанная'},
}
STATUS_LABELS = {
    'uz': {'completed': 'Yakunlangan', 'partially_refunded': 'Qisman qaytarilgan',
           'refunded': 'Qaytarilgan', 'cancelled': 'Bekor qilingan'},
    'ru': {'completed': 'Завершена', 'partially_refunded': 'Частичный возврат',
           'refunded': 'Возврат', 'cancelled': 'Отменена'},
}


def _lang(request):
    lang = (request.GET.get('lang') or 'uz').lower()
    return lang if lang in HEADERS else 'uz'


def _deal(request, rows, base_name, start, end):
    """Return the export as xlsx or csv with a readable file name."""
    lang = _lang(request)
    fmt = (request.GET.get('fmt') or 'xlsx').lower()
    stamp = _stamp(start, end)
    filename = f'{base_name}_{stamp}.{"csv" if fmt == "csv" else "xlsx"}'

    if fmt == 'csv':
        content = rows_to_csv(rows)
        content_type = CSV_MIME
    else:
        content = rows_to_xlsx(rows, title=base_name)
        content_type = XLSX_MIME

    response = HttpResponse(content, content_type=content_type)
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def _stamp(start, end):
    if start and end and start == end:
        return str(start)
    if start and end:
        return f'{start:%Y-%m-%d}_{end:%Y-%m-%d}'
    return str(timezone.localdate())


def sales_export(request):
    """Sales report - one row per sold line."""
    lang = _lang(request)
    h = HEADERS[lang]
    start, end = resolve_period(request.GET)

    rows = [[h['sale_no'], h['date'], h['cashier'], h['customer'], h['product'],
             h['color'], h['size'], h['qty'], h['price'], h['discount'], h['total'],
             h['payment'], h['status']]]

    items = SaleItem.objects.filter(
        sale__in=sales_services.sales_in_range(start, end, store=active_store(request.user))
    ).select_related('sale', 'sale__cashier', 'sale__customer').order_by('-sale__created_at')

    for item in items:
        sale = item.sale
        rows.append([
            sale.sale_number,
            timezone.localtime(sale.created_at).strftime('%d.%m.%Y %H:%M'),
            sale.cashier.display_name,
            sale.customer.name if sale.customer else '',
            item.product_name, item.color_name, item.size_name,
            item.quantity, item.unit_price, item.discount_amount, item.total_price,
            PAYMENT_LABELS[lang].get(sale.payment_method, sale.payment_method),
            STATUS_LABELS[lang].get(sale.status, sale.status),
        ])
    return _deal(request, rows, 'sales', start, end)


def stock_export(request):
    """Current stock levels (purchase price column is owner-only)."""
    lang = _lang(request)
    h = HEADERS[lang]
    owner = request.user.can_view_financials

    header = [h['product'], h['category'], h['barcode'], h['color'], h['size'],
              h['stock'], h['price']]
    if owner:
        header += [h['cost'], h['value']]
    rows = [header]

    variants = ProductVariant.objects.filter(store=active_store(request.user), is_active=True).select_related(
        'product', 'product__category', 'color', 'size'
    ).order_by('product__name')
    for v in variants:
        row = [v.product.name, v.product.category.name if v.product.category else '',
               v.barcode, v.color.name if v.color else '', v.size.name if v.size else '',
               v.stock_quantity, v.effective_price]
        if owner:
            row += [v.effective_cost, v.effective_cost * v.stock_quantity]
        rows.append(row)

    today = timezone.localdate()
    return _deal(request, rows, 'stock', today, today)


def receipts_export(request):
    """Goods receipts with purchase costs — owner only."""
    lang = _lang(request)
    h = HEADERS[lang]
    start, end = resolve_period(request.GET)

    rows = [[h['receipt_no'], h['date'], h['vendor'], h['product'], h['color'],
             h['size'], h['qty'], h['cost'], h['total']]]

    items = StockReceiptItem.objects.filter(receipt__store=active_store(request.user)).select_related(
        'receipt', 'receipt__vendor', 'product_variant__product',
        'product_variant__color', 'product_variant__size'
    )
    if start:
        items = items.filter(receipt__receipt_date__gte=start)
    if end:
        items = items.filter(receipt__receipt_date__lte=end)

    for item in items.order_by('-receipt__number'):
        v = item.product_variant
        rows.append([
            item.receipt.number, str(item.receipt.receipt_date),
            item.receipt.vendor.name if item.receipt.vendor else '',
            v.product.name, v.color.name if v.color else '', v.size.name if v.size else '',
            item.quantity, item.cost_price, item.total_cost,
        ])
    return _deal(request, rows, 'receipts', start, end)


def finance_export(request):
    """Income / expense entries."""
    lang = _lang(request)
    h = HEADERS[lang]
    start, end = resolve_period(request.GET)
    entry_type = request.GET.get('type')

    entries = FinanceEntry.objects.filter(store=active_store(request.user)).select_related('created_by')
    if entry_type in (FinanceEntry.TYPE_INCOME, FinanceEntry.TYPE_EXPENSE):
        entries = entries.filter(entry_type=entry_type)
    if start:
        entries = entries.filter(entry_date__gte=start)
    if end:
        entries = entries.filter(entry_date__lte=end)
    entries = entries.order_by('-entry_date')

    rows = [[h['date'], h['indicator'], h['category'], h['comment'], h['amount'],
             h['created_by']]]
    for entry in entries:
        rows.append([
            str(entry.entry_date),
            h['income'] if entry.entry_type == FinanceEntry.TYPE_INCOME else h['expense'],
            entry.category, entry.comment, entry.amount,
            entry.created_by.display_name if entry.created_by else '',
        ])

    name = entry_type if entry_type in ('income', 'expense') else 'finance'
    return _deal(request, rows, name, start, end)


def financial_summary_export(request):
    """Full P&L for the period - OWNER ONLY."""
    lang = _lang(request)
    h = HEADERS[lang]
    start, end = resolve_period(request.GET)
    stats = sales_services.financial_stats(start, end, store=active_store(request.user))

    labels = {
        'uz': ['Savdo soni', 'Sotilgan dona', 'Tushum', 'Qaytarishlar',
               'Sof tushum', 'Tannarx', 'Yalpi foyda', 'Boshqa kirim',
               'Xarajatlar', 'Sof foyda'],
        'ru': ['Количество продаж', 'Продано единиц', 'Выручка', 'Возвраты',
               'Чистая выручка', 'Себестоимость', 'Валовая прибыль', 'Прочий доход',
               'Расходы', 'Чистая прибыль'],
    }[lang]

    rows = [[h['indicator'], h['amount']]]
    values = [
        stats['sales_count'], stats['units_sold'], stats['revenue'],
        stats['returns_total'], stats['net_revenue'], stats['cost_of_goods'],
        stats['gross_profit'], stats['other_income'], stats['expenses'],
        stats['net_profit'],
    ]
    for label, value in zip(labels, values):
        rows.append([label, value])
    return _deal(request, rows, 'financial_summary', start, end)


#: kind -> (export function, roles allowed to download it)
EXPORTS = {
    'sales': (sales_export, ('owner', 'manager')),
    'stock': (stock_export, ('owner', 'manager')),
    'receipts': (receipts_export, ('owner',)),
    'finance': (finance_export, ('owner', 'manager')),
    'financial-summary': (financial_summary_export, ('owner',)),
    'financial_summary': (financial_summary_export, ('owner',)),
}


def run_export(request, kind):
    """Dispatch to the export function after a role check; 404 on unknown kinds."""
    try:
        export_fn, roles = EXPORTS[kind]
    except KeyError:
        raise Http404('Unknown report')
    if not request.user.is_authenticated or request.user.role not in roles:
        return None
    return export_fn(request)
