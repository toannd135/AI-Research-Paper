# 0008 — Đánh số hình theo khối thật; chặn biểu đồ trộn protocol; sơ đồ corpus thay PRISMA giả

Ngày: 2026-11-09 · Trạng thái: chấp nhận · Bối cảnh: đánh giá phần hình của `survey_c5d84302.pdf` (5.3/10, Major Revision)

## Bối cảnh
- Hai "Figure 7": LLM viết chú thích `**Figure 7: …**` cho scatter, validator bỏ khối scatter nhưng chú thích còn; renderer lại tự đánh số
  các khối hình (kể cả evidence map tự chèn) → số trong thân bài lệch số in dưới hình.
- Figure 5 đặt BraTS 2020 hidden test (%) và BraTS 2021 validation (tỉ lệ) trên một trục dù prompt đã cấm.
- Scatter chi phí/độ bền chỉ có 2–3 điểm; không có sơ đồ hình thành corpus; taxonomy TD 34 lá trên một hàng.

## Quyết định
1. Số hình = thứ tự khối chart/image/mermaid (như renderer). Chú thích không đứng ngay trên khối → hình ma: xóa chú thích và câu nhắc số đó.
2. Chart so sánh (bar/dot/line/scatter…) có ≥2 phiên bản cùng tên dataset, ≥2 loại split, hoặc lẫn % với tỉ lệ → bỏ (không sửa hộ). Dumbbell
   (đúng 2 điều kiện ghép cặp) và heatmap cấu hình được miễn. Thay thế tất định: `protocol_panels` (mỗi ô một setting từ record đã kiểm chứng).
3. Scatter cần ≥4 điểm có căn cứ; ít hơn thì bảng chi phí (cột NR thể hiện mức báo cáo) đảm nhận.
4. Không có `review_protocol.json` → sơ đồ "corpus formation" từ số đếm thật, ghi rõ không phải PRISMA (không bịa bước sàng lọc).
5. Timeline do LLM viết chỉ giữ mốc có đúng một [n] và năm = năm in ở reference [n].

## Đánh đổi
- Heuristic trộn protocol có thể bỏ nhầm chart hợp lệ có caption nhắc hai năm vì lý do khác (vd. "methods 2019–2021" vẫn qua vì không theo tên
  dataset). Chấp nhận: mất một hình tốt hơn in một so sánh sai.
- Hình định tính đúng miền (BraTS) không thể tạo nếu corpus không có ảnh đó; hệ thống không sinh ảnh.
