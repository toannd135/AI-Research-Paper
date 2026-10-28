---
paths:
  - "app/**/*.py"
  - "tests/**/*.py"
---
# Backend Python
- Theo `docs/coding-standards.md`; chạy `ruff check` trên tệp đã sửa.
- Không import `app.api` từ `app.agent`/`app.ai`; cấu hình qua `get_settings()`.
- Không `except Exception` trần; log bằng `logger.exception` hoặc xử lý có chủ đích.
- Test không gọi LLM/mạng thật; dùng fake gateway.
- Thông báo cho người dùng, log, docstring: tiếng Việt.
