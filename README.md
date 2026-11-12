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

## Setup (máy mới vừa pull về)

Yêu cầu: Git, Docker + Docker Compose v2 (Docker Desktop trên Windows/Mac). Máy cần có Internet
cho lần build đầu (tải pip, Chromium, Tectonic + gói LaTeX IEEEtran — khoảng 10–20 phút).

```bash
git pull
cp .env.example .env            # chỉ lần đầu; điền API key LLM (GEMINI/OPENROUTER/GROQ...) + JWT_SECRET
```

### Cách A — chạy toàn bộ bằng Docker (khuyên dùng, không phải cài gì thêm)

Image `paperai-app:local` đã có sẵn Python deps, Chromium, Mermaid/KaTeX và **Tectonic** (xuất PDF LaTeX),
build được trên Linux/Windows (x86_64) và Mac Apple Silicon (arm64).

```bash
./scripts/run_local.sh          # hạ tầng + build api/worker + alembic upgrade head + chạy api/worker
# Windows không có bash: chạy tay 4 lệnh trong scripts/run_local.sh
```

- API: http://localhost:8000/docs
- Log: `docker compose --profile app logs -f api worker`
- Dừng: `docker compose --profile app stop` (giữ nguyên dữ liệu)
- Sau mỗi lần pull có đổi `Dockerfile`/`requirements*.txt`: `docker compose --profile app up -d --build api worker`
- Đổi code Python: không cần build lại (mã nguồn được mount vào container, api tự reload; worker thì
  `docker compose --profile app restart worker`).
- Kiểm tra Tectonic trong container: `docker compose --profile app exec api tectonic --version`

### Cách B — hạ tầng trong Docker, api/worker chạy trên host (cách dev hay dùng)

`docker compose up -d` (không có `--profile app`) chỉ chạy postgres/qdrant/redis.
Trong `.env` đổi URL sang cổng host: `DATABASE_URL=postgresql+psycopg://paperai:paperai@localhost:5433/paperai`,
`QDRANT_URL=http://localhost:6333`, `REDIS_URL`/`CELERY_BROKER_URL=redis://localhost:6380/0`,
`CELERY_RESULT_BACKEND=redis://localhost:6380/1`.

```bash
docker compose up -d
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -c requirements-constraints.txt
python -m playwright install chromium
npm ci --prefix app/pipeline/export/assets          # Windows: npm.cmd
alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info
```

Xuất PDF LaTeX cần **Tectonic** trên host (Docker cách A đã có sẵn). Cài một lần:

```bash
# Linux x86_64 (Mac Apple Silicon: đổi x86_64 -> aarch64; hoặc `brew install tectonic`)
mkdir -p ~/.local/bin
curl -fsSL https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%400.15.0/tectonic-0.15.0-x86_64-unknown-linux-musl.tar.gz \
  | tar -xz -C ~/.local/bin tectonic
tectonic --version
```

App tự tìm Tectonic theo thứ tự: biến `PAPERAI_TECTONIC` → `PATH` → `~/.local/bin/tectonic`.
Windows: tải bản `x86_64-pc-windows-msvc` rồi thêm vào PATH (hoặc đặt `PAPERAI_TECTONIC`).
Lần biên dịch đầu Tectonic tải gói LaTeX từ Internet.

**Đừng chạy cả hai cách cùng lúc** (trùng cổng 8000, hai worker cùng lấy task trong Redis).

### Chạy một phiên research từ terminal (Linux, cách B)

Hướng dẫn đầy đủ từng bước: `docs/huong-dan-chay.md`. Tóm tắt (chạy trong thư mục `paperai`):

