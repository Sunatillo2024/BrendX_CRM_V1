"""POS checkout, sales history, returns/cancel and receipt PDF."""
import io
import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.customers.models import Customer
from apps.inventory import services as inventory_services
from apps.inventory.models import StockMovement
from apps.products.models import Category, ProductVariant
from apps.sales import services as sales_services
from apps.sales.models import Receipt, Sale, SaleItem, SaleReturn
from apps.web.decorators import store_required
from apps.web.i18n import translator
from apps.web.views.helpers import page_title, paginate, query_without_page, resolve_lang


# ── POS ─────────────────────────────────────────────────────────────
@store_required
def pos_view(request):
    return render(request, 'web/pos.html', {
        'page_title': page_title(request, 'pos.title'),
        'categories': Category.objects.filter(store=request.store, is_active=True).order_by('name'),
    })


def _create_sale(request, store, data):
    """Atomic checkout - mirrors the API's rules, reuses the same services."""
    customer = None
    if data.get('customer_id'):
        customer = Customer.objects.filter(pk=data['customer_id'], store=store).first()

    with transaction.atomic():
        number = store.next_number('sale')
        lines = []
        subtotal = Decimal('0')
        for raw in data['items']:
            variant = ProductVariant.objects.select_for_update(of=('self',)).select_related(
                'product', 'color', 'size'
            ).filter(store=store, pk=raw['product_variant_id'], is_active=True,
                     product__is_active=True).first()
            if variant is None or variant.stock_quantity < int(raw['quantity']):
                raise inventory_services.InsufficientStock(
                    variant, variant.stock_quantity if variant else 0, int(raw['quantity']))
            percent = Decimal(str(raw.get('discount_percent') or 0))
            line_total = Decimal(str(raw['unit_price'])) * int(raw['quantity'])
            discount = line_total * percent / Decimal('100')
            subtotal += line_total - discount
            lines.append({'variant': variant, 'raw': raw, 'net': line_total - discount})

        discount_amount = Decimal(str(data.get('discount_amount') or 0))
        if discount_amount > subtotal:
            raise sales_services.PaymentError('invalid_discount', 'Discount exceeds subtotal.')
        taxable = subtotal - discount_amount
        tax_rate = Decimal(str(getattr(settings, 'TAX_RATE', 0)))
        tax_amount = (taxable * tax_rate).quantize(Decimal('0.01'))
        total = taxable + tax_amount

        cash_amount, card_amount, received, change = sales_services.resolve_payment(
            data['payment_method'], total,
            data.get('received_amount') or 0, data.get('card_amount') or 0)

        sale = Sale.objects.create(
            number=number, store=store, customer=customer, cashier=request.user,
            payment_method=data['payment_method'], subtotal=subtotal,
            discount_amount=discount_amount, tax_amount=tax_amount, total_amount=total,
            cash_amount=cash_amount, card_amount=card_amount,
            received_amount=received, change_amount=change, notes=data.get('notes', ''))

        for line in lines:
            variant, raw = line['variant'], line['raw']
            SaleItem.objects.create(
                sale=sale, product_variant=variant, product_name=variant.product.name,
                color_name=variant.color.name if variant.color else '',
                size_name=variant.size.name if variant.size else '',
                quantity=int(raw['quantity']), unit_price=raw['unit_price'],
                unit_cost=variant.effective_cost,
                discount_percent=raw.get('discount_percent') or 0)
            inventory_services.sell_stock(variant, int(raw['quantity']), sale, user=request.user)

        Receipt.objects.create(sale=sale, receipt_number=sale.sale_number)

    log_action(AuditLog.ACTION_SALE_CREATED, user=request.user, entity='sale', entity_id=sale.pk,
               details={'number': sale.sale_number, 'total': str(sale.total_amount)})
    return sale


@store_required
@require_POST
def pos_checkout(request):
    try:
        data = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'detail': 'invalid payload'}, status=400)
    if not data.get('items'):
        return JsonResponse({'detail': 'empty cart'}, status=400)
    try:
        sale = _create_sale(request, request.store, data)
    except sales_services.PaymentError as exc:
        return JsonResponse({'detail': exc.detail, 'code': exc.code}, status=400)
    except inventory_services.InsufficientStock as exc:
        return JsonResponse({'detail': str(exc), 'code': 'insufficient_stock'}, status=400)
    return JsonResponse({'id': sale.pk, 'sale_number': sale.sale_number,
                         'total': str(sale.total_amount), 'change': str(sale.change_amount)})


