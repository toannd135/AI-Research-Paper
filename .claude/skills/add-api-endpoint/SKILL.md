---
name: add-api-endpoint
description: Thêm endpoint FastAPI mới (route, schema, phân quyền, test, doc, kiểu frontend).
---
# Thêm endpoint
1. Xem route cùng nhóm trong `app/api/routes/` để theo đúng mẫu (`router`, `Depends(get_db)`, `Depends(get_current_user)`).
2. Khai báo request/response Pydantic ở `app/core/schemas.py`; dùng `response_model`.
3. Phân quyền: chủ sở hữu hoặc admin (`can_access`), không có quyền -> 404; lỗi nghiệp vụ -> `HTTPException` với `detail` tiếng Việt.
4. Việc dài (>vài giây, LLM, embedding) -> Celery task, không chạy trong request.
5. Test trong `app/api/tests/test_<nhóm>_route.py`: thành công, 401, 404 quyền, dữ liệu sai.
6. Cập nhật `docs/api-contracts.md`; nếu frontend dùng -> `frontend/src/types.ts` và `frontend/src/client/api`.
7. Chạy skill `verify-change`.
