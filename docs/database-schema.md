# Database schema (PostgreSQL, Alembic)

Model ở `app/api/models/`. Migration ở `migrations/versions/` (hiện tới `0008_research_model`). Mọi PK là UUID string(36).

## Thực thể
- **users**: id, email (unique), full_name, password_hash, role (`user|admin`), is_active, created_at
- **papers**: id, filename, file_path, user_id (idx), content_hash (unique, chống trùng), status, error, created_at
- **research_tasks**: id, user_id (idx), question, clarification_answers (JSON text), refined_question, audience, field, contribution_type, target_venue, user_results, **research_model** (JSON text), status, report, citations (JSON text), error, created_at
- **conversations**: id, user_id (idx), paper_id, research_task_id (idx), created_at
- **messages**: id, conversation_id -> conversations.id, role, content, citations (JSON text), created_at

## Quan hệ
users 1—N papers / research_tasks / conversations (qua `user_id`, không FK cứng, nullable cho dữ liệu cũ) · conversations 1—N messages · conversations N—1 paper hoặc research_task (tùy chọn).

## Vector store
Qdrant collection `paper_chunks`: payload gồm paper_id, chunk_index, page, section, text. Xóa paper phải xóa vector tương ứng.

## Lịch sử migration
0001 schema đầu · 0002 research_tasks · 0003 conversation↔research · 0004 citations cho message · 0005 users & ownership · 0006 content_hash · 0007 audience/field · 0008 research_model (+contribution_type, target_venue, user_results).

## Quy tắc migration
1. `alembic revision -m "<mô tả>"`, số thứ tự liên tiếp, có `downgrade` đúng.
2. Cột mới: nullable hoặc `server_default`; không làm mất dữ liệu cũ.
3. Cập nhật model + `schemas.py` + tệp này; thêm test model (`app/api/tests/test_models.py`).
4. Chỉ chạy `alembic upgrade head` trên DB dev khi người dùng đồng ý.
