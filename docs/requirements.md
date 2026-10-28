# Yêu cầu nghiệp vụ

## Phạm vi
Người dùng (giảng viên/sinh viên/người đi làm) đặt câu hỏi nghiên cứu, hệ thống tìm bằng chứng từ paper đã upload + OpenAlex rồi viết bài báo có trích dẫn kiểm chứng được.

## Chức năng
| ID | Yêu cầu | Acceptance criteria |
|---|---|---|
| R1 | Upload & xử lý PDF | file ≤ `max_upload_mb`; trùng hash bị chặn; status chuyển pending->processing->done/failed kèm `error` |
| R2 | Chat hỏi đáp paper | trả lời kèm citations (paper, trang, trích đoạn); lưu lịch sử theo user |
| R3 | Research task | `POST /research` trả task id; poll tới `done` (hoặc `failed` kèm `error`); thiếu thông tin -> trả câu hỏi làm rõ |
| R4 | Citation đáng tin | mọi citation trong report tồn tại trong nguồn; hallucination detector không báo lỗi nặng |
| R5 | Đa đối tượng/lĩnh vực | `audience` (3), `field` (6) đổi khung và giọng văn (xem `app/agent/profiles.py`) |
| R6 | Ảnh/biểu đồ có nguồn | ảnh trích từ PDF kèm "Source:"; ref lạ/trùng bị bỏ + log WARNING |
| R7 | Research Knowledge Model | claim gắn evidence; claim không có bằng chứng bị đánh dấu (`claim_validator`) |
| R8 | Xuất bản | PDF (Chromium 2 cột, 1 cột; Typst), LaTeX, BibTeX |
| R9 | Auth & phân quyền | JWT; user chỉ thấy dữ liệu của mình; admin quản lý user |

## Phi chức năng
- Research task chạy nền, không chặn request; chịu được worker restart (`acks_late`).
- Lỗi LLM/nhà cung cấp: retry + fallback, không làm hỏng cả task nếu có thể suy giảm.
- Không lộ khóa API; mật khẩu băm; `jwt_secret` mặc định bị chặn ngoài môi trường local.

## Ngoài phạm vi (hiện tại)
Dữ liệu mở World Bank/OWID, chart scatter/box, ảnh ngoài có giấy phép, trích bảng số từ PDF (P1 trong `docs/handoff/paper-da-doi-tuong.md`).
