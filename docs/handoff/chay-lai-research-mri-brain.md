# Bàn giao: chạy lại research MRI brain (2026-11-11)

## Mục tiêu
Sinh lại paper bằng hệ thống mới (việc 1–7, xem `docs/handoff/paper-review-export.md`) trên đúng 52 paper đã nạp, xuất PDF LaTeX để so với test5/test6.

## Nhánh/trạng thái git
- paperai: CHƯA commit toàn bộ việc 1–7 + LaTeX. Không tự commit.
- frontend: commit 4332f84 chưa push.

## Đã xong (chưa commit)
- Việc 1–7 trong `docs/implementation-plan.md` (mục "Sửa hệ thống theo đánh giá reviewer…"), `pytest app` xanh.
- Bản thử áp repair lên bài cũ: `data/exports/paper_5a736250_test6_latex.pdf`.
- Đã kiểm tra DB: workspace `72166c1a-9db1-41e1-904d-26a3e5f326c9` có 52 paper `done`; task gốc `5a736250-b275-45b0-a477-31b94bc29335` `done`; task `865b8699-0509-4011-8039-066e8ed6ea50` (cùng câu hỏi/workspace) kẹt `processing` (bị ngắt phiên trước).

## Quyết định đã chốt
- Tác giả trang đầu = PaperAI, không bịa email.
- Chỉ dùng 52 paper của workspace trên; 26 paper không workspace không đụng.

## Tệp quan trọng
- `app/pipeline/tasks.py:120` — `run_research(task_id)`.
- `scripts/host_env.sh` — env host (DB localhost:5433, redis 6380).
- `app/pipeline/export/latex_renderer.py` — `compile_latex_pdf`.
- Script xuất mẫu: `/tmp/claude-1000/-mnt-01DC7E1E309A75E0-CODE-BTL-PTHTTM/3a45b902-3ee1-4fa4-8742-2c58cb571e43/scratchpad/export_test6.py`.

## Việc còn lại
1. (Tiếp theo) Cách 1 — đề xuất: đặt task 865b8699 về `pending`, chạy nền `source scripts/host_env.sh; venv/bin/python -c "from app.pipeline.tasks import run_research; run_research('865b8699-0509-4011-8039-066e8ed6ea50')"` > log scratchpad. Cách 2: người dùng restart celery worker rồi tạo task mới qua API cùng question + workspace_id.
2. Xuất `data/exports/paper_<id>_test7_latex.pdf`, xem `validation/<id>.json` (lỗi blocking), so với test6.
3. Sau đó: chuẩn hoá references (plan việc 7 phần sau, `app/pipeline/export/bibliography.py`).

## Đang chờ
- Người dùng xác nhận chạy (gọi LLM thật, hàng chục phút, tốn quota) và chọn cách 1 hay 2.
- Người dùng quyết định commit paperai; push frontend 4332f84.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app -q -p no:cacheprovider`
- `source scripts/host_env.sh; venv/bin/python -c "..."` truy vấn status task 865b8699
