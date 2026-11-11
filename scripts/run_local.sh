#!/usr/bin/env bash
# Helper: chạy toàn bộ bằng docker compose (hạ tầng + api/worker build từ Dockerfile, đã có Chromium + Tectonic) + migrate
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

docker compose up -d postgres qdrant redis
docker compose --profile app build api
docker compose --profile app run --rm --no-deps api alembic upgrade head
docker compose --profile app up -d api worker

echo "API: http://localhost:8000/docs"
