# Hướng dẫn đọc code — paperai

Tài liệu này dành cho người mới join, giúp hiểu dự án làm gì, luồng dữ liệu đi qua đâu, và nên đọc code theo thứ tự nào. Đọc xong tài liệu này trước khi mở code.

## 1. Dự án này làm gì

`paperai` là trợ lý nghiên cứu khoa học, có 2 luồng chính:

1. **RAG hỏi-đáp 1 paper** (`/papers/upload`, `/chat`): người dùng **upload 1 file PDF**, hệ thống tự đọc/tách nội dung, rồi cho phép **hỏi đáp dựa trên nội dung paper đó**, câu trả lời luôn **kèm trích dẫn (citation)** trỏ về đúng đoạn/trang trong PDF gốc — đây là kỹ thuật **RAG (Retrieval-Augmented Generation)**: thay vì để LLM "bịa" câu trả lời từ trí nhớ, hệ thống đi tìm đoạn văn bản liên quan trong paper trước, rồi mới đưa LLM đọc và trả lời dựa trên đúng đoạn đó.
2. **Research agent nhiều bước, quét toàn bộ kho paper** (`/research`): người dùng gửi 1 câu hỏi nghiên cứu (không cần chỉ định 1 paper cụ thể). Hệ thống **tự suy luận xem câu hỏi có đủ rõ chưa, nếu thiếu thì hỏi lại** (tối đa 1 vòng), sau đó **tự tìm tất cả các đoạn/paper liên quan trong toàn bộ kho đã ingest**, tự phản biện (kiểm tra trích dẫn + phát hiện câu bịa) trước khi chốt, rồi **viết ra 1 báo cáo hoàn chỉnh** kèm danh sách trích dẫn kiểm chứng được. Đây là 1 agent LangGraph nhiều node, chạy nền qua Celery (giống cơ chế xử lý PDF ở luồng 1). Đọc phần 2b và 3b bên dưới để hiểu chi tiết.

## 2. Luồng dữ liệu tổng quan

```
[Upload PDF]
     │  POST /papers/upload
     ▼
[Celery task: process_paper]
     │
     ├─ 1. Parse PDF -> lấy text từng trang            (app/pipeline/parser)
     ├─ 2. Chunking -> cắt text thành đoạn nhỏ          (app/pipeline/chunking)
     ├─ 3. Embedding -> đoạn text -> vector số          (app/ai/embedding)
     └─ 4. Lưu vector + text vào Qdrant                 (app/pipeline/vector_store)
     ▼
[Paper.status = done]


[User hỏi]
     │  POST /chat  {"question": "..."}
     ▼
[1. Hybrid retrieval]  BM25 (từ khoá) + vector (ngữ nghĩa), gộp theo alpha/beta
     (app/ai/retrieval/bm25_search.py, vector_search.py, hybrid.py)
     ▼
[2. Rerank]  cross-encoder chấm điểm lại chính xác hơn, lấy top-k tốt nhất
     (app/ai/retrieval/reranker.py)
     ▼
[3. Build context]  dedup, sort, cắt theo giới hạn token, gắn số trích dẫn [1][2]...
     (app/ai/context_builder.py)
     ▼
[4. Gọi LLM]  đưa context + câu hỏi cho Gemini, LLM trả lời DỰA TRÊN context
     (app/ai/llm_gateway/gemini_adapter.py)
     ▼
[Trả về answer + citations cho user]
```

**Nguyên tắc cốt lõi cần nhớ:** LLM không bao giờ được hỏi trực tiếp câu hỏi của user. Nó luôn được đưa kèm "context" (các đoạn text lấy từ chính paper) và được yêu cầu chỉ trả lời dựa trên context đó, kèm trích dẫn số `[n]` tương ứng với từng đoạn. Đọc `_SYSTEM_PROMPT` trong `app/api/routes/chat.py` để thấy rõ nguyên tắc này được ép vào prompt như thế nào.

## 2b. Luồng research agent (`/research`) — chi tiết

