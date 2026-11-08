# 0006 — Evidence có cấu trúc và chặn export theo Quality Gate

## Quyết định
1. Số liệu định lượng chỉ đến từ `ResultRecord` đã kiểm chứng NGUYÊN VĂN trong chunk PDF; LLM chỉ đề xuất, code lọc. Ledger dựng bằng code, thiếu = `NR`.
2. `validation_report.passed=false` → export PDF/LaTeX trả 409; `?draft=true` để tải bản nháp. BibTeX không bị chặn.
3. `VERIFIED` chỉ khi Crossref khớp DOI + tiêu đề (`REFERENCE_EXTERNAL_VERIFY`, tắt mặc định); khớp catalog nội bộ = `CATALOG_MATCHED`.
4. Hạn mức hình/bảng theo loại paper là benchmark nội bộ (WARNING), không phải chuẩn Q1–Q4.

## Đánh đổi
- Thêm ⌈số paper/5⌉ lần gọi LLM mỗi bài (tốn quota free); bù lại số liệu truy được.
- Trích xuất bỏ giá trị không khớp nguyên văn → ledger thưa hơn (đúng chủ đích, không bịa); độ phủ phụ thuộc chất lượng chunk bảng của parser PDF.
- Chặn export có thể gây khó chịu khi gate quá chặt; lối thoát `?draft=true`.
