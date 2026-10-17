# Bàn giao: sửa chất lượng bài báo + lỗi hệ thống

## Mục tiêu
Sửa lỗi sinh bài báo (mermaid hỏng, bảng/biểu đồ thiếu số liệu, thiếu ảnh, lẫn Anh–Việt) và các lỗi chạy hệ thống. Bài báo luôn bằng tiếng Anh (chuẩn quốc tế).

## Nhánh/trạng thái git
Nhánh `feature/agent`. TOÀN BỘ thay đổi chưa commit, chưa push (kể cả `.env`, đã ignore).

## Đã xong (chưa có commit)
- Gỡ xung đột git còn sót: `app/agent/nodes/synthesize_node.py`, `app/pipeline/export/typst_renderer.py`.
- Hậu xử lý báo cáo: `app/agent/report_postprocess.py` (validate/sửa mermaid, gỡ số không có căn cứ, dịch đoạn lệch ngôn ngữ, chèn biểu đồ từ ledger).
- Ngôn ngữ: `app/agent/language.py`, `MANUSCRIPT_LANGUAGE="en"` ở `graph.py`; critique + analyze + synthesize ép tiếng Anh.
- Frontend nhãn Hình/Bảng theo ngôn ngữ: `frontend/src/client/components/article/articleLang.ts`.
- Docker compose: comment api/worker, chạy uvicorn trên host; `.env` đổi sang localhost:5433/6333/6380.
- Xoá được phiên đang `processing` (Sidebar.tsx, routes/research.py, tasks.py).
- Biến model: ANTHROPIC_MODEL, OPENAI_MODEL, 2 model Gemma (registry.py, config.py).
- Qdrant: lập chỉ mục lại, `process_paper` idempotent, `scripts/reindex_papers.py`.

## Quyết định đã chốt
- Bài báo luôn tiếng Anh, không đa ngôn ngữ; truy vấn tìm kiếm bằng tiếng Anh.
- Dấu mốc cấu trúc (Abstract/Keywords/References) giữ token tiếng Anh vì parser Typst.
- Không nâng server Qdrant; dùng `check_compatibility=False`.

## Tệp quan trọng
- app/agent/report_postprocess.py (toàn file), app/agent/nodes/critique_node.py, app/agent/nodes/synthesize_node.py:423
- app/ai/llm_gateway/registry.py:34, app/core/config.py:36

## Việc còn lại
0. VIỆC TIẾP THEO (user vừa yêu cầu): giao diện phải cho chọn model ngay lúc tạo bài nghiên cứu mới. Hiện model chỉ chọn ở ChatView (frontend/src/client/components/chat/ChatView.tsx:38,171, lấy từ GET /chat/models). Cần: thêm field `model` vào ResearchRequest (app/core/schemas.py:233) + cột DB/migration cho ResearchTask (app/api/models/research_task.py), truyền model qua tasks.run_research → run_graph(llm=build_gateway(resolve_model(...))), và UI chọn model ở bước nhập chủ đề (useAppController.submitTopic → createResearch trong frontend/src/client/api/research.ts).
1. Commit theo nhóm (merge fix; postprocess+ngôn ngữ; model Gemma; docker/env; reindex).
2. Ảnh minh hoạ thật (trích figure từ PDF gốc hoặc sinh bằng mô hình ảnh) — chưa làm.
3. Tuỳ chọn: tên biến key Gemma 26B trong `.env` gõ nhầm (`MODEL_GEMMA_4_2B_IT_FREE_KEY`).

## Đang chờ
Người dùng chọn hướng ảnh minh hoạ và xác nhận commit. `sample_paper.pdf` mất file (cần tải lại).

## Lệnh kiểm tra
`MERMAID_INK_ENABLED=false python -m pytest -q` ; `cd frontend && npm run check`