```bash
# 0. Hạ tầng (một lần)
docker compose up -d
source scripts/host_env.sh && alembic upgrade head

# 1. Tab 1 — API (http://localhost:8000/docs)
source scripts/host_env.sh && uvicorn app.main:app --reload

# 2. Tab 2 — worker (sửa code backend thì Ctrl+C rồi chạy lại)
source scripts/host_env.sh && celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info

# 3. (Tuỳ chọn) Phiên/workspace mới chứa các paper trong một thư mục đã nạp; lấy id rồi sửa
#    "workspace_id" trong data/requests/mri_brain_survey.json
source scripts/host_env.sh
python scripts/assign_papers.py --dir data/papers_brain --email admin@gmail.com --workspace "<tên phiên>" --apply
docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc "select id, name from workspaces"

# 4. Gửi câu hỏi research (-sS: báo lỗi nếu API chưa chạy; có thể mất vài phút vì gọi LLM làm rõ câu hỏi)
set -a; . ./.env; set +a
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r '.access_token // .token')
curl -sS -m 300 localhost:8000/research/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @data/requests/mri_brain_survey.json
TASK=<id vừa nhận>

# 5. Theo dõi (~20 phút trở lên): processing -> done (report > 0) | failed (xem cột lỗi)
docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc \
  "select status, length(coalesce(report,'')), left(coalesce(error,''),150) from research_tasks where id='$TASK'"
# Task đang chạy / hàng đợi
docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc "select id, status from research_tasks where status in ('pending','processing')"
docker exec paperai-redis-1 redis-cli llen research_queue

# 6. Xuất PDF LaTeX (bảng "Table 1.", hình "Figure 1.") và BibTeX
curl -s "localhost:8000/research/$TASK/pdf?engine=latex&template=ieee" -H "authorization: Bearer $TOKEN" \
  -o data/exports/paper_${TASK:0:8}_latex.pdf
curl -s "localhost:8000/research/$TASK/bib" -H "authorization: Bearer $TOKEN" -o data/exports/paper_${TASK:0:8}.bib

# Dừng (giữ dữ liệu). KHÔNG dùng `docker compose down -v` (xoá volume chứa paper đã nạp)
docker compose stop
```

- Lệnh gửi không in gì / token `null` → API chưa chạy (bước 1).
- Worker log chỉ có `received` → đang chờ LLM trả lời (model free có thể xếp hàng tới 15 phút/lời gọi).
- Dự phòng LLM khi 429/413: OpenRouter khóa 1 (`OPENROUTER_MODEL`) → Groq (`GROQ_MODEL`) → OpenRouter khóa 2 (`OPENROUTER_MODEL_2`, trống thì dùng `OPENROUTER_MODEL`).

### Xuất PDF

Mặc định dùng Chromium hai cột; bảng và hình trải ngang trang. Nút **PDF 1 cột** tạo bản một cột.
Xuất LaTeX (IEEEtran) dùng Tectonic; API vẫn hỗ trợ `engine=typst` khi cần.

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

