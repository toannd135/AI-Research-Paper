# Task: Hoàn thiện luồng RAG (paperai)

Cập nhật: 2026-09-21

## Mục tiêu
Hoàn thiện luồng RAG end-to-end: upload PDF → parse → chunk → embed → lưu Qdrant → hybrid retrieval (BM25 + vector) → rerank → build context → **Gemini API** sinh câu trả lời kèm citation, expose qua FastAPI.
Ngoài phạm vi: `app/agent/**` (LangGraph research agent nhiều bước), `app/api/routes/research.py`, `app/api/routes/users.py`, `scripts/seed.py`.

## Đã hoàn thành (code, theo phase)

**Phase 1 — Core contracts**
- `app/core/config.py` — `Settings` (pydantic-settings) đọc `.env`.
- `app/core/schemas.py` — `Chunk`, `ScoredChunk`, `Citation`, `ResearchPayload`, `PaperStatus`, request/response schema cho API.
- `app/core/database.py` — SQLAlchemy engine/session/`Base`.

**Phase 2 — Ingestion pipeline**
- `app/pipeline/parser/pdf_parser.py` — trích text theo trang bằng `pymupdf`.
- `app/pipeline/parser/section_detector.py` — nhận diện heading (numbered + tên section phổ biến).
- `app/pipeline/chunking/simple_chunker.py` — sliding window cố định.
- `app/pipeline/chunking/semantic_chunker.py` — gộp theo đoạn văn + gắn section.
- `app/pipeline/vector_store/qdrant_client.py` — insert/delete/search Qdrant.
- `app/workers/celery_app.py` — cấu hình queue `upload_queue`/`research_queue`.
- `app/pipeline/tasks.py` — task `process_paper()` (parse→chunk→embed→lưu Qdrant→cập nhật status); `run_research()` để `NotImplementedError` (out of scope).

**Phase 3 — Retrieval + embedding**
- `app/ai/embedding/service.py` + `cache.py` — `embed_batch()` bằng `sentence-transformers` (BGE-M3), cache theo hash content.
- `app/ai/retrieval/vector_search.py`, `bm25_search.py`, `hybrid.py` (alpha/beta từ config), `reranker.py` (cross-encoder).
- `app/ai/context_builder.py` — dedup, sort, cắt theo `CONTEXT_TOKEN_LIMIT`, gắn citation.

**Phase 4 — Generation (Gemini) + API**
- `app/ai/llm_gateway/base.py` — interface `generate()` + `LLMGatewayError`.
- `app/ai/llm_gateway/gemini_adapter.py` — implement bằng SDK `google-genai`.
- `app/api/models/paper.py`, `conversation.py` — ORM `Paper`, `Conversation`, `Message`.
- `app/api/routes/papers.py` (`POST /papers/upload`, `GET /papers/{id}`), `chat.py` (`POST /chat`, `GET /conversations[/{id}]`).
- `app/main.py` — mount router.
- `alembic.ini`, `migrations/env.py`, `migrations/script.py.mako`, `migrations/versions/0001_initial_schema.py` (viết tay, đã verify chạy được).
- `requirements.txt`: +1 dòng `google-genai`.

**Phase 5 — Test**
- 6 file test: `app/pipeline/tests/test_chunking.py`, `test_section_detector.py`, `app/ai/tests/test_hybrid.py`, `test_context_builder.py`, `test_gemini_adapter.py`, `app/api/tests/test_models.py`.
- **24/24 pass** với dependency thật (`venv/bin/pytest`).

## Bug phát hiện khi chạy thật (không thấy được nếu chỉ đọc code) — đã sửa
1. Model `gemini-2.5-flash` bị Google retire → đổi `DEFAULT_MODEL` sang `gemini-3.6-flash` (xác nhận qua lỗi 404 thật từ API).
2. `QdrantClient.search()` đã bị xoá ở `qdrant-client` 1.19.1 → đổi sang `query_points()` trong `qdrant_client.py`.
3. `import fitz` (PyMuPDF) deprecated → đổi `import pymupdf`.
4. Test `test_missing_api_key_raises_gateway_error` flaky vì `.env` có key thật → sửa test để mock `get_settings()`.
5. Cổng `5432` (Postgres) và `6379` (Redis) trên host bị chiếm bởi service khác không liên quan tới project → đổi port map trong `docker-compose.yml` (`5433:5432`, `6380:6379`) và cập nhật `DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL`/`CELERY_RESULT_BACKEND` trong `.env` theo port mới. Không đụng vào service lạ trên host.
6. `torch.OutOfMemoryError: CUDA out of memory` khi gọi `/chat`: máy dev chỉ có GPU 5.67GB VRAM, worker đã chiếm ~2.3GB cho BGE-M3, API load thêm reranker (cross-encoder) vào GPU thì tràn bộ nhớ → ép cả `embedding/service.py` và `retrieval/reranker.py` load model với `device="cpu"` để không phụ thuộc VRAM còn trống (đánh đổi tốc độ lấy độ ổn định, hợp lý cho quy mô nhỏ hiện tại).

