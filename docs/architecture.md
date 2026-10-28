# Kiến trúc

## Thành phần
| Khối | Công nghệ | Vai trò |
|---|---|---|
| API | FastAPI (`app/main.py`, `app/api/routes`) | auth, papers, research, chat, sources |
| Worker | Celery + Redis (`app/workers`, `app/pipeline/tasks.py`) | `process_paper` (upload_queue), `run_research` (research_queue; time limit 1h) |
| DB | PostgreSQL + SQLAlchemy + Alembic | users, papers, research_tasks, conversations, messages |
| Vector | Qdrant (`app/pipeline/vector_store`) | collection `paper_chunks` |
| AI | `app/ai` | bge-m3 embedding, BM25 + vector -> hybrid, bge-reranker, context builder, LLM gateway đa nhà cung cấp |
| Agent | LangGraph (`app/agent`) | research pipeline có citation |
| Export | `app/pipeline/export` | Chromium (mặc định), Typst, LaTeX, BibTeX |
| Frontend | React+TS+Vite+antd (`frontend/`, submodule) | admin, client, auth, home |

## Luồng 1: nạp paper
upload `POST /papers/upload` -> lưu file `data/papers` (hash chống trùng) -> Celery `process_paper` -> parse PDF (`pipeline/parser`) -> chunk (`pipeline/chunking`) -> embed -> Qdrant; trích hình (`pipeline/figures.py`). Trạng thái ở `papers.status`.

## Luồng 2: research agent (`app/agent/graph.py`)
```
plan -> search -> analyze -> critique --(thiếu evidence)--> analyze
                                  \--(đủ)--> model -> synthesize -> END
```
- plan: làm rõ câu hỏi, đoán field/audience/contribution_type (`clarify.py`, `profiles.py`, `research_model.py`).
- search: RAG nội bộ (`tools/search_papers`, `retrieve_evidence`) + OpenAlex (`tools/search_external_papers`, lọc miền theo field).
- analyze/critique: trích finding, chấm đủ/thiếu.
- model: dựng Research Knowledge Model (gaps, questions, claims, experiments) — `model_node.py`.
- synthesize: viết paper; hậu xử lý `report_postprocess.py`, `format_sanitizer.py`; kiểm chứng `evidence/` (citation_validator, hallucination_detector, claim_validator, stats, claim_scan, report_structure).
  - `stats.py`: Welch t-test + Cohen's d trên số liệu từng lần chạy (`experiments`) của người dùng; không đủ ≥2 lần chạy thì chỉ cảnh báo, khác biệt không có ý nghĩa thì claim thành `unsupported`.
  - `claim_scan.py`: sau khi ghép bài, quét câu khẳng định cho claim `unsupported`/`hypothesis` và nhờ LLM hạ giọng; câu không sửa được ghi vào `research_model.validation.leaked_claims`.
- State: `app/agent/state.py` (`ResearchState`). Inject LLM giả khi test: `build_graph(llm=fake)`.

## Luồng 3: chat với paper
`POST /chat` -> hybrid retrieval -> context_builder (giới hạn `context_token_limit`) -> LLM gateway -> trả lời + citations, lưu `messages`.

## LLM gateway (`app/ai/llm_gateway`)
Adapter: anthropic, openai, gemini, groq, openrouter; `registry.py` chọn theo `agent_provider`/model; `retry.py` backoff + fallback model OpenRouter.

## Phụ thuộc giữa module (một chiều)
`core` <- `ai`, `pipeline` <- `agent`, `api`. `agent` không import `api`. `api` gọi agent qua Celery task, không chạy agent trong request.

## Nguồn sự thật khác
`docs/RAG_FLOW.md`, `docs/RAG_UPGRADE_PLAN.md`, `docs/duties.md` (phân công 3 Dev: Dev1 ai, Dev2 pipeline/api/workers, Dev3 agent).
