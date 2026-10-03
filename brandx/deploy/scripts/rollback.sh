#!/usr/bin/env bash
# BrandX rollback: oxirgi muvaffaqiyatli image'ga qaytish.
#
#   deploy.sh har ishga tushganda joriy image'ni brandx-backend:previous
#   belgisi bilan saqlaydi. Shu skript uni qayta "prod" qilib ishga tushiradi.
#
#   DIQQAT: migratsiyalar bir tomonlama bo'lishi mumkin - kerak bo'lsa bazani
#   backup'dan tiklang (README 11-bo'lim).
set -euo pipefail
cd "$(dirname "$0")/../.."

[ -f deploy/.env.prod ] || { echo "XATO: deploy/.env.prod yo'q"; exit 1; }
BX="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod"

docker image inspect brandx-backend:previous >/dev/null 2>&1 || {
  echo "XATO: brandx-backend:previous image topilmadi (rollback joyi yo'q)."
  exit 1
}

docker tag brandx-backend:previous brandx-backend:prod
$BX up -d --no-build backend
echo "==> Rollback bajarildi ✓"
$BX ps
