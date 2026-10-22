# Bàn giao: Paper đa đối tượng, đa lĩnh vực

## Mục tiêu
Nâng chất lượng paper sinh ra: ảnh thật (có nguồn/giấy phép), số liệu + biểu đồ từ dữ liệu thật,
phân tích so sánh theo lĩnh vực, điều chỉnh theo đối tượng (giảng viên / sinh viên / người đi làm).

## Nhánh / trạng thái git
- Nhánh `feature/login`, chưa commit: app/agent/tests/test_typst_renderer.py, app/api/routes/research.py,
  app/pipeline/export/templates/cvpr_paper.typ, app/pipeline/export/typst_renderer.py (KHÔNG revert).

## Đã xong
- Chưa sửa mã. Mới soạn prompt Phase 1 (audit + kế hoạch) bằng /prompt-master, chưa chạy.

## Quyết định đã chốt
- Làm 2 pha: Phase 1 chỉ đọc + viết kế hoạch; Phase 2 chỉ cài đặt sau khi người dùng duyệt.
- Nguyên tắc: không bịa số liệu/ảnh/trích dẫn; thiếu dữ liệu thì bỏ hoặc gắn nhãn.

## Tệp quan trọng
- app/agent/nodes/analyze_node.py:18,32,50 (prompt survey/novel, analyze_node)
- app/agent/nodes/synthesize_node.py:435 (synthesize_node, Stage 0–6)
- app/pipeline/export/typst_renderer.py:451 (chart→SVG), :555 (mermaid), :705 (render_report_to_pdf)
- app/api/routes/papers.py:66 (upload PDF → parse/chunk/embed)

## Việc còn lại
1. Chạy Phase 1: audit 4 trục (ảnh thật, số liệu/biểu đồ, lĩnh vực, đối tượng) → ghi
   docs/plans/paper-da-doi-tuong.md (≤150 dòng, bảng P0/P1/P2, thiết kế, test, rủi ro).
2. Sau duyệt: Phase 2 cài đặt các mục P0.

## Đang chờ
- Người dùng chạy prompt Phase 1, rồi chọn: API ảnh nào, có thêm cột `audience` vào DB không.

## Lệnh kiểm tra
- `pytest app/agent/tests -q 2>&1 | tail -20`