```
[User gửi câu hỏi nghiên cứu]
     │  POST /research  {"question": "...", "clarification_answers": null}
     ▼
[app/agent/clarify.py]   1 lệnh LLM ĐỒNG BỘ ngay trong request (không qua Celery)
     │
     ├─ thiếu thông tin & client CHƯA gửi clarification_answers
     │      → trả ngay {status: "needs_clarification", questions: [...]}
     │        KHÔNG tạo row DB, KHÔNG động vào Celery.
     │        Client gọi lại POST /research lần 2, kèm clarification_answers
     │        (hệ thống CHỈ hỏi lại tối đa 1 vòng — lần 2 luôn tiến hành, tự chọn
     │        giả định hợp lý nếu vẫn còn thiếu, để tránh hỏi vô hạn)
     │
     └─ đủ thông tin → tạo ResearchTask(status=pending) trong DB,
                        gọi run_research.delay(task_id), trả {id, status: "pending"}
     ▼
[Client poll GET /research/{id}] cho tới khi status = "done" (hoặc "failed")


--- bên trong Celery worker, queue "research_queue" ---
[app/pipeline/tasks.py -> run_research(task_id)]
     │  load ResearchTask, set status=processing, gọi app/agent/graph.py::run_graph()
     ▼
[app/agent/graph.py — LangGraph StateGraph]

  plan_node       (app/agent/nodes/plan_node.py)
     │   LLM: từ câu hỏi đã refine -> sinh 3-5 search sub-query (bao quát nhiều khía cạnh)
     ▼
  search_node     (app/agent/nodes/search_node.py)
     │   gọi app/agent/tools/retrieve_evidence.py -> lặp app/agent/tools/search_papers.py
     │   cho từng sub-query. search_papers() bọc search_hybrid()+rerank() CÓ SẴN ở
     │   app/ai/retrieval/, nhưng gọi KHÔNG truyền paper_id => quét TOÀN BỘ kho paper
     │   đã ingest, không giới hạn 1 paper như /chat. Kết quả gộp + dedup theo chunk.id.
     ▼
  analyze_node    (app/agent/nodes/analyze_node.py)
     │   build_context() (tái dùng từ /chat) ghép evidence thành context có [n],
     │   LLM viết 1 draft có trích dẫn [n] dựa trên context đó.
     ▼
  critique_node   (app/agent/nodes/critique_node.py) — "tự phản biện"
     │   1. citation_validator.py: marker [n] trong draft có khớp danh sách citations không?
     │   2. hallucination_detector.py: LLM-judge so draft với evidence, tìm câu KHÔNG có
     │      nguồn hỗ trợ (câu bịa/suy diễn quá đà).
     │
     ├─ có lỗi & chưa quá MAX_ITERATIONS (=2) ──► quay lại analyze_node, viết lại có kèm feedback
     └─ hết lỗi (hoặc đã hết số lần thử) ────────► synthesize_node
                                                          │
                                                          ▼
                                            synthesize_node (app/agent/nodes/synthesize_node.py)
                                            LLM cuối: ép draft đã kiểm chứng vào cấu trúc cố định
                                            (Tiêu đề/Tóm tắt/Giới thiệu/Tổng quan tài liệu/
                                            Thảo luận/Kết luận/Tài liệu tham khảo), CHỈ dùng
                                            citation đã có, không thêm trích dẫn mới.
     ▼
run_research lưu report + citations (JSON) vào ResearchTask, set status=done
(hoặc status=failed + error nếu exception — y hệt cách process_paper cập nhật Paper.status).
```

**Khác biệt quan trọng so với `/chat`:** `/chat` trả lời dựa trên **1 paper** (`paper_id` filter), 1 lần gọi LLM, đồng bộ. `/research` quét **toàn bộ kho paper**, chạy nhiều bước bất đồng bộ qua Celery, và có vòng lặp tự phản biện trước khi chốt câu trả lời — vì output là cả 1 báo cáo dài chứ không phải 1 câu trả lời ngắn, rủi ro bịa trích dẫn cao hơn nên cần bước kiểm chứng riêng.

