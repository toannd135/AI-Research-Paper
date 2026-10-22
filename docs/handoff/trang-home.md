# Bàn giao: thiết kế và làm trang /home

## Mục tiêu
Thiết kế và cài đặt trang /home (trang chủ sau đăng nhập) thân thiện với nhà nghiên cứu/sinh viên: hero có ô nhập + gợi ý nhanh, "Tiếp tục gần đây", "Bạn có thể làm gì", footer.

## Nhánh/trạng thái git
- `feature/agent`, CHƯA push. Backend auth + migrations 0003-0005 và `frontend` (repo con) vẫn CHƯA commit (xem dang-nhap-va-chinh-giao-dien.md).
- Phiên này chưa sửa mã nguồn nào, chỉ soạn prompt.

## Đã xong
- Khảo sát: `frontend/src/main.tsx` chỉ có route `/login`, `/admin/*`, `/*` (ClientApp); chưa có `/home`.
- Soạn xong prompt cho Claude Code (Template M): phạm vi sửa `frontend/src/main.tsx` + tệp mới `frontend/src/home/`, không thêm dependency, không đụng backend/auth/admin.

## Quyết định đã chốt
- "/home" = trang chủ sau đăng nhập (giả định, chưa được người dùng xác nhận).
- Stack: React 18, TS, Vite, Tailwind, shadcn/ui, react-router v6; theo `frontend/Claude.md` (không gradient tím, không bo tròn thẻ quá mức, mobile responsive).
- Tiếng Việt toàn bộ giao diện; đạt WCAG AA cả sáng/tối.

## Tệp quan trọng
- `frontend/src/main.tsx:20-42` (Routes)
- `frontend/src/client/components/InitialState.tsx`, `Sidebar.tsx`, `ClientApp.tsx`
- `frontend/src/theme.ts`, `frontend/src/client/api/`
- `frontend/Claude.md` (quy tắc thiết kế)

## Việc còn lại
1. Xác nhận "/home" là trang sau đăng nhập; chạy prompt (ghi hướng thị giác trước, rồi code).
2. Thêm route `/home`, đặt làm đích mặc định sau đăng nhập, giữ URL cũ.
3. Kiểm tra 375/768/1440px bằng Playwright, chụp ảnh.

## Đang chờ
Người dùng xác nhận ý nghĩa "/home" và chọn: chạy prompt ngay trong phiên này hay dán sang phiên mới.

## Lệnh kiểm tra
- `cd frontend && npx tsc -b && npx eslint src`
- `cd frontend && npm run build`
- `cd frontend && npm run dev` (rồi Playwright)
