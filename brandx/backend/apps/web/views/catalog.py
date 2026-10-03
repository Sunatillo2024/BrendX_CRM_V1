"""Catalog pages: products (list/form/delete/barcode) and categories."""
import io

import barcode as barcode_lib
from barcode.writer import ImageWriter
from django.contrib import messages
from django.db.models import Q
from django.forms import inlineformset_factory
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.products.models import Category, Product, ProductVariant
from apps.products.utils import generate_barcode
from apps.web.decorators import manager_required, store_required
from apps.web.forms import CategoryForm, ProductForm, VariantForm
from apps.web.i18n import translator
from apps.web.views.helpers import paginate, page_title, query_without_page, resolve_lang

VariantFormSet = inlineformset_factory(
    Product, ProductVariant, form=VariantForm, extra=1, can_delete=True,
    fields=['color', 'size', 'barcode', 'selling_price', 'cost_price',
            'stock_quantity', 'low_stock_threshold', 'is_active'],
)


# ── Products ────────────────────────────────────────────────────────
@manager_required
def product_list(request):
    store = request.store
    query = (request.GET.get('q') or '').strip()
    category_id = request.GET.get('category') or ''
    active = request.GET.get('active', '1')

    qs = Product.objects.filter(store=store).select_related('category').prefetch_related(
        'variants__color', 'variants__size')
    if query:
        qs = qs.filter(Q(name__icontains=query) | Q(barcode__icontains=query))
    if category_id.isdigit():
        qs = qs.filter(category_id=int(category_id))
    if active in ('1', '0'):
        qs = qs.filter(is_active=(active == '1'))
    qs = qs.order_by('name')

    page = paginate(request, qs, 20)
    return render(request, 'web/products/list.html', {
        'page_title': page_title(request, 'products.title'),
        'page_obj': page,
        'query': query,
        'category_id': category_id,
        'active': active,
        'categories': Category.objects.filter(store=store).order_by('name'),
        'query_string': query_without_page(request),
    })


@manager_required
def product_form(request, pk=None):
    store = request.store
    product = get_object_or_404(Product, pk=pk, store=store) if pk else None

    if request.method == 'POST':
        form = ProductForm(request.POST, request.FILES, instance=product, store=store)
        formset = VariantFormSet(request.POST, instance=product, prefix='variants')
        if form.is_valid() and formset.is_valid():
            product = form.save(commit=False)
            product.store = store
            if not product.barcode:
                product.barcode = generate_barcode()
            product.save()
            formset.instance = product
            variants = formset.save(commit=False)
            for deleted in formset.deleted_objects:
                deleted.is_active = False
                deleted.save(update_fields=['is_active', 'updated_at'])
            for variant in variants:
                variant.store = store
                variant.product = product
                if not variant.barcode:
                    variant.barcode = generate_barcode()
                if not variant.sku:
                    variant.sku = variant.generate_sku()
                variant.save()

            action = AuditLog.ACTION_PRODUCT_UPDATED if pk else AuditLog.ACTION_PRODUCT_CREATED
            log_action(action, user=request.user, entity='product', entity_id=product.pk,
                       details={'name': product.name, 'barcode': product.barcode})
            messages.success(request, translator(resolve_lang(request))('common.saved'))
            return redirect('web:product-list')
    else:
        form = ProductForm(instance=product, store=store)
        formset = VariantFormSet(instance=product, prefix='variants')

    return render(request, 'web/products/form.html', {
        'page_title': page_title(request, 'products.edit' if pk else 'products.new'),
        'form': form,
        'formset': formset,
        'product': product,
    })


@manager_required
def product_delete(request, pk):
    store = request.store
    if request.method != 'POST':
        return redirect('web:product-list')
    product = get_object_or_404(Product, pk=pk, store=store)
    product.is_active = False
    product.save(update_fields=['is_active', 'updated_at'])
    product.variants.update(is_active=False)
    log_action(AuditLog.ACTION_PRODUCT_DELETED, user=request.user, entity='product',
               entity_id=product.pk, details={'name': product.name, 'op': 'deactivate'})
    messages.success(request, translator(resolve_lang(request))('common.deleted'))
    return redirect('web:product-list')


@manager_required
def product_barcode_new(request):
    """A fresh unused barcode for the product form's "Avto" button."""
    from django.http import JsonResponse

    from apps.products.utils import generate_barcode

    if request.method != 'GET':
        return redirect('web:product-list')
    return JsonResponse({'barcode': generate_barcode()})


@store_required
def product_barcode_image(request, pk):
    product = get_object_or_404(Product, pk=pk, store=request.store)
    buffer = io.BytesIO()
    try:
        code = barcode_lib.get('code128', product.barcode, writer=ImageWriter())
        code.write(buffer)
        buffer.seek(0)
        return HttpResponse(buffer.read(), content_type='image/png')
    except Exception:
        return HttpResponse(status=400)


# ── Categories ──────────────────────────────────────────────────────
@manager_required
def category_list(request):
    store = request.store
    categories = Category.objects.filter(store=store).order_by('name')
    counts = {c.pk: c.products.filter(is_active=True).count() for c in categories}
    for category in categories:
        category.product_count = counts.get(category.pk, 0)
    return render(request, 'web/categories/list.html', {
        'page_title': page_title(request, 'categories.title'),
        'categories': categories,
        'form': CategoryForm(),
    })


@manager_required
def category_save(request):
    store = request.store
    if request.method != 'POST':
        return redirect('web:category-list')
    pk = request.POST.get('id')
    instance = Category.objects.filter(pk=pk, store=store).first() if pk else None
    form = CategoryForm(request.POST, instance=instance)
    if form.is_valid():
        category = form.save(commit=False)
        category.store = store
        category.save()
        log_action(AuditLog.ACTION_CATEGORY_CHANGED, user=request.user, entity='category',
                   entity_id=category.pk, details={'name': category.name})
        messages.success(request, translator(resolve_lang(request))('common.saved'))
    else:
        messages.error(request, translator(resolve_lang(request))('common.error'))
    return redirect('web:category-list')


@manager_required
def category_delete(request, pk):
    store = request.store
    if request.method != 'POST':
        return redirect('web:category-list')
    category = get_object_or_404(Category, pk=pk, store=store)
    used = category.products.exists()
    if used:
        category.is_active = False
        category.save(update_fields=['is_active'])
        messages.warning(request, translator(resolve_lang(request))('categories.deactivated'))
    else:
        category.delete()
        messages.success(request, translator(resolve_lang(request))('common.deleted'))
    return redirect('web:category-list')
