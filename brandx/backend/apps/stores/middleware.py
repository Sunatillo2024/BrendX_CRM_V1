from django.http import HttpResponseForbidden
from django.utils import timezone
from zoneinfo import ZoneInfo


class StoreContextMiddleware:
    """Store-aware timezone activation for the server-rendered UI.

    With the DRF API removed, users always arrive via Django session auth, so
    this middleware only guards /admin/ and switches to the store's timezone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if request.path.startswith('/admin/') and user.is_authenticated and user.role != 'platform_admin':
            return HttpResponseForbidden('Technical admin access denied.')
        timezone.deactivate()
        if user and user.is_authenticated and user.store_id and user.store.is_active:
            timezone.activate(ZoneInfo(user.store.timezone))
        try:
            return self.get_response(request)
        finally:
            timezone.deactivate()
