# PHỤ LỤC KỸ THUẬT — TECH STACK & THIẾT KẾ HỆ THỐNG PAPERAI
 
> Tài liệu này bổ sung cho **"Kế hoạch chi tiết 5 tuần — Team PaperAI (3 Dev)"**: nêu rõ **làm như nào** và **dùng công nghệ gì** ở từng phần, đồng thời chốt **thiết kế hệ thống (system design)** dựa trên sơ đồ kiến trúc đã thống nhất.
 
---
 
## 1. SƠ ĐỒ KIẾN TRÚC TỔNG THỂ (System Design)
 
```
                           │
                           ▼
                    ┌─────────────┐
                    │   Frontend  │   (AI-generated, ngoài phạm vi 3 Dev)
                    └──────┬──────┘
                           │  HTTPS/REST (JSON)
                           ▼
                    ┌─────────────┐
                    │ API Gateway │   (routing, auth, rate limit)
                    └──────┬──────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
        User Service   Research       Article
        (Dev 2)        Service        Service (Dev 2)
                        (Dev 2 host,
                         Dev 3 logic)
                           │
                           ▼
                 ┌───────────────────┐
                 │   Research Engine │   (Dev 3 chủ trì, Dev 1 cung cấp RAG)
                 │  LangGraph/LangChain │
                 └─────────┬─────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
     Search Layer      RAG Layer       Knowledge Layer
     (Dev 2 fetch,     (Dev 1)         (Dev 1/Dev 3 - optional
      Dev 3 gọi tool)                   sau MVP, không bắt buộc)
          │                │                │
 Academic APIs        Embedding        Knowledge Graph
 Paper Search         Vector DB              (nice-to-have)
 Document Fetch       Retriever + Reranker
                           │
                           ▼
                    Evidence Layer (Dev 3)
                           │
                    ┌──────┴──────┐
                    ▼             ▼
                 Citation      Verification
               (Dev 1 sinh)   (Dev 3 validate)
                           │
                           ▼
                     LLM Gateway (Dev 1)
                           │
                ┌──────────┼──────────┐
                ▼          ▼          ▼
              vLLM       OpenAI     Claude
                │        (API)      (API)
                ▼
             Qwen/Llama (self-host, optional)
      ┌─────────────────────────────────────┐
      │            DATA LAYER (Dev 2)        │
      │                                     │
      │ PostgreSQL   Vector DB   Object Store│
      │ Knowledge Graph (sau MVP)   Redis    │
      └─────────────────────────────────────┘
```
 
### 1.1 Nguyên tắc thiết kế
- **Stateless services**: mọi service (User/Research/Article) đều stateless, state nằm ở Data Layer → dễ scale ngang, dễ deploy đơn giản (không cần DevOps phức tạp).
- **LLM Gateway là lớp trừu tượng bắt buộc**: không service nào được gọi thẳng OpenAI/Claude/vLLM — tất cả đi qua `LLMService` để đổi model không sửa code gọi (đúng yêu cầu DoD tuần 5).
- **Research Engine là "bộ não"**, không tự làm retrieval — nó **gọi tool** vào RAG Layer, Search Layer, Evidence Layer. Điều này giữ đúng ranh giới Dev 1 (RAG) / Dev 3 (Agent) đã thống nhất.
- **MVP 5 tuần KHÔNG bắt buộc Knowledge Graph** và **KHÔNG bắt buộc Academic APIs bên ngoài** (Search Layer) — đây là phần mở rộng sau MVP để tránh phình phạm vi 3 dev/5 tuần. Trong 5 tuần, "Search Layer" thu hẹp lại = paper người dùng tự upload (không crawl ngoài).
---
 
## 2. TECH STACK THEO LỚP KIẾN TRÚC
 
