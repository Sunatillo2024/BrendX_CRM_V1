#!/bin/sh
# BrandX backend - production entrypoint.
# Waits for the database, applies migrations, collects static files and then
# hands control to Gunicorn. Any failure aborts the boot (set -e) so an
# unhealthy container is never reported as running.
set -e

echo "==> Waiting for the configured database ..."
python - <<'PY'
import os
import sys
import time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'brandx_api.settings')
import django
django.setup()
from django.db import connection

for attempt in range(1, 61):
    try:
        connection.ensure_connection()
        print(f'{connection.vendor} is ready (attempt {attempt}).')
        connection.close()
        break
    except Exception:
        # Never log the exception: it can contain connection details.
        connection.close()
        print(f'  ... database not ready (attempt {attempt})')
        time.sleep(2)
else:
    print('Database did not become ready in time.', file=sys.stderr)
    sys.exit(1)
PY

echo "==> Applying database migrations ..."
python manage.py migrate --noinput

# A transfer target must stay empty until a validated import completes, so
# provisioning is explicit only and never resets credentials on every restart.
if [ "${BOOTSTRAP_ADMIN:-false}" = "true" ]; then
  : "${DJANGO_ADMIN_USERNAME:?Set DJANGO_ADMIN_USERNAME}"
  : "${DJANGO_ADMIN_PASSWORD:?Set DJANGO_ADMIN_PASSWORD}"
  : "${DJANGO_ADMIN_PIN:?Set DJANGO_ADMIN_PIN}"
  echo "==> Provisioning the platform administrator ..."
  python manage.py create_admin \
    --username "$DJANGO_ADMIN_USERNAME" \
    --password "$DJANGO_ADMIN_PASSWORD" \
    --pin "$DJANGO_ADMIN_PIN"
fi

if [ "${SEED_DATA:-false}" = "true" ]; then
  echo "==> Seeding starter categories / colours / sizes ..."
  : "${SEED_STORE_CODE:?Set SEED_STORE_CODE}"
  python manage.py seed_data --store "$SEED_STORE_CODE"
fi

echo "==> Collecting static files ..."
python manage.py collectstatic --noinput >/dev/null

# Report (but never abort on) deployment-checklist warnings in production.
if [ "${DEBUG:-false}" = "false" ]; then
  echo "==> Running deployment checklist ..."
  python manage.py check --deploy || \
    echo "WARNING: 'check --deploy' reported issues (see the lines above)."
fi

echo "==> Starting Gunicorn on 0.0.0.0:8000 ..."
exec gunicorn brandx_api.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers "${GUNICORN_WORKERS:-3}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile -
