# Báo Cáo Tích Hợp & Hoàn Thiện Dev 3: AI Research Agent & RAG Pipeline (Tuần 1 - Tuần 4)

Tài liệu này tổng hợp toàn bộ các công việc của **Dev 3 (AI Agent & Evaluation)** sau khi giải quyết xung đột (merge conflict) với nhánh `develop` (Dev 1 & Dev 2), đồng bộ và hoàn thiện toàn bộ tính năng theo lộ trình từ Tuần 1 đến Tuần 4.

---

## 1. Tổng quan kết quả xử lý Merge Conflict từ `develop`

Nhánh `develop` đã được tích hợp thành công vào `feature/agent` với 0 conflict còn tồn đọng:
- **`app/core/schemas.py`**: Hợp nhất thành công hai luồng schema. Vừa giữ nguyên các model nghiệp vụ của Dev 1 & Dev 2 (`ScoredChunk`, `PaperStatus`, `ResearchStatus`, `ExternalSource`, `SourceSearchResponse`), vừa bổ sung cơ chế alias và proxy tương thích ngược 2 chiều (`chunk_id` <-> `id`, `content` <-> `text`, `page_number` <-> `page`, `section_title` <-> `section`, `quoted_text` <-> `text_snippet`).
- **`app/api/models/`**: Khắc phục lỗi `.gitignore` loại trừ nhầm thư mục ORM models (`/models/`), khôi phục toàn bộ các ORM model SQLAlchemy: `Paper`, `Conversation`, `Message`, `ResearchTask`.
- **`app/agent/graph.py`**: Chuyển đổi đồ thị LangGraph sang workflow 5-node hoàn chỉnh: `plan` -> `search` -> `analyze` -> `critique` -> (vòng lặp phản biện tối đa 2 vòng) -> `synthesize` -> `END`. Giữ đầy đủ hàm tương thích ngược `run_research_agent()` và `build_research_graph()`.
- **`app/agent/tools/`**: Chuẩn hóa `search_papers` và `retrieve_evidence` chạy trực tiếp trên Hybrid Retrieval (BM25 + Qdrant Vector + BGE Reranker) với `ThreadPoolExecutor` chạy song song các sub-query.

---

## 2. Các tính năng Tuần 3 & 4 Dev 3 hoàn thiện tương ứng với Dev 1

Dev 1 đã hoàn thành nền tảng hạ tầng retrieval, reranking và client OpenAlex. Phía Dev 3 đã kết nối và hoàn thiện tương ứng các khối kiến trúc sau:

### 2.1. External Literature Discovery Tool (`search_external_papers`)
- **Vị trí**: [app/agent/tools/search_external_papers.py](file:///d:/paperai/AI-Research-Paper/app/agent/tools/search_external_papers.py)
- **Chức năng**: Kết nối trực tiếp client OpenAlex (`app/ai/external/openalex_client.py`) vào hệ sinh thái Tool của Agent. Cho phép Agent tìm kiếm các công trình nghiên cứu khoa học toàn cầu khi kho dữ liệu nội bộ (Qdrant) chưa đủ bao quát hoặc khi người dùng yêu cầu khảo sát y văn rộng.
- **Dữ liệu trả về**: `SourceSearchResponse` gồm danh sách `ExternalSource` (tiêu đề, tác giả, năm, trích dẫn, DOI, abstract, điểm relevance) và mạng lưới liên kết quan hệ `ExternalSourceRelation` (`cites`, `related`).

### 2.2. Kiểm thử tự động Offline Deterministic 100%
- **Vị trí**: [app/agent/tests/test_agent_v0.py](file:///d:/paperai/AI-Research-Paper/app/agent/tests/test_agent_v0.py), [app/agent/tests/test_search_external_papers.py](file:///d:/paperai/AI-Research-Paper/app/agent/tests/test_search_external_papers.py)
- **Cơ chế**: Sử dụng `_FakeGateway` định tuyến thông minh theo system prompt, giải lập hoàn hảo 4 node LLM (`plan`, `analyze`, `critique/fact-checker`, `synthesize`), loại bỏ hoàn toàn các lệnh gọi tốn phí ra internet hoặc Google Gemini API khi chạy test.
- **Kết quả**: Toàn bộ **30/30 tests** trong `app/agent/tests/` pass 100%.

### 2.3. Benchmark & Đánh giá chất lượng (`run_benchmark.py` & `evaluator.py`)
- **Vị trí**: [app/agent/evaluation/run_benchmark.py](file:///d:/paperai/AI-Research-Paper/app/agent/evaluation/run_benchmark.py), [app/agent/evaluation/evaluator.py](file:///d:/paperai/AI-Research-Paper/app/agent/evaluation/evaluator.py)
- **Chỉ số đánh giá**:
  - `recall_at_k`: Tỉ lệ chunks vàng (gold data) xuất hiện trong top-K retrieved evidence.
  - `citation_faithfulness`: Tỉ lệ các trích dẫn `[n]` trong báo cáo thực sự khớp với evidence đã kiểm chứng.
  - `citation_grounding`: Kiểm tra 4 điều kiện nghiêm ngặt (chunk_id tồn tại, paper_id khớp, page khớp, quoted_text là substring).
  - `keyword_recall`: Đo lường mức độ bao phủ các khái niệm cốt lõi theo từng loại câu hỏi (`factual`, `explanation`, `comparison`, `cross-paper`).
- Hỗ trợ tham số `llm: LLMGateway | None = None` để chạy linh hoạt cả chế độ offline CI/CD và chế độ đo lường thật với Gemini/Claude/OpenAI.

### 2.4. Khung Đồ Thị LangGraph Hoàn Chỉnh

```
                 [POST /research]
                         │
                         ▼
               ┌───────────────────┐
               │ clarify() (Đồng bộ)│ -> Chưa rõ -> Trả ngay câu hỏi làm rõ
               └─────────┬─────────┘
                         │ Đã rõ -> Tạo ResearchTask (PENDING) -> Celery
                         ▼
             [Celery worker: run_research]
                         │
                         ▼
                   [LangGraph]
                         │
                         ▼
                   ┌───────────┐
                   │ plan_node │  Sinh 3-5 sub-queries từ câu hỏi
                   └─────┬─────┘
                         │
                         ▼
                  ┌─────────────┐
                  │ search_node │  ThreadPoolExecutor: Hybrid Retrieval + Rerank
                  └──────┬──────┘
                         │
                         ▼
                 ┌──────────────┐
                 │ analyze_node │  Build context ([1], [2]...) + Viết draft có trích dẫn
                 └───────┬──────┘
                         │
                         ▼
                 ┌──────────────┐
                 │ critique_node│  citation_validator + hallucination_detector
                 └───────┬──────┘
                         │
              / Có lỗi & iterations < 2? \
             <                            >
              \                          /
            Có ├───                  ───┤ Không (hoặc hết lượt)
               │                        │
               ▼                        ▼
        Quay lại analyze_node    ┌─────────────────┐
        (Kèm critique_feedback)  │ synthesize_node │  Ép draft vào khung báo cáo chuẩn
                                 └────────┬────────┘
                                          │
                                          ▼
                                        [END]
                                          │
                                          ▼
                           Cập nhật ResearchTask: DONE
```

---

## 3. Tổng kết tình trạng toàn bộ Test Suite

Tất cả các module trong toàn bộ repo đều vượt qua kiểm thử:
1. `app/agent/tests/`: **30 passed** (bao gồm `test_graph`, `test_plan_node`, `test_critique_node`, `test_hallucination_detector`, `test_clarify`, `test_citation_validator`, `test_search_papers`, `test_search_external_papers`, `test_agent_v0`).
2. `app/ai/tests/`: **35 passed** (`test_gemini_adapter`, `test_hybrid`, `test_context_builder`, `test_openalex_mapper`, `test_llm_registry`, adapter tests).
3. `app/api/tests/`: **12 passed** (`test_models`, `test_chat_route`, `test_research_route`, `test_research_task_model`).
4. `app/pipeline/tests/`: **10 passed** (`test_chunking`, `test_section_detector`).
5. `tests/`: **9 passed** (`test_bm25_index_cache`, `test_embedding_cache`).

**Tổng cộng: 96/96 tests PASSED 100%.**
Code style sạch sẽ, tuân thủ `ruff check` và không còn file uncommitted.