## Đã verify thật (không chỉ mock) — FULL END-TO-END PASS
- `pytest`: 24/24 pass.
- FastAPI app import sạch, đủ 6 route (verify qua `TestClient` + OpenAPI schema).
- Alembic: chạy thật cả trên SQLite tạm lẫn Postgres thật (`docker compose` + `alembic upgrade head`) → tạo đúng bảng `papers`, `conversations`, `messages`.
- `docker compose up -d postgres qdrant redis` chạy được (sau khi đổi port) — cả 3 container `Up`.
- API (`uvicorn`) và Celery worker khởi động thành công, worker connect Redis OK, nhận đúng 2 task.
- `POST /papers/upload` với 1 PDF mẫu tự tạo (2 trang, có heading "1. Introduction"/"2. Method") → `status: pending` → worker parse/chunk/embed (BGE-M3) → `status: done`.
- Qdrant collection `paper_chunks` có đúng 2 point (vector size 1024, khớp BGE-M3) sau khi xử lý.
- **`POST /chat` trả HTTP 200, gọi Gemini API thật (`gemini-3.6-flash`)**, trả lời đúng nội dung: *"Phương pháp hybrid retrieval trong bài báo này kết hợp BM25 và các vector dày (dense vectors) [1]."*, kèm 2 `citations` trỏ đúng `page: 1 / section: "1. Introduction"` và `page: 2 / section: "2. Method"` — khớp 100% nội dung PDF mẫu.

## Toàn bộ checklist ban đầu đã hoàn thành
- [x] Upload PDF → parse → chunk → embed → lưu Qdrant.
- [x] Hybrid retrieval (BM25 + vector) + rerank hoạt động đúng.
- [x] `/chat` trả lời kèm citation chính xác (paper_id/page/section).
- [x] Migration Alembic chạy được trên Postgres thật.
- [x] Gemini API tích hợp và hoạt động thật.

## Phase 6 — Research agent (app/agent, /research) — HOÀN THÀNH

Trước đây `app/agent/**`, `app/api/routes/research.py`, `app/api/models/research_task.py` chỉ là docstring 1 dòng, out of scope theo checklist ban đầu. Đã implement đầy đủ theo yêu cầu: client gửi 1 câu hỏi → hệ thống tự hỏi lại nếu thiếu thông tin → tự tìm tất cả đoạn/paper liên quan trong TOÀN BỘ kho đã ingest (không giới hạn 1 paper như `/chat`) → tự phản biện (citation + hallucination check) → viết báo cáo hoàn chỉnh. Chi tiết kiến trúc xem `instruction.md` mục 2b.

**Đã tạo/sửa:**
- `app/core/schemas.py` — `ResearchStatus`, `ResearchRequest`, `ResearchClarificationResponse`, `ResearchTaskResponse`.
- `app/api/models/research_task.py` — ORM `ResearchTask`; `migrations/versions/0002_research_tasks.py`.
- `app/agent/clarify.py`, `state.py`, `json_utils.py` — bước hỏi-lại đồng bộ + state chung + parse JSON từ LLM.
- `app/agent/nodes/{plan,search,analyze,critique,synthesize}_node.py`, `app/agent/tools/{search_papers,retrieve_evidence}.py`, `app/agent/evidence/{citation_validator,hallucination_detector}.py`, `app/agent/graph.py` (`run_graph()`, `MAX_ITERATIONS=2`).
- `app/pipeline/tasks.py` — implement `run_research()` (trước đây `NotImplementedError`).
- `app/api/routes/research.py` (`POST /research`, `GET /research/{id}`), mount vào `app/main.py`.
- `app/agent/evaluation/metrics.py`, `run_benchmark.py` — implement (chưa có gold data thật nên `questions.json` vẫn để `[]`).
- Test mới: `app/agent/tests/` (6 file, mock LLM bằng `unittest.mock`), `app/api/tests/test_research_task_model.py`, `test_research_route.py` (mock `clarify()` + Celery `.delay()`, DB SQLite in-memory qua `StaticPool` — cần vì FastAPI `TestClient` chạy request khác thread, SQLite `:memory:` mặc định không share giữa các thread).

