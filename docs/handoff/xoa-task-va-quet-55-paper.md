# Bàn giao: xóa task + References phủ đủ 55 paper (2026-11-08) — ĐÃ XONG phần code

## Đã làm
- Không có task research nào đang chạy (celery active/reserved rỗng, research_queue=0, unacked=0). Đã xóa 3 dòng `research_tasks` failed, giữ 3 dòng done.
- Giữ 24 message `process_paper` trong `upload_queue`: đây là ingest của 24 paper `pending` (DB 31 done + 24 pending; Qdrant 31 paper; PDF và catalog đều 55).
- Nguyên nhân thiếu References: chunk trung bình khoảng 790 token, nên 55 paper cần khoảng 44k token, vượt `CONTEXT_TOKEN_LIMIT=22000` và bị `build_context` cắt bớt.
  Đã sửa `app/ai/context_builder.py` (`_fit_first_chunks`): khi diversify, chia đều ngân sách cho từng paper (tối thiểu 150 token) và cắt chunk đầu theo ranh giới từ. Thêm 2 test vào `app/ai/tests/test_context_builder.py`. Đã chạy `pytest app/agent app/ai`: pass.
- README: worker đổi sang `-Q upload_queue,research_queue`. Đã cập nhật docs/architecture.md và docs/implementation-plan.md.

## Đang chờ
- Người dùng chạy theo README: worker nạp 24 paper, rồi kiểm tra `papers` là `done|55` trước khi gửi task research.
- Đọc survey mới: References đủ 55 paper, quality gate không còn cảnh báo `độ phủ kho`.
- `ruff check app/ai` còn lỗi I001 có sẵn từ trước ở `app/ai/tests/test_llm_registry.py`, không liên quan thay đổi này.
