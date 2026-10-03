"""Stock (warehouse), goods receipts and POS lookup endpoints."""
from decimal import Decimal

from django.contrib import messages
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.inventory import services as inventory_services
from apps.inventory.models import StockMovement, StockReceipt
from apps.products.models import ProductVariant
from apps.vendors.models import Vendor
from apps.web.decorators import manager_required, store_required
from apps.web.i18n import translator
from apps.web.views.helpers import page_title, resolve_lang


def _variant_row(variant):
    return {
        'id': variant.id,
        'product_id': variant.product_id,
        'product_name': variant.product.name,
        'barcode': variant.barcode,
        'color_name': variant.color.name if variant.color else '',
        'size_name': variant.size.name if variant.size else '',
        'price': str(variant.effective_price),
        'stock_quantity': variant.stock_quantity,
    }


@store_required
def stock_view(request):
    store = request.store
    variants = ProductVariant.objects.filter(store=store, is_active=True, product__is_active=True)
    cost = Coalesce('cost_price', 'product__base_cost_price')
    price = Coalesce('selling_price', 'product__base_selling_price')

    valuation = variants.aggregate(
        cost_value=Sum(ExpressionWrapper(cost * F('stock_quantity'),
                                        output_field=DecimalField(max_digits=18, decimal_places=2))),
        retail_value=Sum(ExpressionWrapper(price * F('stock_quantity'),
                                           output_field=DecimalField(max_digits=18, decimal_places=2))),
        units=Sum('stock_quantity'),
    )
    cost_value = valuation['cost_value'] or Decimal('0')
    retail_value = valuation['retail_value'] or Decimal('0')

    movements = StockMovement.objects.filter(
        product_variant__store=store
    ).select_related('product_variant__product', 'created_by').order_by('-created_at')[:50]

    return render(request, 'web/stock.html', {
        'page_title': page_title(request, 'stock.title'),
        'valuation': {
            'cost_value': cost_value,
            'retail_value': retail_value,
            'potential_profit': retail_value - cost_value,
            'variants_in_stock': variants.filter(stock_quantity__gt=0).count(),
            'units_in_stock': valuation['units'] or 0,
        },
        'movements': movements,
    })


@manager_required
@require_POST
def stock_adjust(request):
    store = request.store
    variant_id = (request.POST.get('variant_id') or '').strip()
    mode = request.POST.get('mode') or 'delta'
    raw_quantity = request.POST.get('quantity') or '0'
    reason = request.POST.get('reason') or 'correction'
    notes = (request.POST.get('notes') or '').strip()
    t = translator(resolve_lang(request))

    # The variant search field lives inside this form - an accidental
    # Enter/submit must never reach the ORM with an empty id (ValueError -> 500).
    if not variant_id.isdigit():
        messages.error(request, t('stock.selectVariant'))
        return redirect('web:stock')

    variant = ProductVariant.objects.filter(pk=variant_id, store=store).first()
    if not variant:
        messages.error(request, t('stock.selectVariant'))
        return redirect('web:stock')
    try:
        quantity = int(raw_quantity)
    except ValueError:
        messages.error(request, t('common.error'))
        return redirect('web:stock')

    try:
        if mode == 'counted':
            inventory_services.set_counted_stock(variant, quantity, user=request.user,
                                                 reason=reason, notes=notes)
            action = AuditLog.ACTION_INVENTORY_COUNT
        else:
            inventory_services.change_stock(variant, quantity, StockMovement.TYPE_ADJUSTMENT,
                                            user=request.user, reason=reason, notes=notes)
            action = AuditLog.ACTION_STOCK_ADJUSTED
    except inventory_services.InsufficientStock:
        messages.error(request, t('common.error'))
        return redirect('web:stock')

    log_action(action, user=request.user, entity='variant', entity_id=variant.pk,
               details={'mode': mode, 'quantity': quantity})
    messages.success(request, t('common.saved'))
    return redirect('web:stock')


