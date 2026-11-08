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
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -c 1 -l info
```
`upload_queue` nạp PDF mới (paper `pending` → `done`); bỏ queue này thì paper mới thêm không vào Qdrant và không được cite.
Kiểm tra trước khi gửi task: `docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "select status,count(*) from papers group by status"` phải là `done|55`.
Thấy dòng `ready` là sẵn sàng. Log `Trích xuất lô N/M` cho biết tiến độ trích xuất số liệu (không có timeout, chạy đủ mọi lô).

### Terminal 3 — Gửi task và theo dõi
```bash
set -a; . ./.env; set +a
cat > /tmp/req.json <<'JSON'
{"question":"How do deep learning methods perform multimodal fusion of T1, T1ce, T2, and FLAIR MRI for BraTS glioma segmentation, and how effectively do these methods maintain segmentation performance under single- and multiple-missing-modality scenarios? What are the trade-offs among fusion strategies in terms of segmentation accuracy, modality robustness, computational efficiency, and clinical reliability?",
 "audience":"lecturer","field":"computer_vision","contribution_type":"survey",
 "target_venue":"Journal paper (8-12 pages)",
 "clarification_answers":{
  "What is the primary goal or output of this research report?":"A critical literature survey comparing multimodal MRI fusion strategies and missing-modality learning methods for BraTS glioma segmentation. Synthesize reported experimental evidence, identify methodological limitations, compare competing approaches, and derive evidence-supported research gaps. Use reported results from original studies only; do not invent, estimate, or infer missing numerical results. Describe the review scope accurately as a survey of the provided corpus; do not call it a systematic review unless a database search and screening were actually performed.",
  "Which specific tumor types or segmentation tasks are in scope?":"Glioma segmentation using the BraTS benchmark, focusing on whole tumor (WT), tumor core (TC), and enhancing tumor (ET).",
  "Which MRI modalities and preprocessing aspects should be emphasized?":"The four standard BraTS MRI modalities: T1, T1ce (T1c), T2, and FLAIR. Emphasize multimodal fusion strategies, including early fusion, late fusion, hybrid fusion, attention-based fusion, modality-specific encoders, and adaptive fusion. Discuss preprocessing and data harmonization only when supported by the reviewed studies.",
  "Which missing-modality scenarios and methodological families should be analyzed?":"Analyze single-modality and multiple-modality missing scenarios. Examine modality dropout, modality-specific encoding, shared latent representations, knowledge distillation, modality synthesis or reconstruction, and adaptive missing-modality-aware fusion. Distinguish methods evaluated on arbitrary modality subsets from methods evaluated only on predefined missing-modality scenarios. Do not assume that every method supports all possible modality combinations or that every family has BraTS evidence in the corpus.",
  "How should reported experimental results be compared?":"Use only numerical results explicitly reported in original papers. Record BraTS edition, dataset, evaluation split, validation or test setting, segmentation metrics, missing-modality configuration, and reported uncertainty where available. Distinguish full-modality performance from missing-modality performance. Do not directly rank or quantitatively compare studies with incompatible datasets or evaluation protocols. Preserve original Dice scales and units (ratio vs percentage) and mark unavailable information as NR.",
  "Which analytical dimensions should guide the comparison?":"Compare methods across four dimensions: segmentation performance, robustness to missing modalities, computational efficiency, and clinical reliability. Discuss computational cost only when supported by reported parameters, FLOPs, memory usage, inference time, or other explicit measurements. Discuss clinical reliability in terms of external validation, uncertainty estimation, calibration, and failure detection when evidence is available.",
  "What are the expected scientific contributions of the survey?":"Develop an evidence-based analytical framework that connects fusion mechanisms, missing-modality handling strategies, and evaluation protocols. Compare strengths and limitations of existing approaches, identify gaps in experimental evaluation, and formulate specific future research directions. Keep three kinds of content separate: findings supported by the original papers, evidence gaps where the corpus lacks data, and research proposals by the authors.",
  "What is the intended audience and approximate length of the final report?":"Researchers in medical image analysis, computer vision, and biomedical engineering. Target an 8-12 page journal manuscript with sufficient technical depth, critical comparison, concise evidence tables, and a clearly stated review methodology; length must not limit the analysis."}}
JSON
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r '.access_token // .token')
curl -s localhost:8000/research/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @/tmp/req.json | jq -c '{id,status}'

# theo dõi (~20 phút trở lên)
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc \
  "select id,status,length(coalesce(report,'')) from research_tasks"
```
Yêu cầu hợp lệ theo `ResearchRequest` (`app/core/schemas.py`): `question` là câu hỏi nghiên cứu hoàn chỉnh (không phải tiêu đề);
`clarification_answers` đã đủ nên API không trả lại `needs_clarification`. Đổi đề tài thì sửa cả các câu trả lời cho khớp.
`audience` chỉ nhận `lecturer|student|professional`; `lecturer` là giá trị gần "researcher" nhất, phần đối tượng nghiên cứu nằm ở câu trả lời cuối.
Yêu cầu chỉ định hướng nội dung; tính mới Q1/Q2 vẫn phải đối chiếu với các survey đã xuất bản.

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
