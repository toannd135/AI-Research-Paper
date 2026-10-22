# Bàn giao: đăng nhập/phân quyền xong, còn chỉnh giao diện chat

## Mục tiêu
1. (Xong) Thêm login/logout/phân quyền admin-user, dữ liệu tách theo người dùng.
2. (Mới, chưa làm) Cải thiện giao diện theo góp ý bên dưới.

## Nhánh/trạng thái git
- `feature/agent`, merge remote đã commit (b86e17c), CHƯA push.
- CHƯA commit: toàn bộ backend (auth, migrations 0003-0005, route, test) và `frontend` (repo con riêng).
- DB đã ở revision 0005. Tài khoản: `admin`/`admin` (admin), `toannd`/`b23dccn831` (user). Chỉ dùng local.

## Đã xong (chưa commit)
- Backend: `app/api/routes/auth.py`, `app/api/deps.py`, `app/core/security.py`, `app/core/scope.py`, model `user.py`; route papers/chat/research/sources yêu cầu token, lọc theo `user_id`; PDF nhận `?access_token=`.
- Frontend: `frontend/src/auth/*` (AuthContext, LoginPage, RequireAuth), `main.tsx` guard, Sidebar có đăng xuất, `UsersPage` dùng API thật.
- Test API qua; tsc/eslint sạch. Chưa thử tay trên trình duyệt.

## Quyết định đã chốt
- Vai trò: admin + user; email/tên + mật khẩu, JWT; dữ liệu cũ (user_id NULL) chỉ admin thấy.
- Lưu hội thoại ở Postgres; nháp phiên chưa có task lưu localStorage.

## Việc còn lại (góp ý giao diện của người dùng)
1. Thẻ "Research Specification" bị che/cắt: cho expand/collapse hoặc cuộn, hiện đủ nội dung.
2. Tên phiên ở Sidebar quá dài, nút xoá đè mép: tự rút gọn thành tên ngắn (vd dùng LLM hoặc cắt theo từ), sửa layout nút xoá.
3. Tăng độ tương phản chữ/icon xám nhạt ở sidebar (chế độ tối, ô "Tìm trong lịch sử").
4. Dropdown chọn model nổi phía trên ô nhập: đưa vào trong input bar hoặc lên Header.
Tệp gợi ý: `frontend/src/client/components/Sidebar.tsx`, `ClientApp.css`, `chat/ChatView.tsx`, component specification.

## Đang chờ
Người dùng thử đăng nhập và xác nhận auth hoạt động; quyết định có commit/push chưa.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app/api/tests -q`
- `cd frontend && npx tsc -b && npx eslint src`
- API: `venv/bin/uvicorn app.main:app --reload`
