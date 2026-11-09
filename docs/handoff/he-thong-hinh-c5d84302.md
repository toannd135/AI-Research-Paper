# Bàn giao: hệ thống hình theo đánh giá `survey_c5d84302.pdf` (2026-11-09)

## Mục tiêu
Sửa hệ thống biểu đồ/sơ đồ để paper survey qua phản biện Q1/Q2 phần hình (đánh giá 5.3/10, Major Revision).

## Nhánh/trạng thái git
`feature/normalization`, CHƯA commit/push. Cây làm việc lẫn thay đổi chưa commit của task Workspace (migration 0009) + đợt hình này.

## Đã xong (chưa commit)
- Đánh số hình theo khối thật, bỏ chú thích/câu của hình ma (hết hai "Figure 7").
- Chặn chart trộn phiên bản dataset/split/đơn vị; `protocol_panels` + loại chart `panels` (lưới small multiples, chú giải chung).
- Scatter cần ≥4 điểm; bảng chi phí thêm Training time/GPU memory/Energy.
- Sơ đồ hình thành corpus (không phải PRISMA) khi không có review_protocol; mermaid TD tầng >6 nút → LR.
- Chart `timeline` (năm phải khớp References) + prompt roadmap Gap→Direction→Evaluation (mục 6.4).
- `pytest app/agent app/pipeline` pass; ruff không thêm lỗi mới.
- Nạp DB: `papers_brain` 50/50 done; `papers_deepfake` 50/50 done (20 paper mới tải, `_manifest.json` đã cập nhật).
- PDF xem trước (áp hậu xử lý mới lên report cũ, không chạy lại agent): `survey_c5d84302_v2.pdf`.

## Quyết định đã chốt
ADR `docs/decisions/0008-hinh-theo-khoi-va-chan-tron-protocol.md`. Không sinh ảnh định tính BraTS (chỉ dùng ảnh có trong corpus).

## Tệp quan trọng
- `app/agent/evidence/report_structure.py` (`align_figure_captions`, `finalize_structure_report`)
- `app/agent/report_postprocess.py` (`mixed_protocol_reason`, `reject_mixed_protocol`, `orient_mermaid`, `scrub_timeline_spec`, `reference_years`)
- `app/agent/evidence/quant_analysis.py` (`protocol_panels`, `efficiency_table`, `tradeoff_scatter`)
- `app/agent/evidence/corpus_flow.py` (mới) · `app/agent/nodes/synthesize_node.py` (prompt 3.2/6.4, chèn corpus flow, `ref_years`)
- `app/pipeline/export/chart_scientific.py` (`render_panels_svg`, `_draw_timeline`) · `figure_layout.py` · `pdf_renderer.py` (`_extract_blocks`)
- Kế hoạch: `docs/implementation-plan.md` mục "Hệ thống hình…"; `docs/current-task.md`

## Việc còn lại
1. Người dùng chạy migration 0009 rồi restart worker, sau đó chạy lại survey brain → kiểm panels/corpus flow/timeline/roadmap trên PDF thật.
2. Chưa rõ vì sao chú thích ảnh thật in "Qualitative Visual Comparison" (đã có từ PDF gốc).
3. Corpus deepfake nằm chung DB với brain: research nên giới hạn theo workspace để không lẫn chủ đề.

## Đang chờ
Người dùng: `alembic upgrade head` (DB thật chưa có cột `research_tasks.workspace_id`) + commit.

## Lệnh kiểm tra
`ruff check app/agent app/pipeline/export` · `pytest app/agent app/pipeline -q`
Xuất lại PDF xem trước: `UPLOAD_DIR=data/papers_brain PYTHONPATH=. python <scratchpad>/rerender.py`
