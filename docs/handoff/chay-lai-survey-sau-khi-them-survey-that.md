# Việc cần làm: chạy lại survey sau khi thêm survey thật (soạn 2026-11-10, chạy chiều tối)

Bối cảnh: `paper_fd149553_test3.pdf` chỉ là render lại báo cáo CŨ `fd149553`, chưa phải lượt research mới → mọi kiểm tra mới chưa tác dụng. Chi tiết nguyên nhân: `docs/decisions/0009-kiem-tra-nhat-quan-sau-danh-gia-fd149553.md`.

## Trạng thái hiện tại
- Code: gate chặn (độ phủ kho, số trục, ledger, prior-survey) + cảnh báo (novelty, kết luận khái quát `check_overgeneralization`, năm reference lệch `check_reference_years`). `pytest app/agent` pass. Chưa commit.
- Đã tải vào `data/papers_brain/`: `survey_dl_brain_tumor_segmentation_2007.09479.pdf` (arXiv), `survey_multimodal_mri_tumor_seg_frontiers_2024.pdf` (Frontiers 2024).
- Chưa có: survey #4 *Overview of Multi-Modal Brain Tumor MR Image Segmentation* (Healthcare 2021) — PMC/MDPI chặn bot; tải tay từ https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8392341/ rồi bỏ vào `data/papers_brain/`.
- Survey #2 (Zhou, Ruan & Hu, CMIG 2023, PubMed 36584536) — survey chuyên missing-modality, giá trị nhất; chưa tìm được bản mở. Thử tải tay / xin qua thư viện.
- `data/papers_brain` đang có 56 file (bàn giao cũ ghi 50) → kiểm tra 4 file dư là gì trước khi nhập.

## Checklist (làm theo thứ tự; lệnh app thật tự gõ bằng `! <lệnh>`)
1. [ ] Bỏ nốt PDF #4 (và #2 nếu có) vào `data/papers_brain/`.
2. [ ] Thêm metadata (tiêu đề, năm, tác giả, venue) của các survey mới vào `data/papers_brain/catalog.json` — nếu thiếu, References sẽ hiện UUID/"Anonymous" và `check_prior_survey_claims` không nhận ra tiêu đề survey.
3. [ ] Đảm bảo `redis-cli llen upload_queue` = 0 và `llen research_queue` = 0; chạy worker nạp: `celery -A app.workers.celery_app worker -Q upload_queue -l info`. Nạp paper mới (`process_paper.delay(id)` theo `docs/runbook-brain-tumor-survey.md` dòng 35) rồi chờ `done`.
4. [ ] Gán vào workspace "MRI brain" (id `2238e849-15d9-42ff-972a-a5c826ae582a`):
   `python scripts/assign_papers.py --dir data/papers_brain --email <email-user-sở-hữu> --workspace "MRI brain"` (dry-run) rồi thêm `--apply`.
5. [ ] Kiểm tra kho: `done` ≥ 52, vẫn < 80 (`full_corpus_coverage_limit`) để chế độ cite-hết bật. Nếu vector mất: `python scripts/reindex_papers.py --apply`.
6. [ ] Migration 0009 (cột `workspace_id`) phải đã chạy trên DB thật: `alembic upgrade head` (chỉ khi chắc đây là DB đích).
7. [ ] **Restart celery worker** (dừng worker nạp), chạy worker research: `celery -A app.workers.celery_app worker -Q research_queue -l info` — không để nạp và research chạy xen nhau. Sau đó khởi chạy research với body `/tmp/req2.json` (đã có `workspace_id`; nếu `/tmp` bị dọn: `question` + `workspace_id` của "MRI brain").
8. [ ] Xuất PDF: `GET /research/<task_id>/pdf` (hoặc `scripts/export_academic_pdf.py`) → lưu `data/exports/paper_<id>_test4.pdf`; đọc `data/papers_brain/validation/<task_id>.json` (`passed`, `blocking`, `warnings`).

## Tiêu chí đạt khi xem bản mới
- Table 2 (so sánh survey) có ≥3 survey thật, phân biệt: tổng quan BraTS / synthesis / missing-modality segmentation; Introduction không gọi [3],[6] là survey nếu tiêu đề không phải survey.
- Một con số trục (bốn) nhất quán ở Abstract/Contributions/§3.1; evaluation coverage là "dimension" riêng.
- Không còn mâu thuẫn "262 records có cấu hình missing-modality" vs "không trích xuất missing-modality"; phân 3 nhóm dữ liệu (full / missing có cấu hình / kết quả 15 subsets từ [23]).
- Không còn tham chiếu Table/Figure lệch số; không có `[n]` vượt số reference; năm reference không lệch.
- Kết luận "mmFormer/attention fusion tốt nhất" có giới hạn phạm vi [23]; số LCKD không dùng để kết luận chung về distillation.

## Chưa làm trong code (nếu bản mới vẫn lỗi)
- Tách bảng taxonomy thành 4 nhóm (segmentation / missing-modality learning / synthesis / dataset-benchmark) + cột "evidence for assignment" bằng kiểm tra tất định (hiện chỉ có quy tắc prompt).
- Bổ sung min/max Dice theo subset cạnh mean theo cardinality; giữ cảnh báo comparability cạnh mọi kết luận xếp hạng (Bảng 7).
- Cập nhật `docs/architecture.md` cho `check_overgeneralization`, `check_reference_years` và nhóm kiểm tra nhất quán mới.
