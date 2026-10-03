#!/usr/bin/env bash
# BrandX deploy oldidan muhit tekshiruvi: tooling, .env.prod, portlar, disk.
set -euo pipefail
cd "$(dirname "$0")/../.."

fail=0

echo "==> Tooling tekshiruvi"
for cmd in docker git curl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "  XATO: '$cmd' topilmadi"; fail=1; }
done
docker compose version >/dev/null 2>&1 || { echo "  XATO: 'docker compose' plugin yo'q"; fail=1; }

echo "==> deploy/.env.prod"
if [ -f deploy/.env.prod ]; then
  echo "  OK: fayl mavjud"
  for var in SECRET_KEY ALLOWED_HOSTS CSRF_TRUSTED_ORIGINS DB_NAME DB_USER DB_PASSWORD; do
    grep -qE "^${var}=.+" deploy/.env.prod || { echo "  XATO: ${var} to'ldirilmagan"; fail=1; }
  done
else
  echo "  XATO: yo'q. Nusxa oling: cp deploy/.env.prod.example deploy/.env.prod"
  fail=1
fi

PORT="${BRANDX_HTTP_PORT:-8080}"
BIND="${BRANDX_HTTP_BIND:-127.0.0.1}"
if [ -f deploy/.env.prod ]; then
  p=$(grep -E '^BRANDX_HTTP_PORT=' deploy/.env.prod | tail -1 | cut -d= -f2- | tr -d '[:space:]')
  [ -n "$p" ] && PORT="$p"
  b=$(grep -E '^BRANDX_HTTP_BIND=' deploy/.env.prod | tail -1 | cut -d= -f2- | tr -d '[:space:]')
  [ -n "$b" ] && BIND="$b"
fi

echo "==> Port tekshiruvi (${BIND}:${PORT})"
if command -v ss >/dev/null 2>&1 && ss -tulpn 2>/dev/null | grep -qE "[:.]${PORT}[[:space:]]"; then
  echo "  DIQQAT: ${PORT}-port BAND:"
  ss -tulpn 2>/dev/null | grep -E "[:.]${PORT}[[:space:]]" || true
  echo "  deploy/.env.prod da boshqa port yozing."
  fail=1
else
  echo "  OK: ${PORT}-port bo'sh"
fi

echo "=== Hozir eshitilayotgan portlar ==="
ss -tulpn 2>/dev/null | head -20 || true
echo "=== Disk ==="
df -h / | tail -1

if [ "$fail" -ne 0 ]; then
  echo "PREFLIGHT: MUAMMOLAR TOPILDI - yuqoridagi xatolarni tuzating."
  exit 1
fi
echo "PREFLIGHT: hammasi joyida ✓"