# ── Sales history ───────────────────────────────────────────────────
@store_required
def sales_list(request):
    store = request.store
    qs = Sale.objects.filter(store=store).select_related('cashier', 'customer').order_by('-created_at')
    if getattr(request.user, 'is_cashier', False):
        qs = qs.filter(cashier=request.user)

    period = request.GET.get('period') or ''
    if period:
        from apps.common.filters import resolve_period
        start, end = resolve_period(request.GET)
        if start:
            qs = qs.filter(created_at__date__gte=start)
        if end:
            qs = qs.filter(created_at__date__lte=end)

    payment = request.GET.get('payment_method') or ''
    if payment:
        qs = qs.filter(payment_method=payment)
    status = request.GET.get('status') or ''
    if status:
        qs = qs.filter(status=status)
    query = (request.GET.get('q') or '').strip()
    if query:
        qs = qs.filter(number__icontains=query.lstrip('0') or query)

    page = paginate(request, qs, 20)
    return render(request, 'web/sales/list.html', {
        'page_title': page_title(request, 'sales.title'),
        'page_obj': page,
        'period': period,
        'payment': payment,
        'status': status,
        'query': query,
        'query_string': query_without_page(request),
    })


@store_required
def sale_detail(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('cashier', 'customer').prefetch_related(
            'items__product_variant', 'returns__items'),
        pk=pk, store=request.store)
    if getattr(request.user, 'is_cashier', False) and sale.cashier_id != request.user.pk:
        messages.error(request, translator(resolve_lang(request))('common.error'))
        return redirect('web:sales-list')
    return render(request, 'web/sales/detail.html', {
        'page_title': page_title(request, 'sales.detail'),
        'sale': sale,
        'can_return': request.user.role in ('owner', 'manager'),
        'is_owner': request.user.role == 'owner',
    })


@store_required
@require_POST
def return_items(request, pk):
    sale = get_object_or_404(Sale, pk=pk, store=request.store)
    if request.user.role not in ('owner', 'manager'):
        return redirect('web:sale-detail', pk=pk)

    t = translator(resolve_lang(request))
    selections = []
    for item in sale.items.all():
        raw = request.POST.get(f'return_qty_{item.pk}')
        if raw and raw.isdigit() and int(raw) > 0:
            selections.append({'sale_item': item.pk, 'quantity': int(raw)})
    if not selections:
        messages.error(request, t('sales.noReturnItems'))
        return redirect('web:sale-detail', pk=pk)

    from django.core.exceptions import ValidationError

    from apps.sales.returns import process_return
    try:
        process_return(sale, {'items': selections, 'reason': request.POST.get('reason') or 'other',
                              'notes': request.POST.get('notes', '')}, request.user)
    except ValidationError:
        messages.error(request, t('common.error'))
        return redirect('web:sale-detail', pk=pk)
    log_action(AuditLog.ACTION_SALE_RETURNED, user=request.user, entity='sale', entity_id=sale.pk,
               details={'number': sale.sale_number})
    messages.success(request, t('sales.returnDone'))
    return redirect('web:sale-detail', pk=pk)


@store_required
@require_POST
def cancel_sale(request, pk):
    if request.user.role != 'owner':
        return redirect('web:sale-detail', pk=pk)
    sale = get_object_or_404(Sale, pk=pk, store=request.store)
    with transaction.atomic():
        sale = Sale.objects.select_for_update().get(pk=sale.pk, store=request.store)
        if sale.status == Sale.STATUS_CANCELLED:
            return redirect('web:sale-detail', pk=pk)
        for item in sale.items.select_for_update():
            pending = item.quantity - item.returned_quantity
            if pending > 0:
                inventory_services.return_stock(item.product_variant, pending, sale=sale,
                                                user=request.user, reason='correction',
                                                notes='Sale cancelled')
        sale.status = Sale.STATUS_CANCELLED
        sale.save(update_fields=['status', 'updated_at'])
    log_action(AuditLog.ACTION_SALE_RETURNED, user=request.user, entity='sale', entity_id=sale.pk,
               details={'number': sale.sale_number, 'op': 'cancel'})
    messages.success(request, translator(resolve_lang(request))('common.saved'))
    return redirect('web:sale-detail', pk=pk)


# ── Receipt PDF ─────────────────────────────────────────────────────
RECEIPT_LABELS = {
    'uz': {'receipt': 'Chek', 'date': 'Sana', 'cashier': 'Kassir', 'customer': 'Mijoz',
           'item': 'Mahsulot', 'qty': 'Soni', 'price': 'Narx', 'sum': 'Summa',
           'subtotal': 'Jami', 'discount': 'Chegirma', 'total': 'JAMI', 'cash': 'NAQD',
           'card': 'KARTA', 'received': 'OLINDI', 'change': 'QAYTIM',
           'thanks': 'Xaridingiz uchun rahmat!'},
    'ru': {'receipt': 'Чек', 'date': 'Дата', 'cashier': 'Кассир', 'customer': 'Клиент',
           'item': 'Товар', 'qty': 'Кол-во', 'price': 'Цена', 'sum': 'Сумма',
           'subtotal': 'Итого', 'discount': 'Скидка', 'total': 'ИТОГО', 'cash': 'НАЛИЧНЫЕ',
           'card': 'КАРТА', 'received': 'ПОЛУЧЕНО', 'change': 'СДАЧА',
           'thanks': 'Спасибо за покупку!'},
}


