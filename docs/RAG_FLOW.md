# Luồng RAG của PaperAI

Tài liệu này trace toàn bộ luồng RAG từ lúc upload PDF tới lúc trả lời câu hỏi: đi qua hàm nào, file nào.

## 1. Upload file (Ingestion)

**`app/api/routes/papers.py`** — `upload_paper()` (dòng 21)
- Nhận `UploadFile`, kiểm tra đuôi `.pdf`, lưu vào `data/papers/{paper_id}.pdf`
- Tạo record `Paper` (status=`PENDING`) trong DB
- Gọi `process_paper.delay(paper_id)` → đẩy task vào Celery queue `upload_queue`

> ⚠️ Lưu ý: ở frontend hiện tại (`src/admin/pages/PapersPage.tsx:35`), upload đang **mô phỏng** — chưa thật sự gọi `POST /papers/upload`.

## 2. Celery worker xử lý paper

**`app/pipeline/tasks.py`** → `process_paper(paper_id)` (dòng 12), set status `PROCESSING`, rồi chạy tuần tự:

### a) Parse PDF
`app/pipeline/parser/pdf_parser.py:14` `parse_pdf()`
Dùng `pymupdf` đọc từng trang → `list[PageText(page, text)]`

### b) Chunk
`app/pipeline/chunking/semantic_chunker.py:16` `chunk_pages()`
- Gọi `detect_sections()` / `assign_section()` trong `app/pipeline/parser/section_detector.py` để nhận diện heading (Abstract, Introduction, Method...) và gắn section gần nhất cho mỗi chunk
- Gộp đoạn văn liên tiếp tới ~800 ký tự (`DEFAULT_CHUNK_SIZE`), overlap 150 ký tự → trả về `list[Chunk]`

### c) Embed
`app/ai/embedding/service.py:18` `embed_batch()`
- Check cache theo hash SHA256(model+text) trong `app/ai/embedding/cache.py` (cache in-memory dict, không phải Redis)
- Text chưa có cache → load `SentenceTransformer` (model BGE-M3, chạy CPU) → `model.encode()`

### d) Lưu Qdrant
`app/pipeline/vector_store/qdrant_client.py`
- `ensure_collection()` (dòng 19) tạo collection nếu chưa có (distance=COSINE)
- `upsert_chunks()` (dòng 29) đẩy từng chunk + vector + payload (paper_id, text, page, section) vào Qdrant

→ set status `DONE`, hoặc `FAILED` + lưu `error` nếu exception.

## 3. Truy vấn / Chat (Retrieval + Generation)

**`app/api/routes/chat.py`** → `chat()` (dòng 25):

1. **`search_hybrid()`** — `app/ai/retrieval/hybrid.py:20`
   - **Vector search**: `app/ai/retrieval/vector_search.py` → `embed_query()` rồi `qdrant_client.search()` (cosine similarity)
   - **BM25 search**: `app/ai/retrieval/bm25_search.py` → scroll toàn bộ chunk từ Qdrant theo `paper_id`, build `BM25Okapi` tạm thời mỗi lần gọi, tính điểm keyword
   - Min-max normalize 2 tập điểm, kết hợp theo `hybrid_alpha`/`hybrid_beta` (config) → top 20 candidate

2. **Rerank** — `app/ai/retrieval/reranker.py:18` `rerank()`
   - Dùng `CrossEncoder` (BGE-Reranker) chấm điểm lại (query, chunk.text) → lấy top 6

3. **Build context** — `app/ai/context_builder.py:12` `build_context()`
   - Dedupe theo chunk id, sort theo score, cắt theo `context_token_limit` (ước lượng ~4 ký tự/token)
   - Sinh `context_text` có đánh số `[1] [2]...` + list `Citation` (paper_id, page, section, snippet)

4. **Generate** — `app/ai/llm_gateway/gemini_adapter.py` `GeminiAdapter.generate()`
   - Gửi system prompt (chỉ trả lời dựa trên context, trích dẫn `[n]`) + context + câu hỏi → Gemini

5. Lưu `Message` (user + assistant) vào `Conversation`, trả về `ChatResponse(answer, citations)`.

## 4. Luồng phụ: Deep Research Agent (agentic RAG)

`run_research()` trong `app/pipeline/tasks.py:50` chạy queue `research_queue` → gọi `app/agent/graph.py` `run_graph()`, một LangGraph pipeline qua các node: `plan_node` → `search_node` (dùng `tools/search_papers.py`, `tools/retrieve_evidence.py`) → `analyze_node` → `synthesize_node` → `critique_node`, có thêm `citation_validator.py` / `hallucination_detector.py` để kiểm tra citation trước khi trả report.

## Sơ đồ tóm tắt

```
Upload PDF → papers.py (upload_paper)
   → Celery: tasks.py (process_paper)
       → pdf_parser.parse_pdf
       → semantic_chunker.chunk_pages (+ section_detector)
       → embedding/service.embed_batch (+ cache)
       → qdrant_client.ensure_collection/upsert_chunks

Query → chat.py (chat)
   → retrieval/hybrid.search_hybrid
       → retrieval/vector_search.search_vector (embed_query + qdrant search)
       → retrieval/bm25_search.search_bm25
   → retrieval/reranker.rerank
   → context_builder.build_context
   → llm_gateway/gemini_adapter.GeminiAdapter.generate
```
