"""Brand-styled error pages, wired via ``handler400..handler500`` in urls.py.

The pages are deliberately self-contained (inline CSS, bilingual hardcoded
text, no DB queries) and render WITHOUT request/context processors: an error
page must render even when the database, static files, the session or a
context processor itself caused the failure. All texts live in the templates.
"""
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.template import loader


def _plain(template_name, response_class):
    """Render context-free; wrap in the matching HTTP error response."""
    return response_class(loader.get_template(template_name).render())


def bad_request(request, exception=None):
    return _plain('errors/400.html', HttpResponseBadRequest)


def permission_denied(request, exception=None):
    return _plain('errors/403.html', HttpResponseForbidden)


def page_not_found(request, exception=None):
    return _plain('errors/404.html', HttpResponseNotFound)


def server_error(request):
    return _plain('errors/500.html', HttpResponseServerError)
