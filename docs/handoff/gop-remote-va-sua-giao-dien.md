# Bàn giao: gộp remote feature/agent + sửa giao diện

## Mục tiêu
Gộp `origin/feature/agent` lấy code remote làm chuẩn; chỉnh màu giao diện; sửa mất tin nhắn khi đổi phiên.

## Nhánh/trạng thái git
- Nhánh `feature/agent`, merge ĐÃ commit (b86e17c), CHƯA push.
- 9 file xung đột lấy `--theirs`; `test_format_sanitizer.py`, `test_typst_renderer.py` lấy từ remote.
- `frontend` là thư mục con riêng (repo/submodule): thay đổi giao diện nằm ở đó, chưa commit.

## Đã xong
- Cài môi trường local: playwright 1.64.0, chromium, `npm ci` trong `app/pipeline/export/assets`.
- Test agent + llm registry + route chat/research: 131 pass.
- Đổi màu theo góp ý: `frontend/src/index.css:2-14`, `ClientApp.css` (.sidebar-new-btn ~2134), `GraphView.tsx:28`.
- Lưu hỏi đáp theo phiên nghiên cứu: `frontend/src/client/state/useAppController.ts` (loadSavedChat/saveChatTurn, openResearchTask).

## Quyết định đã chốt
- Xung đột: lấy nguyên file remote (mất sửa local trong 9 file đó).
- Lưu hỏi đáp bằng localStorage theo task id, không đổi backend.

## Tệp quan trọng
- `frontend/src/client/state/appReducer.ts:198` LOAD_RESEARCH_TASK (dựng lại phiên chỉ từ câu hỏi + tóm tắt).
- `app/api/routes/chat.py` (bản remote).

## Việc còn lại
1. Push nhánh khi sẵn sàng.
2. Thử tay: chat trong phiên A, sang B, quay lại A.
3. Cân nhắc lưu hội thoại phía server (liên kết ResearchTask–Conversation).
4. Commit riêng trong `frontend`.

## Đang chờ
Người dùng xác nhận giao diện màu và lỗi mất chat đã ổn.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app/agent/tests app/ai/tests/test_llm_registry.py app/api/tests/test_chat_route.py app/api/tests/test_research_route.py -q`
- `cd frontend && npx tsc -b`
- Chạy API bằng venv: `venv/bin/uvicorn app.main:app --reload`
