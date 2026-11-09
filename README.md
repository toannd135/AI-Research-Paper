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

## Chạy survey multimodal deepfake detection (3 terminal)

Đề tài: *Foundation Models for Multimodal Deepfake Detection: Architectures, Cross-Modal Learning, Robustness, and Open Challenges*. Nguồn: 50 PDF trong `data/papers_deepfake` (manifest: `_manifest.json`). Dùng chung stack `paperai_bt` với bài cũ; chạy tương tự phần brain tumor, khác 4 điểm:

1. **Cách ly theo phiên/đề tài (workspace), không cần DB riêng.** Mỗi paper thuộc 1 user và 1 workspace; research/chat trong workspace chỉ truy xuất paper của workspace đó. Riêng admin không chỉ định workspace thì thấy MỌI paper (nên không chạy bằng admin mà không có workspace). Quy trình: đăng ký user, gán 50 paper vào workspace "Deepfake survey", gửi task kèm `workspace_id`. Người dùng thường upload qua `POST /papers/upload?workspace_id=<id>` thì paper đã thuộc đúng phiên.
2. PDF deepfake đặt tên theo tiêu đề (không phải UUID) nên lệnh kiểm tra đủ paper so khớp theo tên tệp (`file_path`), không theo `id`.
3. `UPLOAD_DIR=data/papers_deepfake` (mỗi đề tài một thư mục riêng; `catalog.json` và figures nằm theo `UPLOAD_DIR`).
4. Không có `catalog.json` (khóa theo `paper_id`, cấp lúc nạp nên không dựng trước được): reference của paper nội bộ suy ra từ nội dung PDF, cần rà tay DOI/tác giả với `_manifest.json` trước khi nộp.

**Chuẩn bị (một lần mỗi phiên):**
```bash
docker compose -p paperai_bt up -d postgres qdrant redis
docker exec paperai_bt-redis-1 redis-cli llen research_queue   # phải = 0
docker exec paperai_bt-redis-1 redis-cli exists unacked        # phải = 0
alembic upgrade head   # lần đầu sau khi cập nhật: áp migration 0009 (bảng workspaces) — bạn tự chạy trên DB của mình
```
Sau khi API (Terminal 1) và worker (Terminal 2) đã chạy và nạp xong PDF, tạo user riêng rồi gán paper:
```bash
set -a; . ./.env; set +a
curl -s localhost:8000/auth/register -H 'content-type: application/json' \
  -d '{"email":"deepfake@example.com","password":"<mật-khẩu-mạnh>","full_name":"Deepfake survey"}' | jq -c '{email:.user.email}'
source venv/bin/activate
python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake survey"            # dry-run: liệt kê
python scripts/assign_papers.py --dir data/papers_deepfake --email deepfake@example.com --workspace "Deepfake survey" --apply    # ghi user_id + workspace_id (tạo workspace nếu chưa có)
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"email":"deepfake@example.com","password":"<mật-khẩu-mạnh>"}' | jq -r '.access_token // .token')   # token của USER, không dùng admin
WS=$(curl -s localhost:8000/workspaces -H "authorization: Bearer $TOKEN" | jq -r '.[] | select(.name=="Deepfake survey") | .id'); echo "workspace: $WS"
```

