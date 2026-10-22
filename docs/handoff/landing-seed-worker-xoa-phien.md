# Bàn giao: landing page, tự nhập PDF, sửa worker OOM, xoá phiên

## Mục tiêu
Làm đẹp landing page, tự nhập PDF có sẵn lúc khởi động, sửa tác vụ nghiên cứu kẹt 92%, xoá phiên phải xoá sạch.

## Nhánh/trạng thái git
- `feature/login`. TẤT CẢ thay đổi dưới đây CHƯA commit, CHƯA push (frontend là repo con).

## Đã xong (chưa commit)
- Landing: hero (badge pill, nền chấm, mockup sidebar navy + con trỏ giả), bento, FAQ, nhãn tag.
- Migration `0006` (`papers.content_hash`) + `app/pipeline/seed.py` tự nhập PDF trong `data/papers`; cờ `AUTO_IMPORT_PAPERS`.
- Nguyên nhân kẹt: không có Celery worker, rồi `retrieve_evidence` chạy 5 luồng nạp BGE-M3 cùng lúc (OOM, ~10 GB RAM). Sửa bằng `load_once` (có test).
- Xoá phiên: dọn bản lưu tạm + RESET, không stash lại phiên vừa xoá.

## Quyết định đã chốt
- Seed = PDF trong `data/papers`, chạy lúc app khởi động, idempotent (theo đường dẫn + sha256).
- Sau khi xoá phiên đang mở: chuyển sang phiên mới trống (giả định, chưa xác nhận).
- Không dùng logo thật cho arXiv/IEEE/Crossref, không bịa số liệu ("50+ trang/phút").

## Tệp quan trọng
- `frontend/src/home/LandingPage.tsx`, `LandingPage.css`
- `app/pipeline/seed.py`, `migrations/versions/0006_paper_content_hash.py`, `app/main.py:21-45`
- `app/ai/device.py` (`load_once`), `app/ai/embedding/service.py:17`, `app/ai/retrieval/reranker.py:13`
- `frontend/src/client/state/useAppController.ts:588-612` (`removeResearchTask`)

## Việc còn lại
1. Chạy `alembic upgrade head`, khởi động lại worker (đặt `EMBEDDING_DEVICE=cpu` hoặc `-c 2`), thử câu hỏi mới.
2. Tác vụ `66c646ab` kẹt `processing`: đặt `failed` hoặc tạo lại.
3. Chụp Playwright landing 375/768/1440px; commit theo nhóm.
4. Tuỳ chọn: ghi bước tiến độ thật từ backend; huỷ Celery task khi xoá phiên đang chạy.

## Đang chờ
Người dùng khởi động lại worker và báo kết quả bước "Tìm kiếm kho nội bộ & OpenAlex"; xác nhận hành vi sau khi xoá phiên.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app/ai app/agent app/api/tests app/pipeline/tests -q`
- `cd frontend && npx tsc -b && npx eslint src && npm run build`
- `venv/bin/celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info`
