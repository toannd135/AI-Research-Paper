# Biến môi trường để chạy API/worker trực tiếp trên máy host (không trong Docker).
# .env dùng hostname nội bộ Docker (postgres/redis/qdrant) -> đổi sang cổng đã publish ra localhost.
# Dùng: source scripts/host_env.sh   (chạy từ thư mục gốc repo; không sửa .env)

cd "$(dirname "${BASH_SOURCE[0]:-${(%):-%x}}")/.." || return 1
[ -f venv/bin/activate ] && source venv/bin/activate

_db_url="$(command grep -m1 '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '\r"'"'")"
export DATABASE_URL="${_db_url/@postgres:5432/@localhost:5433}"
unset _db_url
export QDRANT_URL=http://localhost:6333
export REDIS_URL=redis://localhost:6380/0
export CELERY_BROKER_URL=redis://localhost:6380/0
export CELERY_RESULT_BACKEND=redis://localhost:6380/1
export UPLOAD_DIR=data/papers_brain EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=22000

echo "host_env: DB=${DATABASE_URL##*@} | broker=$CELERY_BROKER_URL | upload_dir=$UPLOAD_DIR"
