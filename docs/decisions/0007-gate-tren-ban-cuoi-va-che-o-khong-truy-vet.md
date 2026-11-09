# ADR 0007: Quality Gate chạy trên bản cuối và che ô số không truy vết

Ngày: 2026-11-09 · Trạng thái: chấp nhận

## Bối cảnh
Gate chạy trên văn bản thô (trước chèn bảng định lượng, đánh số lại [n]) nên `validation_report` không mô tả PDF được xuất; 18 ô HD95 không truy vết vẫn lọt vào bảng chỉ với cảnh báo.

## Quyết định
1. Chạy gate lần 2 trên bản cuối với `numbered_citations` (ánh xạ [k] → paper); lần 1 giữ làm `draft_gate`.
2. Ô số UNTRACED trong bảng không `derived` được thay bằng `NR` và caption ghi chú.

## Đánh đổi
- (+) Báo cáo khớp PDF; không số liệu không nguồn trong bảng.
- (−) Mất số có thể đúng nhưng extractor/traceability không khớp (false positive) — người dùng vẫn đối chiếu được qua `redacted_cells`; thêm chi phí 1 lần gate (không gọi LLM).
- Không dùng LLM để "cứu" số: tránh bịa.