**File đánh giá chất lượng (không nằm trong luồng chính, chạy tay khi cần):** `app/agent/evaluation/run_benchmark.py` chạy `run_graph()` trực tiếp (không qua Celery) trên các câu hỏi khai báo trong `app/agent/evaluation/questions.json`, in ra `recall@K` và `citation_faithfulness` (định nghĩa ở `metrics.py`). `questions.json` hiện để trống — điền câu hỏi + `relevant_chunk_ids` (optional) vào đó sau khi đã có paper thật đã ingest để làm gold data.

## 3. Cấu trúc thư mục — module nào làm việc gì

| Thư mục | Vai trò | File chính |
|---|---|---|
| `app/core/` | Contract dùng chung toàn dự án | `config.py` (đọc `.env`), `schemas.py` (định nghĩa `Chunk`, `Citation`...), `database.py` (SQLAlchemy) |
| `app/pipeline/parser/` | Đọc PDF ra text thuần | `pdf_parser.py` (PyMuPDF), `section_detector.py` (nhận diện heading "1. Introduction"...) |
| `app/pipeline/chunking/` | Cắt text dài thành đoạn nhỏ để embed | `simple_chunker.py` (cắt cố định), `semantic_chunker.py` (cắt theo đoạn văn + gắn section) |
| `app/pipeline/vector_store/` | Giao tiếp với Qdrant (vector DB) | `qdrant_client.py` |
| `app/pipeline/tasks.py` | Task Celery chạy nền: `process_paper()` nối 4 bước ingest lại với nhau | — |
| `app/workers/celery_app.py` | Cấu hình Celery (queue, broker) | — |
| `app/ai/embedding/` | Text → vector số | `service.py` (`embed_batch()`, model BGE-M3), `cache.py` (cache theo hash) |
| `app/ai/retrieval/` | Tìm đoạn liên quan tới câu hỏi | `bm25_search.py`, `vector_search.py`, `hybrid.py` (gộp 2 cái trên), `reranker.py` (lọc lại lần 2) |
| `app/ai/context_builder.py` | Ghép các đoạn tìm được thành 1 khối "context" đưa cho LLM | — |
| `app/ai/llm_gateway/` | Giao tiếp với LLM | `base.py` (interface chung), `gemini_adapter.py` (implementation đang dùng) |
| `app/api/models/` | ORM (bảng DB) | `paper.py`, `conversation.py` |
| `app/api/routes/` | Endpoint FastAPI | `papers.py` (upload), `chat.py` (hỏi đáp 1 paper), `research.py` (research agent nhiều bước) |
| `app/main.py` | Điểm khởi động app, mount router | — |
| `migrations/` | Alembic — quản lý thay đổi schema DB | `versions/0001_initial_schema.py`, `0002_research_tasks.py` |
| `app/agent/clarify.py` | Bước hỏi-lại-nếu-thiếu-info, chạy đồng bộ trước khi vào graph | — |
| `app/agent/state.py` | `ResearchState` — state (TypedDict) dùng chung xuyên suốt graph | — |
| `app/agent/graph.py` | Ghép các node thành LangGraph `StateGraph`, export `run_graph()` | — |
| `app/agent/nodes/` | 5 bước của agent: `plan_node` (sinh sub-query) → `search_node` (gọi tool tìm evidence) → `analyze_node` (LLM viết draft có `[n]`) → `critique_node` (tự kiểm) → `synthesize_node` (LLM viết báo cáo cuối) | — |
| `app/agent/tools/` | Tool agent dùng: `search_papers.py` (bọc hybrid search + rerank, quét toàn kho), `retrieve_evidence.py` (chạy nhiều sub-query rồi dedup) | — |
| `app/agent/evidence/` | Kiểm chứng chất lượng draft: `citation_validator.py` (marker `[n]` có khớp citations không), `hallucination_detector.py` (LLM-judge tìm câu không có evidence hỗ trợ) | — |
| `app/agent/evaluation/` | Benchmark ngoài luồng chính: `metrics.py` (recall@K, faithfulness), `run_benchmark.py`, `questions.json` (đang rỗng) | — |
| `app/api/models/research_task.py` | ORM `ResearchTask` — 1 row / 1 câu hỏi nghiên cứu, poll qua `status` | — |

