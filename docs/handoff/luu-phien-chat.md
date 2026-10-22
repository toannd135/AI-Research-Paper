# Bàn giao: lưu phiên chat / sidebar

## Mục tiêu
Phiên chat không mất khi bấm qua lại phiên hoặc F5; phiên mới hiện ở sidebar ngay.

## Nhánh/trạng thái git
- `feature/agent`, merge remote đã commit (b86e17c), CHƯA push.
- CHƯA commit: backend (chat.py, conversation.py, schemas.py, test_chat_route.py, migrations 0003/0004) và `frontend` (repo con riêng).

## Đã xong (chưa commit)
- Backend: cột `conversations.research_task_id`, `messages.citations`; `GET /conversations/by-research/{task_id}`; `POST /chat` nhận `research_task_id`.
- Frontend: stash phiên đang chạy (bộ nhớ + localStorage), khôi phục khi mở lại; phiên nháp (`draft_*`) hiện ở sidebar sau F5; hỏi đáp nạp từ server.
- Đổi màu giao diện (index.css, ClientApp.css, GraphView.tsx).
- Test API qua; tsc/eslint sạch.

## Quyết định đã chốt
- Lưu hội thoại ở Postgres, không dùng SeaweedFS.
- Nháp chưa có task chỉ lưu localStorage (chưa lên server).

## Tệp quan trọng
- `app/api/routes/chat.py` (by-research, lưu citations)
- `migrations/versions/0003_*.py`, `0004_*.py`
- `frontend/src/client/state/useAppController.ts` (stashSession, openResearchTask, drafts)
- `frontend/src/client/state/appReducer.ts` (RESTORE_SESSION, draftId)

## Việc còn lại
1. Người dùng chạy `venv/bin/alembic upgrade head` (0004) rồi thử tay.
2. Commit backend và `frontend`; push.
3. Tuỳ chọn: tạo bản ghi phiên ở server từ tin nhắn đầu để nháp không phụ thuộc localStorage.

## Đang chờ
Người dùng thử: chat → F5 → sidebar còn phiên; qua lại phiên không mất.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app/api/tests -q`
- `cd frontend && npx tsc -b`
- API: `venv/bin/uvicorn app.main:app --reload`
