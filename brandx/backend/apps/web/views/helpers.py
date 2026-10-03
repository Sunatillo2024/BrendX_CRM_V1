"""Shared helpers for the server-rendered views."""
from django.conf import settings
from django.core.paginator import EmptyPage, Paginator

from apps.web.i18n import translator


def resolve_lang(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and getattr(user, 'language', None) in ('uz', 'ru'):
        return user.language
    lang = request.session.get('brandx_lang')
    if lang in ('uz', 'ru'):
        return lang
    return getattr(settings, 'DEFAULT_LANGUAGE', 'uz')


def page_title(request, key):
    """Translated page title for the top bar."""
    return translator(resolve_lang(request))(key)


def paginate(request, queryset, per_page=20):
    """Return (page_obj, els) for a queryset using per_page from ?page_size."""
    try:
        size = int(request.GET.get('page_size', per_page))
    except (TypeError, ValueError):
        size = per_page
    size = max(1, min(size, 200))
    paginator = Paginator(queryset, size)
    number = request.GET.get('page') or 1
    try:
        page = paginator.page(number)
    except EmptyPage:
        page = paginator.page(paginator.num_pages or 1)
    return page


def query_without_page(request):
    """Current query string without the ``page`` key (for pagination links)."""
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()
