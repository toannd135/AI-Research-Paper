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

Xuất PDF mặc định dùng Chromium hai cột; bảng và hình trải ngang trang.
Nút **PDF 1 cột** tạo bản một cột. API vẫn hỗ trợ `engine=typst` khi cần.
Docker đóng gói sẵn Chromium, Mermaid và KaTeX nên xuất PDF không cần CDN.
Nếu chạy Python trực tiếp, cài thêm tài nguyên render:

```powershell
python -m playwright install chromium
npm.cmd ci --prefix app/pipeline/export/assets
```

Sau khi cập nhật Dockerfile hoặc requirements, chạy `docker compose up -d --build api worker`.

## Test

```bash
pytest
```
