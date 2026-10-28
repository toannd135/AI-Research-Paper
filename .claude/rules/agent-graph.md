---
paths:
  - "app/agent/**/*.py"
---
# Agent / LangGraph
- Node: `def x_node(state, llm=None) -> dict` trả phần state cập nhật; nhận `llm` để inject khi test.
- Output LLM luôn parse qua `json_utils`, giả định có thể sai; có fallback, không để node ném lỗi làm sập graph.
- Đổi graph (node/edge) -> cập nhật `docs/architecture.md` + `test_graph.py` (routing).
- Mọi citation/claim phải truy được tới nguồn; thêm kiểm tra vào `evidence/` thay vì tin LLM.
- Prompt theo `profiles.py` (field/audience); không hard-code theo một lĩnh vực.