**Đã verify thật:**
- `venv/bin/pytest -q`: **45/45 pass** (24 cũ + 21 mới), không gọi Gemini/Qdrant thật.
- `venv/bin/alembic upgrade head` chạy trên Postgres thật → verify bảng `research_tasks` đúng 9 cột qua `psql \d`.
- OpenAPI schema (`/openapi.json` qua `TestClient`) show đúng `/research/` (POST) và `/research/{task_id}` (GET).
- Restart API + worker với code mới, gọi thật `POST /research` — request đi đúng đường: vào `clarify()` → gọi `GeminiAdapter.generate()` với model `gemini-3.6-flash` → **Gemini trả 503 "high demand"** (lỗi tạm thời từ phía Google, không phải lỗi code) → `LLMGatewayError` được raise và propagate đúng thành HTTP 500. Đã thử 3 lần trong vài phút, cùng lỗi 503 — dừng thử thêm để không tốn quota. **Chưa verify được 1 lượt full end-to-end thành công (report thật) do Gemini đang quá tải tại thời điểm code** — nên thử lại `POST /research` khi Gemini ổn định, hoặc dùng lúc rảnh để confirm nốt.

## Việc còn lại (không chặn "luồng RAG hoạt động", chỉ là dọn dẹp/tối ưu)
- [ ] Dọn dữ liệu demo: paper test `49cf4009-f089-4f52-9907-2c5a5b5917d0` trong Postgres + 2 point trong Qdrant collection `paper_chunks` (dữ liệu test, không phải dữ liệu thật).
- [ ] Cân nhắc đưa `device` (cpu/cuda) cho embedding/reranker thành config thay vì hardcode "cpu", nếu sau này chạy trên máy có GPU dư VRAM riêng cho RAG (hiện tại hardcode CPU là lựa chọn an toàn, không phải giới hạn kỹ thuật).
- [ ] BM25 index build lại từ Qdrant mỗi query (đã note từ đầu) — chỉ phù hợp quy mô nhỏ, cần đổi sang index persistent nếu scale lớn.
- [ ] Dừng process API/worker chạy nền (PID xem bên dưới) khi không cần nữa: `kill $(pgrep -f "uvicorn app.main:app") $(pgrep -f "celery -A app.workers.celery_app")`.

## Trạng thái hạ tầng hiện tại (local, để tiếp tục ngay)
- `docker compose up -d postgres qdrant redis` — 3 container đang chạy, port đã đổi: Postgres `5433:5432`, Qdrant `6333-6334` (giữ nguyên), Redis `6380:6379`.
- Migration đã chạy tới `0002` (`research_tasks` đã có trên Postgres thật).
- API: `uvicorn app.main:app --host 0.0.0.0 --port 8000` chạy nền (đã restart để load code Phase 6), log: `/tmp/paperai_api.log`.
- Worker: `celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info` chạy nền (đã restart), log: `/tmp/paperai_worker.log`.
- Paper test đã xử lý xong: id `49cf4009-f089-4f52-9907-2c5a5b5917d0`, file gốc `/tmp/sample_paper.pdf`, `status: done`, 2 chunk trong Qdrant.
- Đã test `/chat` thành công, response mẫu lưu ở `/tmp/chat_resp2.json`.
- Đã gọi thật `POST /research` 3 lần — Gemini trả 503 cả 3 lần (xem Phase 6), chưa có `ResearchTask` nào ở trạng thái `done` trong DB.

## Lệnh để tự chạy lại từ đầu
```bash
docker compose up -d postgres qdrant redis
venv/bin/alembic upgrade head
venv/bin/uvicorn app.main:app --reload &
venv/bin/celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info &

curl -X POST http://localhost:8000/papers/upload -F "file=@/path/to/paper.pdf;type=application/pdf"
curl http://localhost:8000/papers/{id}
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"question": "..."}'

curl -X POST http://localhost:8000/research/ -H "Content-Type: application/json" \
  -d '{"question": "..."}'
curl http://localhost:8000/research/{id}
```

## Ngoài phạm vi (chủ đích, không đụng vào)
`app/api/routes/users.py`, `app/ai/llm_gateway/anthropic_adapter.py` / `openai_adapter.py` / `vllm_adapter.py` (giữ nguyên dạng stub), `scripts/seed.py`. `app/agent/**`/`app/api/routes/research.py`/`app/api/models/research_task.py` đã implement xong ở Phase 6, không còn ngoài phạm vi.
