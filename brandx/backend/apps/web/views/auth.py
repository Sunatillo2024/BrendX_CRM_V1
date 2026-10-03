"""PIN session authentication for the server-rendered UI."""
from django.conf import settings
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.db import transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from apps.audit.models import AuditLog
from apps.audit.services import log_action
from apps.authentication.models import PinAttempt, User
from apps.web.i18n import translator


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def home_redirect(request):
    """Landing route: send the visitor to the right place by role."""
    if not request.user.is_authenticated:
        return redirect('web:login')
    if request.user.role == 'platform_admin':
        return redirect('web:platform')
    if getattr(request.user, 'is_cashier', False):
        return redirect('web:pos')
    return redirect('web:dashboard')


def _find_pin_user(pin, store_code, platform):
    """Return the employee whose PIN matches, or None. Same rules as the API."""
    candidates = User.objects.filter(is_active=True).exclude(pin_hash='').select_related('store')
    if platform:
        candidates = candidates.filter(role='platform_admin', store__isnull=True)
    else:
        code = (store_code or '').strip().upper()
        if not code:
            return None
        candidates = candidates.filter(store__code=code, store__is_active=True).exclude(role='platform_admin')
    for candidate in candidates:
        if candidate.check_pin(pin):
            return candidate
    return None


def login_view(request, code=None, platform=False):
    platform = bool(platform)

    # Allow ?lang=xx on the login page itself.
    requested_lang = request.GET.get('lang')
    if requested_lang in ('uz', 'ru'):
        request.session['brandx_lang'] = requested_lang
        params = request.GET.copy()
        params.pop('lang', None)
        url = request.path + (f'?{params.urlencode()}' if params else '')
        return redirect(url)

    store_code = (code or request.POST.get('store_code') or '').upper().strip()

    lang = request.session.get('brandx_lang')
    if lang not in ('uz', 'ru'):
        lang = getattr(settings, 'DEFAULT_LANGUAGE', 'uz')
    t = translator(lang)

    if request.user.is_authenticated:
        return redirect('web:home')

    context = {
        'platform': platform,
        'store_code': store_code,
        'error': None,
        'attempts_left': None,
        'locked': False,
    }

    if request.method == 'POST':
        ip = _client_ip(request)
        max_attempts = getattr(settings, 'PIN_MAX_ATTEMPTS', 10)
        lockout = getattr(settings, 'PIN_LOCKOUT_SECONDS', 300)

        locked_until = PinAttempt.locked_until(ip, max_attempts, lockout)
        if locked_until:
            seconds = max(1, int((locked_until - timezone.now()).total_seconds()))
            context['locked'] = True
            context['error'] = t('auth.tooManyAttempts')
            context['retry_after'] = seconds
            return render(request, 'web/auth/login.html', context, status=429)

        if platform:
            entered = (request.POST.get('pin') or '').strip()
            user = _find_pin_user(entered, '', True)
        else:
            store_code = (request.POST.get('store_code') or store_code or '').strip().upper()
            entered = ''.join(ch for ch in (request.POST.get('pin') or '') if ch.isdigit())
            if not store_code:
                context['error'] = t('common.error')
                context['store_code'] = store_code
                return render(request, 'web/auth/login.html', context)
            user = _find_pin_user(entered, store_code, False)

        if user is None:
            PinAttempt.objects.create(ip_address=ip, was_success=False)
            log_action(AuditLog.ACTION_LOGIN_FAILED, entity='user', details={'ip': ip or ''})
            remaining = max(0, max_attempts - PinAttempt.recent_failures(ip, lockout))
            context['error'] = t('auth.wrongPin')
            context['attempts_left'] = remaining
            context['store_code'] = store_code
            return render(request, 'web/auth/login.html', context, status=400)

        PinAttempt.objects.create(ip_address=ip, was_success=True)
        # Correct PIN entered: clear the failure counter so the next
        # lockout cycle counts PIN_MAX_ATTEMPTS fresh attempts.
        PinAttempt.reset_failures(ip)
        User.objects.filter(pk=user.pk).update(last_login=timezone.now())
        log_action(AuditLog.ACTION_LOGIN, user=user, entity='user', entity_id=user.pk,
                   details={'method': 'pin', 'ui': 'web'})

        # Session login (the DRF/JWT backend is not used for rendered pages).
        user.backend = 'django.contrib.auth.backends.ModelBackend'
        auth_login(request, user)
        if user.language in ('uz', 'ru'):
            request.session['brandx_lang'] = user.language

        destination = request.POST.get('next')
        if destination and url_has_allowed_host_and_scheme(destination, {request.get_host()}):
            return HttpResponseRedirect(destination)
        if user.role == 'platform_admin':
            return redirect('web:platform')
        if getattr(user, 'is_cashier', False):
            return redirect('web:pos')
        return redirect('web:dashboard')

    return render(request, 'web/auth/login.html', context)


@transaction.atomic
def logout_view(request):
    if request.user.is_authenticated:
        log_action(AuditLog.ACTION_LOGOUT, user=request.user, entity='user', entity_id=request.user.pk)
    auth_logout(request)
    return redirect('web:login')


def set_language(request, code):
    """Persist the UI language (session + employee record) and return."""
    code = code if code in ('uz', 'ru') else 'uz'
    request.session['brandx_lang'] = code
    if request.user.is_authenticated and request.user.language != code:
        User.objects.filter(pk=request.user.pk).update(language=code)

    target = request.META.get('HTTP_REFERER') or reverse('web:home')
    response = HttpResponseRedirect(target)
    response.set_cookie('brandx_lang', code, max_age=60 * 60 * 24 * 365, samesite='Lax')
    return response
