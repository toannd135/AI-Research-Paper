# 0003 — Research Knowledge Model lưu dạng JSON text trong research_tasks
Trạng thái: accepted (theo code hiện tại)
**Bối cảnh:** muốn claim/gap/experiment có cấu trúc và kiểm chứng được với evidence.
**Quyết định:** cột `research_tasks.research_model` (Text, JSON, nullable); validator ở `evidence/claim_validator.py`. Không tạo bảng riêng ở giai đoạn này.
**Hệ quả:** đơn giản, tương thích task cũ (NULL); không truy vấn được theo claim bằng SQL — nếu cần, viết ADR mới để chuẩn hóa thành bảng.