**Kiểm tra đủ paper trước khi chạy research (bắt buộc):** research chỉ truy xuất paper có `status = done` trong DB, nên phải xác nhận mọi PDF trong `data/papers_brain` đã được lập chỉ mục. Lệnh chỉ đọc, thoát mã `1` nếu còn paper thiếu:
```bash
source venv/bin/activate
python -c "import pathlib,sys; from app.core.database import SessionLocal; from app.api.models.paper import Paper; ids={p.stem for p in pathlib.Path('data/papers_brain').glob('*.pdf')}; db=SessionLocal(); done={i for i,s in db.query(Paper.id,Paper.status).all() if s=='done'}; db.close(); miss=ids-done; print(f'PDF {len(ids)} | done {len(ids&done)} | thieu {len(miss)}'); sys.exit(1 if miss else 0)" && echo "OK: đủ paper, có thể chạy research"
```
Kết quả phải là `PDF 50 | done 50 | thieu 0` (số PDF hiện có trong `data/papers_brain`). Nếu còn thiếu, chờ worker `upload_queue` xử lý xong rồi chạy lại lệnh; chưa đủ thì không gửi task.

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
Kiểm tra trước khi gửi task: chạy lệnh kiểm tra đủ paper ở phần Chuẩn bị (phải in `thieu 0`).
Thấy dòng `ready` là sẵn sàng. Log `Trích xuất lô N/M` cho biết tiến độ trích xuất số liệu (mỗi lô được cache trong `data/cache/extract/`; quá ngân sách 25 phút thì bỏ các lô còn lại để graph đi tiếp).

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
  "How should reported experimental results be compared?":"Use only numerical results explicitly reported in original papers. Record BraTS edition, dataset, evaluation split, validation or test setting, segmentation metrics, missing-modality configuration, and reported uncertainty where available. Distinguish full-modality performance from missing-modality performance. Do not directly rank or quantitatively compare studies with incompatible datasets or evaluation protocols. Preserve original Dice scales and units (ratio vs percentage) and mark unavailable information as NR. Distinguish Reported, Not reported (NR) and Not retrieved; never treat Not retrieved as evidence of absence. Group quantitative evidence by BraTS edition, evaluation split, tumor region, metric and missing-modality configuration; separate validation from hidden-test results and predefined missing-modality configurations from arbitrary modality subsets. State whether a value is a single experiment, a per-case average or an average across modality configurations. Every numerical, comparative and factual claim must trace to an identifiable source in the corpus; never invent authors, titles, venues, DOIs or corpus statistics.",
  "Which analytical dimensions should guide the comparison?":"Compare methods across four dimensions: segmentation performance, robustness to missing modalities, computational efficiency, and clinical reliability. Discuss computational cost only when supported by reported parameters, FLOPs, memory usage, inference time, or other explicit measurements. Discuss clinical reliability in terms of external validation, uncertainty estimation, calibration, and failure detection when evidence is available.",
  "What are the expected scientific contributions of the survey?":"Develop an evidence-based analytical framework that connects fusion mechanisms, missing-modality handling strategies, and evaluation protocols. Compare strengths and limitations of existing approaches, identify gaps in experimental evaluation, and formulate specific future research directions. Keep three kinds of content separate: findings supported by the original papers, evidence gaps where the corpus lacks data, and research proposals by the authors. Classify methods with a multi-label, multi-axis taxonomy (fusion strategy, encoder design, fusion location, missing-modality strategy, availability awareness, evaluation coverage) instead of forcing one category per paper. For every research gap give the observed findings, the specific missing evidence, why it matters, and a concrete future direction; never present a proposed direction as an experimentally demonstrated conclusion. Quantitative figures must be reproducible from extracted evidence; label conceptual diagrams as author-designed. Conclusions must not exceed the strength of the evidence.",
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

## Chạy bài so sánh (comparison) multimodal deepfake detection (3 terminal)

Đề tài: *so sánh kết quả đã công bố của các detector deepfake dựa trên foundation model (CLIP/VLM, ViT, speech SSL, MLLM) với CNN truyền thống*. Loại bài `comparison` (giao diện: "So sánh các mô hình"), không phải survey như bài MRI. Nguồn: **chỉ** 50 PDF trong `data/papers_deepfake` (manifest: `_manifest.json`). Dùng chung stack `paperai_bt` với bài MRI; khác ở các điểm sau:

1. **Kho riêng, loại kho = `deepfake`.** Mỗi paper thuộc 1 user và 1 kho; task gắn `workspace_id` chỉ truy xuất paper `done` của kho đó và tắt hẳn OpenAlex. Loại kho (`workspaces.domain`) quyết định bộ prompt: kho `deepfake` dùng quy tắc trích xuất AUC/EER/ACC, giao thức in-domain/cross-dataset/cross-generator, c23/c40; kho `mri_brain` dùng BraTS/Dice/WT-TC-ET. Kho tạo bằng `assign_papers.py` mặc định là `general` → **phải đổi sang `deepfake`** (lệnh dưới hoặc trang Kho dữ liệu). Không gộp PDF MRI và deepfake vào cùng một kho; không chạy bằng admin mà không có `workspace_id` (admin không chỉ định kho thấy MỌI paper).
2. **Comparison không có số liệu tự chạy** (`user_results` trống) chạy theo khung bài tổng hợp, nhưng nội dung xoay quanh so sánh: giao thức so sánh, mỗi bối cảnh đánh giá một bảng (≤ 8 cột), kết luận theo ràng buộc (nên chọn họ phương pháp nào khi nào). Không được ghi là tự chạy lại mô hình.
3. PDF deepfake đặt tên theo tiêu đề (không phải UUID) nên lệnh kiểm tra đủ paper so khớp theo tên tệp (`file_path`), không theo `id`.
4. Không có `catalog.json`: References lấy tiêu đề/năm/DOI từ `_manifest.json` (khớp theo tên tệp), tác giả/venue đọc từ trang 1 của PDF. Vẫn rà tay tác giả trước khi nộp.