| Lớp | Công nghệ đề xuất | Dev phụ trách | Ghi chú |
|---|---|---|---|
| API Gateway | **FastAPI** (Python) làm gateway kiêm luôn routing nội bộ (monolith-modular, chưa cần Kong/Nginx riêng) | Dev 2 | 5 tuần không đủ thời gian cho microservice thật, dùng **modular monolith**: 1 FastAPI app, chia module `users/`, `papers/`, `chat/`, `research/` |
| User/Article/Research "Service" | Modules trong cùng FastAPI app, gọi nhau qua function/service layer (không qua network) | Dev 2 (host), Dev 3 (logic research) | Để dành network-service-thật cho giai đoạn sau MVP nếu cần scale |
| Research Engine | **LangGraph** (state machine cho Agent, quản lý Plan→Search→Read→Analyze→Synthesize), **LangChain** (tool wrapper, prompt template) | Dev 3 | LangGraph phù hợp hơn LangChain Agent thường vì cần multi-step có state rõ ràng (đúng yêu cầu Tuần 4) |
| Search Layer | Trong MVP: query nội bộ trên paper đã upload (không gọi Academic API ngoài) | Dev 2 (data), Dev 3 (tool wrapper) | Academic API (Semantic Scholar, arXiv API...) để **sau MVP**, ghi chú "future work" |
| RAG Layer — Embedding | **BGE-M3** hoặc **OpenAI `text-embedding-3-small`** (so sánh 2 lựa chọn trong `model-selection.md` Tuần 1) | Dev 1 | BGE-M3 chạy local (không tốn phí, hỗ trợ multilingual) — ưu tiên nếu có GPU; nếu không, dùng API embedding |
| RAG Layer — Vector DB | **Qdrant** (self-host, dễ deploy bằng Docker, hỗ trợ hybrid search built-in) | Dev 2 (deploy + abstraction), Dev 1 (dùng) | Thay thế được bằng pgvector nếu muốn giảm 1 service, nhưng Qdrant có sẵn BM25+vector hybrid nên nhanh hơn cho Tuần 2 |
| RAG Layer — Reranker | **BGE-Reranker-v2-m3** (cross-encoder, chạy local) hoặc Cohere Rerank API | Dev 1 | Local model tránh phụ thuộc API ngoài, phù hợp nếu có GPU |
| Knowledge Layer | Bỏ qua trong MVP (đã ghi ở mục 1.1) | — | — |
| Evidence Layer (Citation/Verification) | Prompt-based extraction (LLM trích claim) + rule-based matching (so khớp `chunk_id` đã cite có thực sự chứa nội dung không) | Dev 3 | Không cần model riêng, dùng LLM Gateway + string/semantic matching đơn giản |
| LLM Gateway | Python class `LLMService` với interface chung `generate(prompt, model="default")`, config theo `.env`/`config.yaml` | Dev 1 | Hỗ trợ tối thiểu 2 provider: **OpenAI/Claude API** (chính) + 1 model qua **vLLM** hoặc Ollama tự host (Qwen2.5/Llama3) để demo khả năng đổi model |
| vLLM / self-host model | **vLLM** serving **Qwen2.5-7B-Instruct** hoặc **Llama-3.1-8B** (nếu có GPU); nếu không có GPU, dùng **Ollama** làm phương án nhẹ hơn | Dev 1 | Chỉ cần chạy được, không cần tối ưu throughput trong MVP |
| PDF Parsing | **PyMuPDF (fitz)** cho extract nhanh + **Docling** hoặc **GROBID** nếu cần giữ cấu trúc section tốt hơn (ưu tiên PyMuPDF trước, nâng cấp Docling nếu Tuần 1 thấy chất lượng section kém) | Dev 2 | GROBID cần chạy Java service riêng — cân nhắc theo thời gian còn lại |
| Async Processing / Queue | **Celery + Redis** (hoặc **RQ + Redis** nếu muốn nhẹ hơn) | Dev 2 | Redis dùng chung cho cả Queue lẫn cache (đỡ 1 service) |
| Database (metadata) | **PostgreSQL** (qua **SQLAlchemy** + **Alembic** migration) | Dev 2 | Bảng chính: `Paper, PaperMetadata, PaperChunk, Conversation, Message, ResearchTask` |
| Object Storage | **MinIO** (S3-compatible, self-host bằng Docker) hoặc lưu local disk nếu MVP không cần scale | Dev 2 | Local disk là đủ cho 5 tuần nếu không deploy production thật; MinIO nếu muốn gần production hơn |
| Backend Framework chung | **FastAPI** + **Pydantic** (schema validation) cho toàn bộ API | Cả 3 Dev (Dev 2 chủ) | Thống nhất 1 framework để 3 Dev code cùng convention |
| Testing | **pytest** (unit + integration), **httpx** (test API async) | Cả 3 Dev | Coverage tối thiểu cho các module cốt lõi theo checklist Tuần 5 |
| Containerization | **Docker Compose** (1 file duy nhất: `app, postgres, qdrant, redis`) — **không dùng Kubernetes** trong 5 tuần | Dev 2 setup, cả team dùng | Giữ đúng nguyên tắc "không có DevOps trong phạm vi" — dùng hạ tầng đơn giản nhất |
 
---