@store_required
@require_GET
def receipt_pdf(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related('items'), pk=pk, store=request.store)
    lang = request.GET.get('lang') or resolve_lang(request)
    labels = RECEIPT_LABELS.get(lang, RECEIPT_LABELS['uz'])
    buffer = _build_receipt_pdf(sale, labels)

    receipt = getattr(sale, 'receipt', None)
    if receipt:
        Receipt.objects.filter(pk=receipt.pk).update(printed_count=receipt.printed_count + 1)

    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="receipt_{sale.sale_number}.pdf"'
    return response


def _build_receipt_pdf(sale, labels):
    from pathlib import Path
    from xml.sax.saxutils import escape

    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(8.0 * cm, 24 * cm),
                            rightMargin=0.45 * cm, leftMargin=0.45 * cm,
                            topMargin=0.5 * cm, bottomMargin=0.5 * cm)
    font_dir = Path(reportlab.__file__).parent / 'fonts'
    if 'ReceiptFont' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ReceiptFont', str(font_dir / 'Vera.ttf')))
        pdfmetrics.registerFont(TTFont('ReceiptBold', str(font_dir / 'VeraBd.ttf')))
        pdfmetrics.registerFontFamily('ReceiptFont', normal='ReceiptFont', bold='ReceiptBold')

    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontName='ReceiptFont', fontSize=7.5, leading=9.5)
    centre = ParagraphStyle('centre', parent=small, alignment=1)
    bold = ParagraphStyle('bold', parent=small, fontName='ReceiptBold')

    story = [
        Paragraph(f'<b>{escape(sale.store.name)}</b>',
                  ParagraphStyle('h', parent=styles['Title'], fontName='ReceiptBold', fontSize=12, alignment=1)),
        Paragraph(f"{labels['receipt']} №{sale.sale_number}", centre),
        Spacer(1, 0.15 * cm),
        Paragraph(f"{labels['date']}: {timezone.localtime(sale.created_at):%d.%m.%Y %H:%M}", small),
        Paragraph(f"{labels['cashier']}: {escape(sale.cashier.display_name)}", small),
    ]
    if sale.store.address:
        story.append(Paragraph(escape(sale.store.address), centre))
    if sale.store.receipt_header:
        story.append(Paragraph(escape(sale.store.receipt_header), centre))
    if sale.customer:
        story.append(Paragraph(f"{labels['customer']}: {escape(sale.customer.name)}", small))
    story.append(Spacer(1, 0.2 * cm))

    rows = [[labels['item'], labels['qty'], labels['sum']]]
    for item in sale.items.all():
        variant = ' / '.join(p for p in [item.color_name, item.size_name] if p)
        name = item.product_name if not variant else f'{item.product_name} ({variant})'
        rows.append([Paragraph(escape(name), small), str(item.quantity), f'{item.total_price:.0f}'])

    table = Table(rows, colWidths=[4.3 * cm, 1.2 * cm, 1.6 * cm])
    table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'ReceiptFont'), ('FONTSIZE', (0, 0), (-1, -1), 7.5),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('LINEBELOW', (0, 0), (-1, 0), 0.4, colors.black),
        ('LINEABOVE', (0, -1), (-1, -1), 0.4, colors.black), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))
    story += [table, Spacer(1, 0.2 * cm)]

    if sale.discount_amount:
        story.append(Paragraph(f"{labels['discount']} -{sale.discount_amount:.0f}", small))
    story.append(Paragraph(f"<b>{labels['total']} {sale.total_amount:.2f} {escape(sale.store.currency_symbol)}</b>", small))
    if sale.cash_amount:
        story.append(Paragraph(f"{labels['cash']} {sale.cash_amount:.0f}", small))
    if sale.card_amount:
        story.append(Paragraph(f"{labels['card']} {sale.card_amount:.0f}", small))
    if sale.change_amount:
        story.append(Paragraph(f"{labels['change']} {sale.change_amount:.0f}", small))
    story += [Spacer(1, 0.35 * cm),
              Paragraph(escape(sale.store.receipt_footer or labels['thanks']), centre)]
    doc.build(story)
    buffer.seek(0)
    return buffer