**Chuẩn bị (một lần mỗi phiên):**
```bash
docker compose -p paperai_bt up -d postgres qdrant redis
docker exec paperai_bt-redis-1 redis-cli llen research_queue   # phải = 0
docker exec paperai_bt-redis-1 redis-cli exists unacked        # phải = 0
alembic upgrade head   # lần đầu sau khi cập nhật: áp migration 0009 (workspaces) và 0010 (workspaces.domain) — bạn tự chạy trên DB của mình
```
Sau khi API (Terminal 1) và worker (Terminal 2) đã chạy và nạp xong PDF, tạo user riêng, gán paper, đặt loại kho:
```bash
set -a; . ./.env; set +a
curl -s localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"deepfake@example.com","password":"<mật-khẩu-mạnh>","full_name":"Deepfake comparison"}' | jq -c '{email:.user.email}'
source venv/bin/activate
python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake comparison"            # dry-run: liệt kê
python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake comparison" --apply    # ghi user_id + workspace_id (tạo kho nếu chưa có)
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"deepfake@example.com","password":"<mật-khẩu-mạnh>"}' | jq -r '.access_token // .token')   # token của USER, không dùng admin
WS=$(curl -s localhost:8000/workspaces -H "authorization: Bearer $TOKEN" | jq -r '.[] | select(.name=="Deepfake comparison") | .id'); echo "workspace: $WS"
# đặt loại kho = deepfake (bắt buộc; phải in "deepfake")
curl -s -X PATCH localhost:8000/workspaces/$WS -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"domain":"deepfake"}' | jq -r .domain
```

**Kiểm tra kho chỉ chứa paper deepfake (bắt buộc, chạy sau khi API đã nạp PDF):** lệnh chỉ đọc, thoát mã `1` nếu kho thiếu paper, có paper ngoài `data/papers_deepfake`, hoặc loại kho không phải `deepfake`:
```bash
WS=$WS python -c "import os,pathlib,sys; from app.core.database import SessionLocal; from app.api.models.paper import Paper; from app.api.models.workspace import Workspace; ws=os.environ['WS']; root=pathlib.Path('data/papers_deepfake').resolve(); names={p.name for p in root.glob('*.pdf')}; db=SessionLocal(); dom=db.get(Workspace,ws).domain; rows=db.query(Paper.file_path,Paper.status).filter(Paper.workspace_id==ws).all(); db.close(); done={pathlib.Path(fp).name for fp,s in rows if s=='done'}; outside=[fp for fp,_ in rows if pathlib.Path(fp).resolve().parent!=root]; miss=names-done; print(f'domain {dom} | PDF {len(names)} | done {len(names&done)} | thieu {len(miss)} | ngoai thu muc {len(outside)}'); [print(' -',m) for m in sorted(miss)+outside]; sys.exit(1 if miss or outside or dom!='deepfake' else 0)" && echo "OK: kho sạch, có thể chạy research"
```
Phải in `domain deepfake | PDF 50 | done 50 | thieu 0 | ngoai thu muc 0`. Paper `pending`/`processing` mãi nghĩa là chưa có worker `upload_queue` chạy (Terminal 2) hoặc worker đã bị tắt giữa chừng; chạy lại worker rồi `process_paper.delay(<id>)` cho paper kẹt.

### Terminal 1 — API
```bash
source venv/bin/activate
export UPLOAD_DIR=data/papers_deepfake EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=22000
uvicorn app.main:app --port 8000        # tự nạp PDF trong UPLOAD_DIR (tạo record pending, đẩy vào upload_queue)
```

### Terminal 2 — Worker
```bash
source venv/bin/activate
export UPLOAD_DIR=data/papers_deepfake EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=22000
# export EMBEDDING_DEVICE=cuda   # tùy chọn
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -c 1 -l info
```
Khởi động worker TRƯỚC hoặc ngay sau API, chờ lệnh kiểm tra đủ paper in `thieu 0` rồi mới gửi task. Không để nạp paper và sinh paper chạy xen nhau.

