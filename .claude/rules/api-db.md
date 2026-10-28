---
paths:
  - "app/api/**/*.py"
  - "app/core/schemas.py"
  - "migrations/**/*.py"
---
# API & DB
- Route mới: `Depends(get_current_user)` + kiểm `can_access`; không có quyền -> 404.
- Đổi schema DB chỉ qua Alembic (xem skill `add-migration`); cột mới nullable/có default.
- Đổi response/request -> cập nhật `docs/api-contracts.md`, `docs/database-schema.md`, `frontend/src/types.ts`.
- Không chạy `alembic upgrade` trên DB thật khi chưa được đồng ý.
