"""
PIN login for the Django admin.

Employees sign into /admin/ with a PIN (no username/password form). Only active
staff accounts (owner) are allowed in. The same database-backed throttling used
by the API is reused, so repeated failures lock the IP temporarily.
"""
from django.conf import settings
from django.contrib.auth import login as auth_login
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View

from apps.audit.models import AuditLog
from apps.audit.services import log_action

from .models import PinAttempt, User


def _client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def _safe_next(request, fallback):
    nxt = request.POST.get('next') or request.GET.get('next')
    if nxt and url_has_allowed_host_and_scheme(
        nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return nxt
    return fallback


class PinAdminLoginView(View):
    template_name = 'admin/login.html'

    def _render(self, request, **context):
        context.setdefault('next', _safe_next(request, ''))
        context.setdefault(
            'language', getattr(request, 'LANGUAGE_CODE', settings.LANGUAGE_CODE)
        )
        return render(request, self.template_name, context)

    def get(self, request):
        if request.user.is_authenticated and request.user.is_staff and request.user.role == 'platform_admin':
            return HttpResponseRedirect(_safe_next(request, reverse('admin:index')))
        return self._render(request)

    def post(self, request):
        ip = _client_ip(request)
        max_attempts = getattr(settings, 'PIN_MAX_ATTEMPTS', 10)
        lockout = getattr(settings, 'PIN_LOCKOUT_SECONDS', 300)

        locked_until = PinAttempt.locked_until(ip, max_attempts, lockout)
        if locked_until:
            seconds = max(1, int((locked_until - timezone.now()).total_seconds()))
            return self._render(request, error='locked', retry_after=seconds)

        pin = (request.POST.get('pin') or '').strip()
        if not pin:
            return self._render(request, error='empty')

        user = None
        for candidate in User.objects.filter(
            is_active=True, is_staff=True, role='platform_admin', store__isnull=True
        ).exclude(pin_hash=''):
            if candidate.check_pin(pin):
                user = candidate
                break

        if not user:
            PinAttempt.objects.create(ip_address=ip, was_success=False)
            log_action(AuditLog.ACTION_LOGIN_FAILED, entity='user',
                       details={'ip': ip or '', 'surface': 'admin'})
            remaining = max(0, max_attempts - PinAttempt.recent_failures(ip, lockout))
            return self._render(request, error='wrong', attempts_left=remaining)

        PinAttempt.objects.create(ip_address=ip, was_success=True)
        # Correct PIN entered: clear the failure counter so the next
        # lockout cycle counts PIN_MAX_ATTEMPTS fresh attempts.
        PinAttempt.reset_failures(ip)
        auth_login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        User.objects.filter(pk=user.pk).update(last_login=timezone.now())
        log_action(AuditLog.ACTION_LOGIN, user=user, entity='user', entity_id=user.pk,
                   details={'method': 'pin', 'surface': 'admin'})

        response = HttpResponseRedirect(_safe_next(request, reverse('admin:index')))
        # Open the admin in the employee's preferred language (from the app).
        if user.language in ('uz', 'ru'):
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME, user.language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response
