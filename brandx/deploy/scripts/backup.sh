#!/usr/bin/env bash
# BrandX backup: PostgreSQL (custom format) + media volume -> backups/
# 14 kundan eski nusxalar avtomatik o'chiriladi.
set -euo pipefail
cd "$(dirname "$0")/../.."

[ -f deploy/.env.prod ] || { echo "XATO: deploy/.env.prod yo'q"; exit 1; }
set -a; . deploy/.env.prod; set +a

mkdir -p backups
STAMP=$(date +%Y%m%d-%H%M%S)
BX="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod"

echo "==> PostgreSQL backup..."
$BX exec -T postgres pg_dump -U "${DB_USER:?DB_USER yo'q}" -d "${DB_NAME:?DB_NAME yo'q}" -Fc \
  > "backups/db-${STAMP}.dump"

echo "==> Media volume backup..."
docker run --rm \
  -v brandx_prod_media_data:/data:ro \
  -v "$(pwd)/backups":/backup \
  alpine tar czf "/backup/media-${STAMP}.tar.gz" -C /data . \
  2>/dev/null || echo "DIQQAT: media volume hali bo'sh bo'lishi mumkin (birinchi deploy)"

echo "Tayyor:"
ls -lh "backups/db-${STAMP}.dump" "backups/media-${STAMP}.tar.gz" 2>/dev/null || \
  ls -lh "backups/db-${STAMP}.dump"

# Retenshion: 14 kundan eskilarni o'chirish
find backups -name 'db-*.dump' -mtime +14 -delete 2>/dev/null || true
find backups -name 'media-*.tar.gz' -mtime +14 -delete 2>/dev/null || true
