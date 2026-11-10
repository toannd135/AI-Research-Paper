# Bàn giao: kiểm tra nhất quán sau đánh giá survey fd149553 (2026-11-10)

## Đã xong
- Kho: workspace "MRI brain" (`2238e849-15d9-42ff-972a-a5c826ae582a`) chứa đúng 50 PDF của `data/papers_brain`; research phải gửi `workspace_id` này (file `/tmp/req2.json`). Lượt chạy `fd149553` cite đủ 50 reference.
- `app/agent/evidence/quality_gate.py`: độ phủ kho (kho ≤ `full_corpus_coverage_limit`=80) thiếu paper → **lỗi chặn**.
- `app/agent/evidence/consistency_check.py` (mới, nối vào gate; có test trong `test_quality_gate.py`):
  - `check_axis_count` (số trục taxonomy nhất quán) → chặn
  - `check_ledger_claims` / `check_limitation_denial` (record có/không có missing-modality phải khớp sổ cái) → chặn
  - `check_prior_survey_claims` ([n] gọi là prior survey phải có tiêu đề survey) → chặn
  - `check_novelty_claims` ("first comprehensive…") → cảnh báo
- `synthesize_node.py`: thêm quy tắc prompt (trục, ledger, phạm vi bằng chứng 1 nghiên cứu, gán nhãn taxonomy, không "first").
- `pdf_renderer.py`: bỏ ảnh hỏng + đánh số lại Figure và tham chiếu (`_drop_dead_images`).
- `chart_scientific.py`: timeline hết chồng nhãn.
- `pytest app/agent app/pipeline` pass.

## Phát hiện mới (chưa sửa trong báo cáo)
Kho chỉ có **1 survey thật**: [8] Diffusion Models… Comprehensive Survey. Báo cáo `fd149553` gọi [3] (Ensembles of Multiple Models…) và [6] (Missing MRI Pulse Sequence Synthesis GAN) là "prior surveys" — sai; gate mới đã bắt được.

## Đang chờ
- Chạy lại research với `/tmp/req2.json` + restart celery worker để các kiểm tra mới có tác dụng khi sinh bài (báo cáo cũ vẫn còn mâu thuẫn).
- Quyết định: bảng so sánh survey trước cần survey thật; kho chỉ có 1 → hạ claim novelty hoặc thêm survey vào `papers_brain`.
- Chưa làm: đối chiếu "Table N" nhắc trong thân bài với nội dung bảng; metadata reference (vd. [37]); trích số liệu missing-modality cho ma trận suy giảm.
- `docs/current-task.md` và `docs/architecture.md` chưa cập nhật cho nhóm kiểm tra mới.
