# 0004 — Cột JSON lưu dạng Text, ID là UUID string, ownership qua user_id không FK
Trạng thái: accepted
**Bối cảnh:** dữ liệu cũ chưa có user, cần migration đơn giản, chạy được trên nhiều DB.
**Quyết định:** citations/clarification/research_model là Text JSON; `user_id` nullable có index, kiểm quyền ở tầng route (`can_access`); user không thấy dữ liệu người khác (404).
**Hệ quả:** phải kiểm quyền thủ công ở mọi route mới; không có ràng buộc toàn vẹn ở DB cho `user_id`.
