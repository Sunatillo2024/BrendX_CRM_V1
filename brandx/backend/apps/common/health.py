"""Lightweight liveness/readiness probe used by Docker health checks.

Deliberately a plain Django view (not DRF) so it stays public, fast and free of
authentication or store-context requirements. It answers 200 only while the
database is reachable, so an unhealthy container never receives traffic.
"""
from django.db import connection
from django.http import JsonResponse


def health(request):
    """Return HTTP 200 while the app and its database respond, else HTTP 503."""
    database_ok = True
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
    except Exception:
        database_ok = False

    return JsonResponse(
        {'status': 'ok' if database_ok else 'degraded', 'database': database_ok},
        status=200 if database_ok else 503,
    )