**Kiểm tra đủ paper (bắt buộc, chạy sau khi API đã nạp PDF):** lệnh chỉ đọc, thoát mã `1` nếu còn thiếu:
```bash
python -c "import pathlib,sys; from app.core.database import SessionLocal; from app.api.models.paper import Paper; names={p.name for p in pathlib.Path('data/papers_deepfake').glob('*.pdf')}; db=SessionLocal(); done={pathlib.Path(fp).name for fp,s in db.query(Paper.file_path,Paper.status).all() if s=='done'}; db.close(); miss=names-done; print(f'PDF {len(names)} | done {len(names&done)} | thieu {len(miss)}'); [print(' -',m) for m in sorted(miss)]; sys.exit(1 if miss else 0)" && echo "OK: đủ paper, có thể chạy research"
```
Phải in `PDF 50 | done 50 | thieu 0`. Paper `pending`/`processing` mãi nghĩa là chưa có worker `upload_queue` chạy (Terminal 2) hoặc worker đã bị tắt giữa chừng; chạy lại worker rồi `process_paper.delay(<id>)` cho paper kẹt.

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
cat > /tmp/req_df.json <<'JSON'
{"question":"How do foundation models (large vision-language models, audio-visual and speech self-supervised encoders, and multimodal LLMs) support multimodal deepfake detection across visual, audio, and text/semantic modalities, and how do architectural choices and cross-modal learning mechanisms affect detection accuracy, cross-dataset and cross-generator generalization, and robustness to compression, noise, adversarial attacks, and unseen manipulation types? What are the trade-offs among architectures, adaptation strategies, and fusion mechanisms in terms of accuracy, robustness, computational cost, and explainability, and which open challenges remain?",
 "audience":"lecturer","field":"computer_vision","contribution_type":"survey",
 "target_venue":"Journal paper (8-12 pages)",
 "clarification_answers":{
  "What is the primary goal or output of this research report?":"A critical literature survey of foundation-model-based multimodal deepfake detection. Synthesize reported experimental evidence, compare architectures and cross-modal learning strategies, identify methodological limitations, and derive evidence-supported open challenges. Use reported results from original studies only; do not invent, estimate, or infer missing numerical results. Describe the review scope accurately as a survey of the provided corpus; do not call it a systematic review unless a database search and screening were actually performed.",
  "Which modalities and manipulation types are in scope?":"Visual (image, video, face), audio (speech, voice cloning/TTS), and text or semantic/captioning cues, including audio-visual consistency (lip-sync, identity) and image-text consistency. Cover face swap, face reenactment, attribute editing, fully synthetic images from GANs and diffusion models, and synthetic or cloned speech. State clearly which modalities each reviewed method actually uses; do not assume a method is multimodal unless the paper says so.",
  "Which foundation-model families and architectural aspects should be emphasized?":"Vision-language models (CLIP-style and prompt-tuned VLMs), vision transformers and self-supervised encoders, audio and speech self-supervised models, and multimodal large language models. Emphasize frozen versus fine-tuned backbones, parameter-efficient adaptation (prompt tuning, adapters, LoRA), fusion location and mechanism (early, late, cross-attention), and cross-modal alignment or consistency learning. Discuss only what the reviewed studies support.",
  "Which robustness and generalization scenarios should be analyzed?":"Cross-dataset and cross-generator (unseen manipulation) generalization, robustness to compression and post-processing, noise, adversarial attacks and purification, and missing or corrupted modalities where reported. Distinguish in-domain evaluation from cross-domain evaluation, and methods evaluated on a single benchmark from those evaluated on several. Do not assume every family has evidence for every scenario in the corpus.",
  "How should reported experimental results be compared?":"Use only numerical results explicitly reported in original papers. Record dataset (for example FaceForensics++, Celeb-DF, DFDC, DFDCP, WildDeepfake, FakeAVCeleb, DF-Platter), train/test protocol, in-domain versus cross-domain setting, metric (AUC, ACC, EER, F1, AP), compression level, and reported uncertainty where available. Do not directly rank or quantitatively compare studies with incompatible datasets, splits, or protocols. Preserve original metric scales and units (ratio vs percentage) and mark unavailable information as NR. Distinguish Reported, Not reported (NR) and Not retrieved; never treat Not retrieved as evidence of absence. Group quantitative evidence by dataset, protocol, metric and modality configuration. Every numerical, comparative and factual claim must trace to an identifiable source in the corpus; never invent authors, titles, venues, DOIs or corpus statistics.",
  "Which analytical dimensions should guide the comparison?":"Compare methods across four dimensions: detection accuracy, generalization and robustness, computational efficiency, and explainability or trustworthiness. Discuss computational cost only when supported by reported parameters, FLOPs, memory, or inference time. Discuss trustworthiness in terms of calibration, interpretability, fairness across demographics, and failure analysis when evidence is available.",
  "What are the expected scientific contributions of the survey?":"Develop an evidence-based analytical framework connecting foundation-model architectures, cross-modal learning mechanisms, and evaluation protocols. Compare strengths and limitations, identify gaps in experimental evaluation (benchmark leakage, protocol inconsistency, limited audio-text coverage), and formulate specific future directions. Keep three kinds of content separate: findings supported by the original papers, evidence gaps where the corpus lacks data, and research proposals by the authors. Classify methods with a multi-label, multi-axis taxonomy (modalities, backbone, adaptation strategy, fusion location, cross-modal learning objective, evaluation coverage) instead of forcing one category per paper. For every open challenge give the observed findings, the specific missing evidence, why it matters, and a concrete future direction; never present a proposed direction as an experimentally demonstrated conclusion. Quantitative figures must be reproducible from extracted evidence; label conceptual diagrams as author-designed. Conclusions must not exceed the strength of the evidence.",
  "What is the intended audience and approximate length of the final report?":"Researchers in multimedia forensics, computer vision, speech processing, and trustworthy AI. Target an 8-12 page journal manuscript with sufficient technical depth, critical comparison, concise evidence tables, and a clearly stated review methodology; length must not limit the analysis."}}
JSON
jq --arg ws "$WS" '. + {workspace_id: $ws}' /tmp/req_df.json > /tmp/req_df_ws.json   # gắn task vào phiên Deepfake
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
curl -s -H "authorization: Bearer $TOKEN" "localhost:8000/research/<task_id>/pdf?draft=true" -o survey_deepfake.pdf
```

**Checklist chuẩn nộp Q1/Q2 (đối chiếu trước khi nộp):**
- Tên là "survey of the provided corpus" (50 paper, nguồn OpenAlex open access), KHÔNG gọi là systematic review. Muốn gọi systematic review thì tự làm: tìm CSDL (Scopus/WoS/IEEE/arXiv), chuỗi truy vấn, tiêu chí gộp/loại, sơ đồ PRISMA, 2 reviewer độc lập.
- `validation/<task_id>.json`: `passed = true`, `blocking` rỗng, không còn UNTRACED/NO_CITATION; mọi con số trong bảng truy được về paper.
- Không so xếp hạng giữa các paper khác dataset/giao thức; giữ nguyên thang gốc (%, tỉ lệ); ô thiếu ghi NR.
- Rà tay References với `_manifest.json` (DOI, năm, tác giả), vì không có `catalog.json`.
- Đối chiếu tính mới với các survey deepfake đã xuất bản (hệ thống không tự kiểm tra được).
- Corpus 50 paper là nhỏ: nêu rõ giới hạn phạm vi ở phần Methodology/Limitations; mở rộng corpus là việc của bạn.

### Dừng và dọn
```bash
ps -eo pid,args | grep -E "[c]elery -A|[u]vicorn app"   # lấy PID rồi: kill <pid>  (KHÔNG dùng pkill -f)
docker compose -p paperai_bt stop                        # giữ nguyên dữ liệu
docker exec paperai_bt-redis-1 redis-cli del unacked unacked_index   # hủy task treo
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "delete from research_tasks where id='<task_id>'"
```
