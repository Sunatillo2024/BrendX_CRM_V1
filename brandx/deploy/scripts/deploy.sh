#!/usr/bin/env bash
# BrandX to'liq deploy:
#   (testlar) -> backup -> joriy image'ni "previous" qilib saqlash
#   -> image qurish -> stack ko'tarish -> healthy bo'lguncha kutish.
#
#   ./deploy/scripts/deploy.sh               # test + backup + deploy
#   ./deploy/scripts/deploy.sh --skip-tests  # testlarni o'tkazib yuborish
#   ./deploy/scripts/deploy.sh --pull        # avval git pull --ff-only
set -euo pipefail
cd "$(dirname "$0")/../.."

SKIP_TESTS=false; DO_PULL=false
for arg in "$@"; do
  case "$arg" in
    --skip-tests) SKIP_TESTS=true ;;
    --pull)       DO_PULL=true ;;
    *) echo "Noma'lum argument: $arg (faqat --skip-tests, --pull)"; exit 1 ;;
  esac
done

[ -f deploy/.env.prod ] || { echo "XATO: deploy/.env.prod yo'q"; exit 1; }
BX="docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod"

if [ "$DO_PULL" = true ]; then
  echo "==> git pull --ff-only"
  git pull --ff-only
fi

if [ "$SKIP_TESTS" = false ]; then
  ./deploy/scripts/test.sh
fi

./deploy/scripts/backup.sh || echo "DIQQAT: backup bajarilmadi - davom etamiz"

# Joriy ishlab turgan image'ni "previous" belgisi bilan saqlaymiz (rollback uchun).
if docker image inspect brandx-backend:prod >/dev/null 2>&1; then
  docker tag brandx-backend:prod brandx-backend:previous
fi

echo "==> Production image qurilmoqda..."
$BX build backend

echo "==> Stack ko'tarilmoqda..."
$BX up -d --remove-orphans

PORT=$(grep -E '^BRANDX_HTTP_PORT=' deploy/.env.prod | tail -1 | cut -d= -f2- | tr -d '[:space:]')
PORT="${PORT:-8080}"

echo "==> Backend 'healthy' bo'lishi kutilmoqda (maks. 3 daqiqa)..."
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/health/" >/dev/null 2>&1; then
    echo "==> Deploy MUVAFFAQIYATLI ✓"
    $BX ps
    echo "    Health: http://127.0.0.1:${PORT}/health/"
    docker image prune -f >/dev/null 2>&1 || true
    exit 0
  fi
  sleep 3
done

echo "XATO: backend 3 daqiqada healthy bo'lmadi. Oxirgi loglar:"
$BX logs --tail=50 backend
exit 1
