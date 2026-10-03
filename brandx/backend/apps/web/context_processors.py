"""Template context shared by every server-rendered page."""
from django.conf import settings

from apps.web.i18n import LANGUAGES


def brandx_context(request):
    user = getattr(request, 'user', None)
    authenticated = bool(user and user.is_authenticated)

    chosen = None
    if authenticated and getattr(user, 'language', None) in ('uz', 'ru'):
        chosen = user.language
    if not chosen:
        chosen = request.session.get('brandx_lang')
    if not chosen:
        chosen = request.COOKIES.get('brandx_lang')
    if chosen not in ('uz', 'ru'):
        chosen = getattr(settings, 'DEFAULT_LANGUAGE', 'uz')

    return {
        'brand_lang': chosen,
        'brand_languages': LANGUAGES,
        'brand_user': user if authenticated else None,
        'BUSINESS_NAME': getattr(settings, 'BUSINESS_NAME', 'BrandX'),
        'CURRENCY_SYMBOL': getattr(settings, 'CURRENCY_SYMBOL', 'сом'),
    }
