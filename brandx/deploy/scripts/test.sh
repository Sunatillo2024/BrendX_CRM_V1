#!/usr/bin/env bash
# BrandX testlarini izolyatsiyalangan Docker stack ichida ishga tushirish:
# production image + vaqtinchalik tmpfs PostgreSQL. Production'ga tegmaydi.
set -euo pipefail
cd "$(dirname "$0")/../.."

cleanup() {
  docker compose -f deploy/docker-compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "==> Production image qurilmoqda (test bilan bir xil kod)..."
docker compose -f deploy/docker-compose.test.yml build tests

echo "==> Testlar ishga tushmoqda..."
docker compose -f deploy/docker-compose.test.yml up --exit-code-from tests tests
