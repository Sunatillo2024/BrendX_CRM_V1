"""BrandX - Main URL Configuration (server-rendered UI only)."""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve as media_serve

from apps.authentication.admin_login import PinAdminLoginView
from apps.common.health import health

admin.site.site_header = 'BrandX'
admin.site.site_title = 'BrandX'
admin.site.index_title = 'Boshqaruv'

urlpatterns = [
    # PIN login for the admin (must come before admin.site.urls so it wins).
    path('admin/login/', PinAdminLoginView.as_view(), name='admin-pin-login'),
    path('admin/', admin.site.urls),

    # Language switching (used by the admin language chooser).
    path('i18n/', include('django.conf.urls.i18n')),

    # Public health probe for Docker / load balancers (no auth, no store context).
    path('health/', health, name='health'),

    # Server-rendered UI (Django templates + session auth).
    path('', include('apps.web.urls')),

    # Product photos and other uploads. Media is served by Django directly:
    # the previous Angular/nginx container no longer exists.
    re_path(r'^media/(?P<path>.*)$', media_serve, {'document_root': settings.MEDIA_ROOT}),
]
