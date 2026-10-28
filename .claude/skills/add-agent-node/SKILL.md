---
name: add-agent-node
description: Thêm hoặc sửa một node trong đồ thị LangGraph của research agent (app/agent). Dùng khi cần bước xử lý mới trong pipeline plan→search→analyze→critique→model→synthesize.
---
# Thêm node agent
1. `codegraph_explore "build_graph ResearchState <node liên quan>"` để xem graph + state hiện tại.
2. Thêm field vào `app/agent/state.py` nếu node đọc/ghi state mới (có default, tương thích node cũ).
3. Tạo `app/agent/nodes/<tên>_node.py`: `def <tên>_node(state, llm=None) -> dict`. Parse LLM bằng `json_utils`; có fallback khi JSON sai/LLM lỗi.
4. Nối vào `app/agent/graph.py` (`add_node`, `add_edge`/conditional). Giữ `llm` inject qua lambda như các node khác.
5. Test: `app/agent/tests/test_<tên>_node.py` (fake LLM, nhánh lỗi) + cập nhật `test_graph.py` (routing).
6. Nếu kết quả lưu/hiển thị: đi tiếp `add-migration` / `add-api-endpoint`.
7. Cập nhật `docs/architecture.md` (sơ đồ luồng 2), rồi chạy skill `verify-change`.
