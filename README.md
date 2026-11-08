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

## Chạy survey brain tumor (3 terminal)

Chi tiết và điều kiện chạy: `docs/runbook-brain-tumor-survey.md`. Chạy tất cả từ thư mục gốc repo.

**Chuẩn bị (một lần mỗi phiên):** bật hạ tầng, rồi kiểm tra hàng đợi trống.
```bash
docker compose -p paperai_bt up -d postgres qdrant redis
docker exec paperai_bt-redis-1 redis-cli llen research_queue   # phải = 0
docker exec paperai_bt-redis-1 redis-cli exists unacked        # phải = 0 (khác 0 thì task cũ sẽ chạy lại)
```

### Terminal 1 — API
```bash
source venv/bin/activate
export UPLOAD_DIR=data/papers_brain EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=22000
uvicorn app.main:app --port 8000
```

### Terminal 2 — Worker
```bash
source venv/bin/activate
export UPLOAD_DIR=data/papers_brain EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=22000
# export EMBEDDING_DEVICE=cuda   # tùy chọn: embedding/rerank trên GPU (mặc định tự dò, lùi về CPU)
celery -A app.workers.celery_app worker -Q research_queue -c 1 -l info
```
Thấy dòng `ready` là sẵn sàng. Log `Trích xuất lô N/M` cho biết tiến độ trích xuất số liệu (không có timeout, chạy đủ mọi lô).

### Terminal 3 — Gửi task và theo dõi
```bash
set -a; . ./.env; set +a
cat > /tmp/req.json <<'JSON'
{"question":"Deep Learning-Based Brain Tumor Segmentation with Multi-Modal MRI: Fusion Strategies and Missing-Modality Robustness","audience":"lecturer","field":"computer_vision","contribution_type":"survey",
 "clarification_answers":{
  "What is the primary goal or output of this research report?":"Comprehensive literature review/survey paper",
  "Which specific tumor types or segmentation tasks are in scope?":"Glioma (whole tumor, core, enhancing core) per BraTS",
  "Which MRI modalities and preprocessing aspects should be emphasized?":"Standard 4-modality (T1, T1ce, T2, FLAIR) + fusion strategies; missing modality robustness",
  "What is the intended audience and approximate length of the final report?":"Journal paper (8-12 pages, technical depth)"}}
JSON
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r '.access_token // .token')
curl -s localhost:8000/research/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @/tmp/req.json | jq -c '{id,status}'

# theo dõi (~20 phút trở lên)
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc \
  "select id,status,length(coalesce(report,'')) from research_tasks"
```
Khi `status = done`: kết quả kiểm chứng ở `data/papers_brain/validation/<task_id>.json`; xuất PDF bằng
`curl -s -H "authorization: Bearer $TOKEN" "localhost:8000/research/<task_id>/pdf?draft=true" -o survey.pdf`.

### Dừng và dọn
```bash
ps -eo pid,args | grep -E "[c]elery -A|[u]vicorn app"   # lấy PID rồi: kill <pid>  (KHÔNG dùng pkill -f)
docker compose -p paperai_bt stop                        # giữ nguyên dữ liệu
# Hủy task đang chạy: kill worker, rồi xóa message treo để nó không chạy lại
docker exec paperai_bt-redis-1 redis-cli del unacked unacked_index
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "delete from research_tasks where id='<task_id>'"
```
DB: `localhost:5433`, user/password/db đều là `paperai`.
