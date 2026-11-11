# Bàn giao: chạy lại research MRI brain (workspace v3) và xuất PDF nộp (2026-11-11)

## Mục tiêu
Sinh lại survey "multimodal MRI fusion & missing-modality, BraTS" từ 52 paper, xuất PDF LaTeX IEEE để nộp gấp.

## Nhánh/trạng thái git
- paperai `feature/normalization`, HEAD `6fbbb69`; ~20 tệp CHƯA commit, chưa push. Không tự commit.

## Đã xong (chưa commit)
- Chi tiết sửa export/gateway: xem `docs/handoff/latex-nop-bai-mri-brain.md`.
- 52 paper `done` chuyển sang workspace "MRI brain survey v3" `2e7beae0-65f5-4173-a638-c403f227f9d0` (`scripts/assign_papers.py`).
- PDF bản cũ: `data/exports/paper_5a736250_submission.pdf` (16 trang).

## Quyết định đã chốt
- Không tự điền Funding/CoI/Author Contributions.
- Fallback LLM: OpenRouter key1 → Groq → OpenRouter key2; 413/429 chuyển model kế.

## Tệp quan trọng
- `data/requests/mri_brain_survey.json` (câu hỏi + workspace_id v3).
- `app/pipeline/export/publication_prep.py:105` `prepare_report_for_latex`.
- `app/api/routes/research.py:214` endpoint `/pdf`.

## Việc còn lại
1. (Tiếp theo) Kiểm tra task `7af6af38-b6c9-4b61-b61a-992706e150d2` (processing từ 22:24, chưa lỗi lúc 22:35); xong → xuất PDF, kiểm Overfull/glyph.
2. Rút bài xuống 8–12 trang theo lựa chọn người dùng.

## Đang chờ
- Worker (tab người dùng) đang chạy `run_research` cho task trên; log chỉ ở terminal người dùng.
- Người dùng: chọn phần cắt; nội dung Funding/CoI/Author Contributions.

## Lệnh kiểm tra
- `docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc "select status,length(coalesce(report,'')),left(coalesce(error,''),150) from research_tasks where id='7af6af38-b6c9-4b61-b61a-992706e150d2'"`
- `source scripts/host_env.sh; celery -A app.workers.celery_app inspect active`
- Xuất: `curl -o data/exports/paper_7af6af38.pdf "localhost:8000/research/7af6af38-b6c9-4b61-b61a-992706e150d2/pdf?engine=latex&template=ieee&draft=true"` (cần token admin) hoặc nút tải trên UI.
