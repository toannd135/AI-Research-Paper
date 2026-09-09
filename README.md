# paperai

Paper research assistant: upload paper -> parse/chunk -> hybrid RAG -> research agent có citation.

## Cấu trúc

| Thư mục | Chủ sở hữu | Nội dung |
|---|---|---|
| `app/core` | dùng chung | config, schemas, database — interface contract giữa 3 Dev |
| `app/ai` | Dev 1 | embedding, retrieval (vector/BM25/hybrid/rerank), context builder, LLM gateway |
| `app/pipeline` | Dev 2 | PDF parser, chunking, vector store, Celery tasks |
| `app/api` | Dev 2 | FastAPI routes + ORM models |
| `app/agent` | Dev 3 | LangGraph research agent, evidence check, evaluation |
| `app/workers` | Dev 2 | Celery app/queue config |

## Setup

```bash
cp .env.example .env
./scripts/run_local.sh          # docker compose + alembic upgrade head
```

Chạy trực tiếp (không docker):

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info
```

## Test

```bash
pytest
```