### Terminal 3 — Gửi task và theo dõi
```bash
# dùng $TOKEN và $WS đã đặt ở phần Chuẩn bị (cùng terminal; nếu mở terminal mới thì đặt lại)
# yêu cầu: data/requests/deepfake_comparison.json (contribution_type = comparison); gắn workspace_id của kho Deepfake
jq --arg ws "$WS" '.workspace_id = $ws' data/requests/deepfake_comparison.json > /tmp/req_df_ws.json
curl -s localhost:8000/research/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @/tmp/req_df_ws.json | jq -c '{id,status}'

# theo dõi (~20 phút trở lên)
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc \
  "select id,status,length(coalesce(report,'')) from research_tasks"
```
**Đảm bảo reference chỉ từ `data/papers_deepfake`:** (1) task gắn `workspace_id` thì hệ thống ép chế độ chỉ-kho-nội-bộ, tắt hẳn OpenAlex dù `EXTERNAL_SEARCH_ENABLED` là gì, và truy xuất chỉ trong paper của workspace; (2) sau khi xong, kiểm chứng bằng lệnh chỉ đọc (thoát mã `1` nếu có citation ngoài thư mục):
```bash
python scripts/verify_task_sources.py --task <task_id> --dir data/papers_deepfake
```
Phải in `ngoài data/papers_deepfake: 0` và `OK`. Lưu ý: lệnh chỉ kiểm paper được trích dẫn; số liệu/thực thể LLM tự thêm vào văn bản mà không có `[n]` do quality gate bắt (`validation/<task_id>.json`: UNTRACED/NO_CITATION).

Khi `status = done`: kiểm chứng ở `data/papers_deepfake/validation/<task_id>.json` (đọc `passed`, `blocking`, `warnings`, đếm TRACED/UNTRACED/NO_CITATION); xuất PDF:
```bash
curl -s -H "authorization: Bearer $TOKEN" "localhost:8000/research/<task_id>/pdf?draft=true" -o comparison_deepfake.pdf
```

**Checklist chuẩn nộp Q1/Q2 (đối chiếu trước khi nộp):**
- Bài là "comparative analysis of published results" trên corpus 50 paper (nguồn OpenAlex open access), KHÔNG gọi là systematic review, KHÔNG ghi là tự chạy lại mô hình. Muốn gọi systematic review thì tự làm: tìm CSDL (Scopus/WoS/IEEE/arXiv), chuỗi truy vấn, tiêu chí gộp/loại, sơ đồ PRISMA, 2 reviewer độc lập.
- `validation/<task_id>.json`: `passed = true`, `blocking` rỗng, không còn UNTRACED/NO_CITATION; mọi con số trong bảng truy được về paper.
- Không so xếp hạng giữa các paper khác dataset/giao thức; giữ nguyên thang gốc (%, tỉ lệ); ô thiếu ghi NR.
- Rà tay tác giả trong References (tiêu đề/năm/DOI lấy từ `_manifest.json`, tác giả đọc từ PDF); References không được còn UUID hay "Anonymous".
- Mỗi bảng so sánh chỉ một bối cảnh đánh giá (cùng dataset/giao thức/metric); log worker phải có `Bắt đầu [Deepfake]`.
- Đối chiếu tính mới với các survey/bài so sánh deepfake đã xuất bản (hệ thống không tự kiểm tra được).
- Corpus 50 paper là nhỏ: nêu rõ giới hạn phạm vi ở phần Methodology/Limitations; mở rộng corpus là việc của bạn.

### Dừng và dọn
```bash
ps -eo pid,args | grep -E "[c]elery -A|[u]vicorn app"   # lấy PID rồi: kill <pid>  (KHÔNG dùng pkill -f)
docker compose -p paperai_bt stop                        # giữ nguyên dữ liệu
docker exec paperai_bt-redis-1 redis-cli del unacked unacked_index   # hủy task treo
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "delete from research_tasks where id='<task_id>'"
```