# ── POS JSON lookups ────────────────────────────────────────────────
@store_required
@require_GET
def pos_search(request):
    store = request.store
    query = (request.GET.get('q') or '').strip()
    try:
        limit = min(int(request.GET.get('limit', 40)), 200)
    except ValueError:
        limit = 40
    qs = ProductVariant.objects.filter(
        store=store, is_active=True, product__is_active=True
    ).select_related('product', 'color', 'size')
    category_id = (request.GET.get('category') or '').strip()
    if category_id.isdigit():
        qs = qs.filter(product__category_id=int(category_id))
    if query:
        qs = qs.filter(
            Q(product__name__icontains=query) | Q(barcode__icontains=query)
            | Q(product__barcode__icontains=query) | Q(sku__icontains=query)
        )
    qs = qs.order_by('product__name')[:limit]
    return JsonResponse({'results': [_variant_row(v) for v in qs]})


@store_required
@require_GET
def pos_barcode(request):
    store = request.store
    code = (request.GET.get('code') or '').strip()
    if not code:
        return JsonResponse({'detail': 'barcode required'}, status=400)
    variant = ProductVariant.objects.filter(store=store, barcode=code, is_active=True).select_related(
        'product', 'color', 'size').first()
    if variant:
        return JsonResponse({'type': 'variant', 'variant': _variant_row(variant)})
    product = None
    from apps.products.models import Product
    product = Product.objects.filter(store=store, barcode=code, is_active=True).first()
    if product:
        variants = product.variants.filter(is_active=True).select_related('color', 'size')
        return JsonResponse({'type': 'product', 'product': {'id': product.id, 'name': product.name},
                             'variants': [_variant_row(v) for v in variants]})
    return JsonResponse({'detail': 'not found'}, status=404)


# ── Goods receipts ──────────────────────────────────────────────────
@manager_required
def receipts_view(request):
    store = request.store
    if request.method == 'POST':
        return _create_receipt(request)
    receipts = StockReceipt.objects.filter(store=store).select_related('vendor', 'created_by').order_by('-number')[:100]
    return render(request, 'web/receipts/list.html', {
        'page_title': page_title(request, 'receipts.title'),
        'receipts': receipts,
    })


def _create_receipt(request):
    store = request.store
    t = translator(resolve_lang(request))
    variant_ids = request.POST.getlist('variant_id')
    quantities = request.POST.getlist('quantity')
    costs = request.POST.getlist('cost_price')

    items = []
    for vid, qty, cost in zip(variant_ids, quantities, costs):
        if not vid or not qty:
            continue
        try:
            items.append({'product_variant': int(vid), 'quantity': int(qty),
                          'cost_price': Decimal(cost or '0')})
        except (ValueError, ArithmeticError):
            continue

    if not items:
        messages.error(request, t('common.error'))
        return redirect('web:receipts')

    vendor = None
    vendor_id = request.POST.get('vendor_id')  # kept for API compatibility; the UI no longer sends it
    if vendor_id:
        vendor = Vendor.objects.filter(pk=vendor_id, store=store).first()

    try:
        receipt = inventory_services.receive_stock(
            items=items, user=request.user, vendor=vendor, notes=request.POST.get('notes', ''))
    except Exception:
        messages.error(request, t('common.error'))
        return redirect('web:receipts')

    log_action(AuditLog.ACTION_STOCK_RECEIPT, user=request.user, entity='receipt',
               entity_id=receipt.pk, details={'number': receipt.number})
    messages.success(request, t('common.saved'))
    return redirect('web:receipt-detail', pk=receipt.pk)


@manager_required
def receipt_detail(request, pk):
    receipt = get_object_or_404(StockReceipt, pk=pk, store=request.store)
    return render(request, 'web/receipts/detail.html', {
        'page_title': page_title(request, 'receipts.detail'),
        'receipt': receipt,
    })