**Không thuộc phạm vi hiện tại (để nguyên dạng chưa implement — không sửa nếu chưa hỏi):**
`app/api/routes/users.py`, `app/ai/llm_gateway/anthropic_adapter.py` / `openai_adapter.py` / `vllm_adapter.py`, `scripts/seed.py`. `app/agent/**` **đã implement xong** (xem mục 2b) — vẫn nên hỏi trước khi đổi kiến trúc graph, nhưng không còn là "chưa cần đọc".

## 4. Thứ tự nên đọc code (gợi ý cho người mới)

1. **`app/core/schemas.py`** — đọc trước tiên. Đây là "ngôn ngữ chung" của cả hệ thống: `Chunk`, `ScoredChunk`, `Citation` xuất hiện xuyên suốt mọi module.
2. **`app/pipeline/parser/pdf_parser.py`** → **`chunking/simple_chunker.py`** — đơn giản nhất, dễ hình dung nhất: PDF → text → list các đoạn nhỏ.
3. **`app/pipeline/tasks.py`** (hàm `process_paper`) — thấy toàn bộ luồng ingest được nối lại ra sao (gọi lần lượt các hàm ở bước 2).
4. **`app/ai/retrieval/hybrid.py`** — đọc kỹ hàm `search_hybrid()`, đây là "trái tim" của retrieval: cách 2 điểm số (BM25 + vector) được chuẩn hoá rồi cộng theo alpha/beta.
5. **`app/ai/context_builder.py`** — cách các đoạn được chọn/cắt/đánh số trích dẫn trước khi đưa cho LLM.
6. **`app/api/routes/chat.py`** — nơi TẤT CẢ các bước ở trên được gọi tuần tự trong 1 request: retrieval → rerank → build context → gọi Gemini → lưu conversation. Đọc file này xong là hiểu được toàn bộ luồng `/chat`.
7. **`app/ai/llm_gateway/base.py` + `gemini_adapter.py`** — cách LLM được trừu tượng hoá qua 1 interface chung (để sau này đổi provider khác không phải sửa `chat.py`).

Sau khi đọc xong 7 file trên theo đúng thứ tự, bạn sẽ hiểu được ~80% luồng chính của dự án (luồng `/chat`, 1 paper).

**Đọc tiếp nếu cần hiểu luồng `/research` (research agent nhiều bước):**

8. **`app/agent/graph.py`** — đọc trước để thấy toàn bộ graph được ghép ra sao (thứ tự node + điều kiện loop), rồi mới đọc từng node.
9. **`app/agent/nodes/analyze_node.py` → `critique_node.py`** — đọc cặp này cùng nhau: `analyze_node` viết draft có `[n]`, `critique_node` gọi `citation_validator.py` + `hallucination_detector.py` để kiểm lại — đây là phần khác biệt lớn nhất so với `/chat` (có bước tự kiểm trước khi trả kết quả).
10. **`app/api/routes/research.py`** — thấy cách bước "hỏi lại" (`app/agent/clarify.py`) chạy đồng bộ trước khi tạo `ResearchTask` + gọi Celery, khác với `process_paper` ở chỗ có thể trả kết quả ngay mà không tạo task nào.

## 5. Các khái niệm cần biết trước

- **RAG (Retrieval-Augmented Generation):** tìm dữ liệu liên quan trước, đưa cho LLM đọc, rồi mới để LLM trả lời — giảm "ảo giác" (hallucination) so với hỏi thẳng LLM.
- **Chunking:** paper dài không thể nhét hết vào 1 lần tìm kiếm/embedding, phải cắt thành đoạn nhỏ (chunk), mỗi đoạn embed riêng.
- **Embedding:** biến 1 đoạn text thành 1 vector số (ở đây là 1024 chiều, model BGE-M3), 2 đoạn có nghĩa gần nhau thì vector gần nhau trong không gian.
- **Hybrid retrieval:** kết hợp 2 cách tìm — BM25 (khớp từ khoá chính xác, tốt cho tên riêng/thuật ngữ) và vector search (khớp ngữ nghĩa, tốt khi người dùng hỏi khác từ ngữ trong paper). `HYBRID_ALPHA`/`HYBRID_BETA` trong `.env` quyết định trọng số mỗi bên.
- **Rerank:** sau khi hybrid retrieval trả về top-N ứng viên (nhanh nhưng thô), dùng 1 model cross-encoder chính xác hơn (nhưng chậm hơn) để chấm điểm lại và chỉ giữ top-k tốt nhất.
- **Citation:** mỗi đoạn context đưa cho LLM được gắn số `[1]`, `[2]`... kèm `paper_id`/`page`/`section`; LLM được yêu cầu trích dẫn đúng số đó trong câu trả lời, nên có thể truy ngược lại chính xác câu trả lời lấy từ đâu.

