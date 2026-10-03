"""Access-control decorators for the server-rendered UI.

Mirrors the DRF permission model so the SSR pages enforce exactly the same
rules: a store is required for staff, roles gate the pages, and a deactivated
store blocks access.
"""
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from apps.web.i18n import translator

MANAGER_ROLES = ('owner', 'manager')
STAFF_ROLES = ('owner', 'manager', 'cashier')


def _lang(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and getattr(user, 'language', None) in ('uz', 'ru'):
        return user.language
    return request.session.get('brandx_lang', 'uz')


def _deny(request, text_key):
    t = translator(_lang(request))
    messages.error(request, t(text_key))
    return redirect('web:dashboard')


def login_required_web(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url='/store/login/')
        return view(request, *args, **kwargs)
    return wrapper


def store_required(view):
    """Require an authenticated employee bound to an active store."""
    @wraps(view)
    @login_required_web
    def wrapper(request, *args, **kwargs):
        user = request.user
        if user.role == 'platform_admin':
            return redirect('web:platform')
        if not user.store_id:
            return _deny(request, 'common.error')
        if not user.is_active or not user.store.is_active:
            messages.error(request, translator(_lang(request))('common.error'))
            return redirect('web:logout')
        request.store = user.store
        return view(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        @store_required
        def wrapper(request, *args, **kwargs):
            if request.user.role not in roles:
                return _deny(request, 'common.error')
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def manager_required(view):
    return role_required(*MANAGER_ROLES)(view)


def owner_required(view):
    return role_required('owner')(view)


def platform_admin_required(view):
    @wraps(view)
    @login_required_web
    def wrapper(request, *args, **kwargs):
        if request.user.role != 'platform_admin':
            return redirect('web:dashboard')
        return view(request, *args, **kwargs)
    return wrapper
