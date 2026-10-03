"""Employees (owner) and personal settings pages."""
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.authentication.models import User
from apps.authentication.validators import pin_is_taken, validate_pin_format
from apps.web.decorators import owner_required, store_required
from apps.web.forms import EmployeeForm, StoreSettingsForm
from apps.web.i18n import translator
from apps.web.views.helpers import page_title, resolve_lang


@owner_required
def employee_list(request):
    store = request.store
    employees = User.objects.filter(store=store).exclude(role='platform_admin').order_by('first_name', 'username')
    return render(request, 'web/employees.html', {
        'page_title': page_title(request, 'employees.title'),
        'employees': employees,
        'form': EmployeeForm(),
    })


@owner_required
def employee_save(request):
    store = request.store
    t = translator(resolve_lang(request))
    if request.method != 'POST':
        return redirect('web:employees')

    pk = request.POST.get('id')
    instance = User.objects.filter(pk=pk, store=store).exclude(role='owner').first() if pk else None
    form = EmployeeForm(request.POST, instance=instance)
    if not form.is_valid():
        messages.error(request, t('common.error'))
        return redirect('web:employees')

    pin = form.cleaned_data.get('pin') or ''
    if pin and pin_is_taken(pin, exclude_user_id=instance.pk if instance else None, store=store):
        messages.error(request, t('employees.pinTaken'))
        return redirect('web:employees')

    user = form.save(commit=False)
    user.store = store
    user.is_staff = False
    user.is_superuser = False
    if not instance:
        user.set_unusable_password()
    user.save()
    if pin:
        user.set_pin(pin)
        user.save(update_fields=['pin_hash', 'updated_at'])

    if instance:
        log_action(AuditLog.ACTION_USER_UPDATED, user=request.user, entity='user', entity_id=user.pk,
                   details={'username': user.username})
    else:
        log_action(AuditLog.ACTION_USER_CREATED, user=request.user, entity='user', entity_id=user.pk,
                   details={'username': user.username, 'role': user.role})
    messages.success(request, t('common.saved'))
    return redirect('web:employees')


@owner_required
@require_POST
def employee_set_pin(request, pk):
    store = request.store
    t = translator(resolve_lang(request))
    user = get_object_or_404(User, pk=pk, store=store)
    try:
        pin = validate_pin_format(request.POST.get('pin'))
    except Exception:
        messages.error(request, t('employees.pinRule'))
        return redirect('web:employees')
    if pin_is_taken(pin, exclude_user_id=user.pk, store=store):
        messages.error(request, t('employees.pinTaken'))
        return redirect('web:employees')
    user.set_pin(pin)
    user.save(update_fields=['pin_hash', 'updated_at'])
    log_action(AuditLog.ACTION_PIN_CHANGED, user=request.user, entity='user', entity_id=user.pk,
               details={'by': 'owner'})
    messages.success(request, t('common.saved'))
    return redirect('web:employees')


@owner_required
@require_POST
def employee_deactivate(request, pk):
    store = request.store
    user = get_object_or_404(User, pk=pk, store=store)
    if user.role == 'owner':
        return redirect('web:employees')
    user.is_active = False
    user.save(update_fields=['is_active', 'updated_at'])
    log_action(AuditLog.ACTION_USER_DEACTIVATED, user=request.user, entity='user', entity_id=user.pk,
               details={'username': user.username})
    messages.success(request, translator(resolve_lang(request))('common.saved'))
    return redirect('web:employees')


# ── Personal settings ───────────────────────────────────────────────
@store_required
def settings_view(request):
    store = request.store
    user = request.user
    t = translator(resolve_lang(request))

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'profile':
            user.first_name = (request.POST.get('first_name') or '').strip()
            user.last_name = (request.POST.get('last_name') or '').strip()
            user.phone = (request.POST.get('phone') or '').strip()
            lang = request.POST.get('language')
            if lang in ('uz', 'ru'):
                user.language = lang
                request.session['brandx_lang'] = lang
            user.save()
            messages.success(request, t('common.saved'))
            return redirect('web:settings')

        if action == 'pin':
            current = request.POST.get('current_pin') or ''
            new = request.POST.get('pin') or ''
            confirm = request.POST.get('pin_confirm') or ''
            if not user.check_pin(current):
                messages.error(request, t('auth.wrongPin'))
            elif new != confirm:
                messages.error(request, t('settings.pinMismatch'))
            else:
                try:
                    pin = validate_pin_format(new)
                    if pin_is_taken(pin, exclude_user_id=user.pk, store=store):
                        messages.error(request, t('employees.pinTaken'))
                    else:
                        user.set_pin(pin)
                        user.save(update_fields=['pin_hash', 'updated_at'])
                        log_action(AuditLog.ACTION_PIN_CHANGED, user=user, entity='user',
                                   entity_id=user.pk, details={'by': 'self'})
                        messages.success(request, t('common.saved'))
                except Exception:
                    messages.error(request, t('employees.pinRule'))
            return redirect('web:settings')

        if action == 'store' and user.role == 'owner':
            form = StoreSettingsForm(request.POST)
            if form.is_valid():
                store.phone = form.cleaned_data['phone']
                store.address = form.cleaned_data['address']
                store.receipt_header = form.cleaned_data['receipt_header']
                store.receipt_footer = form.cleaned_data['receipt_footer']
                store.low_stock_threshold = form.cleaned_data['low_stock_threshold']
                store.save(update_fields=['phone', 'address', 'receipt_header', 'receipt_footer',
                                          'low_stock_threshold', 'updated_at'])
                log_action(AuditLog.ACTION_SETTINGS_CHANGED, user=user, entity='store', entity_id=store.pk)
                messages.success(request, t('common.saved'))
            return redirect('web:settings')

    return render(request, 'web/settings.html', {
        'page_title': page_title(request, 'settings.title'),
        'store': store,
        'is_owner': user.role == 'owner',
        'store_form': StoreSettingsForm(initial={
            'phone': store.phone, 'address': store.address,
            'receipt_header': store.receipt_header, 'receipt_footer': store.receipt_footer,
            'low_stock_threshold': store.low_stock_threshold,
        }),
    })
