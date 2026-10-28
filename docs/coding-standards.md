# Quy tắc coding

## Python (3.11)
- Ruff cấu hình trong `pyproject.toml` (line 120; E,F,W,I,B,UP,SIM,RUF,PIE,TRY). Chạy `ruff check app tests` trước khi báo xong.
- Type hints kiểu hiện đại: `str | None`, `list[str]`; schema ở `app/core/schemas.py` (Pydantic v2).
- Tên: module/hàm `snake_case`, class `PascalCase`, hằng `UPPER_SNAKE`. Node agent: `<tên>_node(state, llm=None)`.
- Docstring/comment/log/thông báo lỗi người dùng thấy: tiếng Việt, ngắn, giải thích *vì sao*.
- Import tuyệt đối từ `app.`; không import vòng; `agent` không import `api`.
- Cấu hình chỉ qua `get_settings()`; không `os.getenv` rải rác; không hard-code khóa/URL.

## Xử lý lỗi
- Không `except Exception: pass`. Bắt đúng loại hoặc `logger.exception(...)` rồi suy giảm có chủ đích (xem `main.py` `_seed_admin`).
- API: `HTTPException` với status đúng + `detail` tiếng Việt; không rò stack trace (đã có `unhandled_exception_handler`).
- Lỗi LLM/mạng: dùng retry của gateway; node agent phải có đường fallback (`nodes/fallback.py`), không làm sập graph.
- Dữ liệu LLM trả về: parse bằng `json_utils`, luôn giả định có thể sai định dạng.

## DB
- Mọi đổi schema qua Alembic (`docs/database-schema.md`). Cột mới nullable hoặc có default để không vỡ dữ liệu cũ.
- ID là UUID string(36); thời gian `datetime.now(UTC)` timezone-aware.

## Test
Xem `docs/testing-strategy.md`. Code mới có test; sửa bug có test tái hiện.

## Frontend
Theo `frontend/Claude.md`; `npm run check` phải pass.

## Git
Commit nhỏ, thông điệp tiếng Việt/Anh ngắn, một mục đích. Không commit `.env`, `data/`, `*.pdf` mẫu.
