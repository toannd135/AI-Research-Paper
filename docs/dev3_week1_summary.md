# Báo Cáo Tổng Hợp Công Việc: Dev 3 — Tuần 1 (AI Agent & Evaluation)

Tài liệu này tổng hợp toàn bộ các kết quả triển khai của **Dev 3 — Tuần 1** cho dự án **PaperAI**, cấu trúc kiến trúc đã xây dựng, cùng hướng dẫn chi tiết cách kiểm thử tự động và thủ công.

---

## 1. Danh sách file đã sửa và tạo mới

### 1.1. File đã sửa (Interface Contract)
* [app/core/schemas.py](file:///d:/paperai/AI-Research-Paper/app/core/schemas.py):
  * Định nghĩa `PaperRef`, `Chunk` (sử dụng `chunk_id`), `Citation`.
  * Định nghĩa `ResearchState` với trường `steps: Annotated[list[str], operator.add]` (LangGraph Reducer).
  * Định nghĩa Tool Input Schemas: `SearchPapersInput`, `RetrieveEvidenceInput`.
  * Định nghĩa API schemas: `ResearchRequest`, `ResearchResponse`.

### 1.2. File đã tạo mới
* [app/agent/tools/search_papers.py](file:///d:/paperai/AI-Research-Paper/app/agent/tools/search_papers.py): Mock tool tìm kiếm bài báo khoa học (`Attention Is All You Need`, `LoRA`, `RAG`, `BGE-M3`) chuẩn LangChain `@tool`.
* [app/agent/tools/retrieve_evidence.py](file:///d:/paperai/AI-Research-Paper/app/agent/tools/retrieve_evidence.py): Mock tool trích xuất đoạn văn bản (chunks) bằng chứng kèm số trang, đề mục, và điểm liên quan.
* [app/agent/generators/base.py](file:///d:/paperai/AI-Research-Paper/app/agent/generators/base.py): Protocol `AnswerGenerator` cho abstraction tầng sinh câu trả lời.
* [app/agent/generators/mock.py](file:///d:/paperai/AI-Research-Paper/app/agent/generators/mock.py): `MockAnswerGenerator` chạy 100% offline, đảm bảo nghiêm ngặt 4 yếu tố **Citation Grounding Invariant**.
* [app/agent/generators/llm.py](file:///d:/paperai/AI-Research-Paper/app/agent/generators/llm.py): Khung adapter LLM chuẩn bị cho Tuần 2.
* [app/agent/nodes/search.py](file:///d:/paperai/AI-Research-Paper/app/agent/nodes/search.py): Node tìm kiếm bài báo, bắt buộc gọi `PaperRef.model_validate()`.
* [app/agent/nodes/retrieve.py](file:///d:/paperai/AI-Research-Paper/app/agent/nodes/retrieve.py): Node trích xuất evidence, bắt buộc gọi `Chunk.model_validate()`.
* [app/agent/nodes/synthesize.py](file:///d:/paperai/AI-Research-Paper/app/agent/nodes/synthesize.py): Factory closure `create_synthesize_node(generator)` thực hiện dependency injection cho generator.
* [app/agent/nodes/fallback.py](file:///d:/paperai/AI-Research-Paper/app/agent/nodes/fallback.py): Node fallback xử lý khi không có evidence, chống hallucination.
* [app/agent/graph.py](file:///d:/paperai/AI-Research-Paper/app/agent/graph.py): Xây dựng `StateGraph(ResearchState)`, conditional edge `should_synthesize` và entrypoint `run_research_agent()`.
* [app/agent/evaluation/questions.json](file:///d:/paperai/AI-Research-Paper/app/agent/evaluation/questions.json): Bộ 6 câu hỏi kiểm thử baseline (factual, explanation, comparison, cross-paper).
* [app/agent/evaluation/evaluator.py](file:///d:/paperai/AI-Research-Paper/app/agent/evaluation/evaluator.py): Evaluator tính các chỉ số baseline và kiểm tra 4 điều kiện citation grounding.
* [app/agent/tests/test_agent_v0.py](file:///d:/paperai/AI-Research-Paper/app/agent/tests/test_agent_v0.py): 8 bài unit test bao phủ toàn bộ chức năng.

---

## 2. Kiến trúc luồng đồ thị LangGraph v0

```
                   [START]
                      │
                      ▼
               ┌─────────────┐
               │ search_node │  Gọi tool search_papers
               └──────┬──────┘  Lưu papers vào State (PaperRef.model_validate)
                      │
                      ▼
              ┌───────────────┐
              │ retrieve_node │  Gọi tool retrieve_evidence
              └───────┬───────┘  Lưu evidence vào State (Chunk.model_validate)
                      │
                      ▼
            / Có evidence không? \
           <                      >
            \                    /
          Có ├───            ───┤ Không
             │                  │
             ▼                  ▼
    ┌─────────────────┐ ┌───────────────┐
    │ synthesize_node │ │ fallback_node │
    └────────┬────────┘ └───────┬───────┘
             │                  │
             └────────┬─────────┘
                      │
                      ▼
                    [END]
```

### 4 Điểm kỹ thuật mấu chốt:
1. **Model Validate**: Mọi dữ liệu dict từ tool đều qua `PaperRef.model_validate()` và `Chunk.model_validate()` trước khi vào State.
2. **Closure / Factory Pattern**: `create_synthesize_node(generator: AnswerGenerator)` giúp inject generator linh hoạt khi khởi tạo đồ thị.
3. **Accumulating Steps Reducer**: `steps: Annotated[list[str], operator.add]` tự động nối bước chạy qua từng node mà không bị ghi đè.
4. **Strict Citation Grounding Invariant**: Mọi trích dẫn `Citation` bắt buộc phải thỏa mãn:
   - `chunk_id` tồn tại trong `evidence`.
   - `paper_id` khớp với chunk tương ứng.
   - `page_number` khớp với trang của chunk.
   - `quoted_text` là một chuỗi con (`substring`) thực sự nằm trong `chunk.content`.

---

## 3. Hướng dẫn kiểm thử (Cách test phần việc Tuần 1)

Bạn có thể test bằng 2 cách: **Kiểm thử tự động bằng Pytest** hoặc **Chạy thử kịch bản trực tiếp bằng Python Script**.

### Cách 1: Chạy toàn bộ Pytest tự động

Mở PowerShell tại thư mục dự án `d:\paperai\AI-Research-Paper`:

```powershell
# Kích hoạt môi trường ảo (nếu chưa kích hoạt)
.\.venv\Scripts\Activate.ps1

# Chạy toàn bộ test suite của Dev 3
pytest app/agent/tests/test_agent_v0.py -v
```

**Các kịch bản được kiểm tra trong Pytest:**
1. `test_search_papers_schema`: Kiểm tra dữ liệu bài báo trả về khớp chuẩn `PaperRef`.
2. `test_retrieve_evidence_schema`: Kiểm tra dữ liệu chunk trả về khớp chuẩn `Chunk`.
3. `test_retrieve_unknown_paper`: Kiểm tra query với paper lạ không gây crash, trả về mảng rỗng an toàn.
4. `test_graph_returns_required_fields`: Kiểm tra graph chạy qua `search -> retrieve -> synthesize` và trả về đủ các trường.
5. `test_citations_reference_existing_chunks`: Kiểm tra nghiêm ngặt 4 điều kiện Citation Grounding Invariant.
6. `test_unknown_question_uses_fallback`: Kiểm tra câu hỏi ngoài phạm vi sẽ tự động rẽ sang `fallback_node`.
7. `test_generator_dependency_injection`: Kiểm tra cơ chế inject generator qua closure.
8. `test_evaluation_dataset`: Chạy đánh giá batch trên toàn bộ 6 câu hỏi trong `questions.json`.

---

### Cách 2: Chạy trực tiếp qua Python CLI

Bạn có thể mở Python trong terminal hoặc tạo script chạy thử:

```python
from app.agent.graph import run_research_agent
import json

# Test 1: Câu hỏi hợp lệ
print("=== TEST CÂU HỎI HỢP LỆ ===")
res = run_research_agent("Cơ chế Attention trong bài báo Attention Is All You Need hoạt động như thế nào?")
print("Papers tìm thấy:", [p.title for p in res["papers"]])
print("Số evidence:", len(res["evidence"]))
print("Các bước thực hiện:", res["steps"])
print("Câu trả lời:\n", res["answer"])
print("Citations:", [c.model_dump() for c in res["citations"]])

print("\n" + "="*50 + "\n")

# Test 2: Câu hỏi ngoài phạm vi (Fallback)
print("=== TEST FALLBACK KHI KHÔNG CÓ BẰNG CHỨNG ===")
res_fallback = run_research_agent("Thông tin về một chủ đề không tồn tại trong cơ sở dữ liệu xyz 123?")
print("Các bước thực hiện:", res_fallback["steps"])
print("Câu trả lời:", res_fallback["answer"])
print("Citations:", res_fallback["citations"])
```

---

## 4. Hạn chế của phiên bản v0 và Kế hoạch kết nối Tuần 2

### Hạn chế ở Tuần 1:
* Đang sử dụng dữ liệu Mock (`MOCK_PAPERS` và `MOCK_EVIDENCE_CHUNKS`) thay vì dữ liệu thật.
* `MockAnswerGenerator` sinh câu trả lời theo khuôn mẫu trích dẫn deterministic, chưa gọi LLM sinh ngôn ngữ tự nhiên tự do.
* Luồng chạy là deterministic tĩnh (chưa có multi-turn retrieval hay reflection loop).

### Kế hoạch bàn giao & Tích hợp ở Tuần 2:
1. **Với Dev 1 (RAG / AI)**:
   * Thay thế `retrieve_evidence` mock bằng hàm `retrieve()` thật từ `app/ai/retrieval/` (Hybrid Vector + BM25).
   * Cắm `LLMAnswerGenerator` vào `LLMService` của Dev 1 (`app/ai/llm_gateway/`).
2. **Với Dev 2 (Pipeline / Backend)**:
   * Chuyển `search_papers` mock thành truy vấn danh sách paper từ PostgreSQL (`models/paper.py`).
   * Cắm `run_research_agent` vào Celery task `run_research` trên `research_queue`.
