---
name: add-migration
description: Thêm cột/bảng DB bằng Alembic và đồng bộ model, schema, doc. Dùng mỗi khi đổi cấu trúc PostgreSQL.
---
# Thêm migration
1. Sửa model trong `app/api/models/*.py` (cột mới `nullable=True` hoặc có default).
2. Tạo `migrations/versions/NNNN_<mô_tả>.py` với số liền sau bản mới nhất (xem `ls migrations/versions`); `down_revision` trỏ bản trước; viết cả `upgrade` và `downgrade`.
3. Cập nhật `app/core/schemas.py` nếu field lộ ra API; đảm bảo bản ghi cũ (giá trị NULL) vẫn đọc được.
4. Cập nhật `docs/database-schema.md` (thực thể + lịch sử migration).
5. Test: `app/api/tests/test_models.py` hoặc test route liên quan.
6. KHÔNG tự chạy `alembic upgrade head` trên DB dev; đưa lệnh cho người dùng: `! alembic upgrade head` (kiểm cả `downgrade -1`).
