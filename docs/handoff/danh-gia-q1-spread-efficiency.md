# Bàn giao: nâng survey theo đánh giá Q1/Q2 (2026-11-08)

## Đã làm
- `ResultRecord.spread` + `spread_type` (SD|SE|CI95); extractor chỉ giữ khi `± x` có nguyên văn trong chunk và loại sai số hợp lệ (`extractor._verified_spread`).
- `quant_analysis.efficiency_table` (Params/GFLOPs/Inference time, ô thiếu NR) vào `build_quant_blocks`; bảng Δ có cột Spread khi có ít nhất một nguồn báo; `evidence_limits` đếm spread thật; ledger Notes hiện `±x (loại)`.
- `_CHART_BLOCK_RULE`: biểu đồ có error bar thì caption phải nêu loại sai số, đơn vị lặp, viết tắt.
- `docs/paper-wishlist.md`: danh sách paper nên thêm (BraTS 2022+, Mamba, SAM, diffusion). Tên viết theo trí nhớ, cần kiểm tra nguồn.
- Test: `pytest app/agent -q` pass (thêm 5 test trong `test_evidence_pipeline.py`).

## Cố ý không làm
- Tự dựng PRISMA/số liệu sàng lọc; p-value/meta-analysis (nguồn hiếm báo).
- Chưa sửa: font chart (DejaVu → Liberation Sans, chữ ≥8pt), violin/trendline, caption nêu n/p-value ngoài error bar.

## Đang chờ
- Người dùng thêm paper từ wishlist vào `data/papers_brain`, nạp, chạy lại survey (analyze ~17 phút) để thấy spread/efficiency thật.
- Task trước còn mục "chạy lại survey và đối chiếu".
- PDF `data/exports/survey_58ad3caf.pdf` là bản HTML engine: Typst lỗi `unknown variable: ap` (công thức có biến trần), 6 khối image bị bỏ (F1, F2, F4…).
- `git status` có `m frontend` (submodule đổi nội dung) — không do task này.
