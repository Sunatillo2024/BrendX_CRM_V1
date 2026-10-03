"""Platform admin pages (global, no store context)."""
from django.contrib import messages
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.audit.services import log_action
from apps.authentication.models import User
from apps.authentication.validators import pin_is_taken, validate_pin_format
from apps.products.models import Product
from apps.sales.models import Sale
from apps.stores.models import Store
from apps.stores.services import make_owner
from apps.web.decorators import platform_admin_required
from apps.web.i18n import translator
from apps.web.views.helpers import page_title, resolve_lang


@platform_admin_required
def platform_dashboard(request):
    stores = Store.objects.all().order_by('-created_at')
    return render(request, 'web/platform/dashboard.html', {
        'page_title': 'Platform Admin',
        'stats': {
            'total_stores': stores.count(),
            'active_stores': stores.filter(is_active=True).count(),
            'inactive_stores': stores.filter(is_active=False).count(),
            'total_users': User.objects.exclude(role='platform_admin').count(),
            'total_owners': User.objects.filter(role='owner').count(),
            'total_sales': Sale.objects.count(),
        },
        'stores': stores[:50],
        'platform': True,
    })


@platform_admin_required
@transaction.atomic
def platform_store_create(request):
    t = translator(resolve_lang(request))
    if request.method != 'POST':
        return redirect('web:platform')

    name = (request.POST.get('name') or '').strip()
    code = (request.POST.get('code') or '').strip().upper()
    owner_name = (request.POST.get('owner_name') or '').strip()
    owner_language = request.POST.get('owner_language') or 'ru'
    if not name or not code or not owner_name:
        messages.error(request, t('common.error'))
        return redirect('web:platform')
    if Store.objects.filter(code=code).exists():
        messages.error(request, t('common.error'))
        return redirect('web:platform')
    try:
        owner_pin = validate_pin_format(request.POST.get('owner_pin'))
    except Exception:
        messages.error(request, t('employees.pinRule'))
        return redirect('web:platform')

    store = Store.objects.create(
        name=name, code=code, phone=request.POST.get('phone', ''),
        address=request.POST.get('address', ''),
        default_language=owner_language if owner_language in ('uz', 'ru') else 'ru')
    make_owner(store, owner_name, owner_pin, owner_language)
    log_action('store_created', user=request.user, store=store, entity='store', entity_id=store.pk)
    messages.success(request, t('common.saved'))
    return redirect('web:platform-store-detail', pk=store.pk)


@platform_admin_required
def platform_store_detail(request, pk):
    store = get_object_or_404(Store, pk=pk)
    owners = store.user_set.filter(role='owner')
    return render(request, 'web/platform/store_detail.html', {
        'page_title': store.name,
        'store': store,
        'owners': owners,
        'employees_count': store.user_set.exclude(role='platform_admin').count(),
        'products_count': Product.objects.filter(store=store).count(),
        'sales_today': Sale.objects.filter(store=store, created_at__date=timezone.localdate()).count(),
        'last_activity': store.user_set.aggregate(last=Max('last_login'))['last'],
        'platform': True,
    })


@platform_admin_required
@require_POST
def platform_store_update(request, pk):
    store = get_object_or_404(Store, pk=pk)
    store.name = (request.POST.get('name') or store.name).strip()
    store.phone = request.POST.get('phone', store.phone)
    store.address = request.POST.get('address', store.address)
    if request.POST.get('toggle') == '1':
        store.is_active = not store.is_active
    store.save()
    log_action('store_updated', user=request.user, store=store, entity='store',
               entity_id=store.pk, details={'active': store.is_active})
    messages.success(request, translator(resolve_lang(request))('common.saved'))
    return redirect('web:platform-store-detail', pk=store.pk)


@platform_admin_required
@require_POST
@transaction.atomic
def platform_manage_owner(request, pk):
    store = Store.objects.select_for_update().get(pk=get_object_or_404(Store, pk=pk).pk)
    t = translator(resolve_lang(request))
    name = (request.POST.get('name') or '').strip()
    language = request.POST.get('language', store.default_language)
    try:
        pin = validate_pin_format(request.POST.get('pin'))
    except Exception:
        messages.error(request, t('employees.pinRule'))
        return redirect('web:platform-store-detail', pk=store.pk)
    if not name or language not in ('uz', 'ru'):
        messages.error(request, t('common.error'))
        return redirect('web:platform-store-detail', pk=store.pk)

    owner = store.user_set.filter(role='owner').first()
    if pin_is_taken(pin, exclude_user_id=owner.pk if owner else None, store=store):
        messages.error(request, t('employees.pinTaken'))
        return redirect('web:platform-store-detail', pk=store.pk)

    if owner:
        owner.first_name = name
        owner.language = language
        owner.is_active = True
        owner.set_pin(pin)
        owner.save()
    else:
        owner = make_owner(store, name, pin, language)
    log_action('store_owner_changed', user=request.user, store=store, entity='user', entity_id=owner.pk)
    messages.success(request, t('common.saved'))
    return redirect('web:platform-store-detail', pk=store.pk)


@platform_admin_required
def platform_store_list(request):
    """JSON list used by the dashboard search (kept intentionally small)."""
    from django.http import JsonResponse
    query = (request.GET.get('search') or '').strip()
    qs = Store.objects.all()
    if query:
        from django.db.models import Q
        qs = qs.filter(Q(name__icontains=query) | Q(code__icontains=query) | Q(phone__icontains=query))
    data = [{'id': s.pk, 'name': s.name, 'code': s.code, 'is_active': s.is_active}
            for s in qs.order_by('-created_at')[:50]]
    return JsonResponse({'results': data})
