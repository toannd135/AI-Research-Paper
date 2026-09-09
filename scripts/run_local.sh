#!/usr/bin/env bash
# Helper: chạy docker compose + migrate
set -euo pipefail

cd "$(dirname "$0")/.."

[ -f .env ] || cp .env.example .env

docker compose up -d postgres qdrant redis
docker compose run --rm api alembic upgrade head
docker compose up -d api worker

echo "API: http://localhost:8000/docs"