## 6. Setup & chạy thử

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt

cp .env.example .env   # rồi điền GEMINI_API_KEY (xin trong team, không commit key thật)

docker compose up -d postgres qdrant redis   # xem docker-compose.yml, port hiện tại: Postgres 5433, Redis 6380
venv/bin/alembic upgrade head

venv/bin/uvicorn app.main:app --reload &
venv/bin/celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info &
```

Test nhanh qua Swagger UI: mở **http://localhost:8000/docs**, thử `POST /papers/upload` (chọn 1 file PDF) → `GET /papers/{id}` (đợi `status: done`) → `POST /chat` (hỏi 1 câu liên quan tới nội dung PDF).

Test luồng research agent: `POST /research` với `{"question": "..."}` → nếu trả `status: needs_clarification`, gọi lại `POST /research` kèm `clarification_answers` (hoặc hỏi câu đủ rõ ngay từ đầu) → nhận `{id, status: "pending"}` → `GET /research/{id}` poll tới khi `status: "done"`, xem `report` + `citations`.

**Lưu ý lần chạy đầu tiên:** model embedding (BGE-M3) và reranker (BGE-reranker-v2-m3) sẽ tự tải từ HuggingFace (~2GB), có thể mất vài phút. Các model này được cấu hình chạy CPU (xem `app/ai/embedding/service.py`, `app/ai/retrieval/reranker.py`) để không phụ thuộc VRAM GPU.

## 7. Chạy test

```bash
venv/bin/pytest -q
```
Test nằm rải theo module: `app/pipeline/tests/`, `app/ai/tests/`, `app/api/tests/`, `app/agent/tests/` — mỗi module tự test phần logic của mình, không phụ thuộc DB/Qdrant/API key thật (dùng SQLite in-memory hoặc mock, xem `unittest.mock.patch` trong `app/agent/tests/*` và `app/api/tests/test_research_route.py` để biết cách mock LLM/Celery khi viết test mới).

## 8. Lưu ý khi sửa code

- `app/core/schemas.py` là contract dùng chung — đổi field ở đây ảnh hưởng nhiều module, sửa cẩn thận.
- Mọi provider (LLM, embedding...) nên đi qua interface chung (`base.py`) thay vì gọi thẳng SDK trong route/task — để dễ đổi provider sau này. Mọi node trong `app/agent/nodes/` nhận `llm: LLMGateway | None = None` để test dễ inject fake gateway, không hardcode `GeminiAdapter()` bên trong logic test được.
- Config (model name, alpha/beta, token limit...) lấy từ `app/core/config.py` (đọc `.env`), không hardcode giá trị trong code nghiệp vụ.
- Khi đổi schema DB: sửa ORM model trong `app/api/models/`, rồi tạo migration mới bằng `alembic revision --autogenerate -m "mô tả"`, không sửa tay migration cũ đã áp dụng.
- `app/agent/graph.py::MAX_ITERATIONS` (hiện = 2) giới hạn số lần `critique_node` được phép bắt `analyze_node` viết lại — đổi số này cần cân nhắc giữa chất lượng (viết lại nhiều hơn) và chi phí (nhiều lệnh gọi LLM hơn), không nên bỏ giới hạn này (tránh vòng lặp không dừng).
- Bước "hỏi lại" (`app/agent/clarify.py`) chỉ hỏi **tối đa 1 vòng** theo thiết kế — nếu cần hỏi nhiều vòng hơn, đây là thay đổi kiến trúc (cần thêm state lưu lịch sử hỏi-đáp), nên hỏi trước khi làm.
