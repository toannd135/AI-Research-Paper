# ADR 0009 — Kiểm tra nhất quán + độ phủ kho sau đánh giá survey `fd149553` (2026-11-10)

## Bối cảnh
Lượt chạy `fd149553` (kho "MRI brain", 50 PDF) cite đủ 50 reference nhưng đánh giá phát hiện bài tự mâu thuẫn và nói sai về chính kho.

## Vấn đề đúc rút (nguyên nhân gốc, không chỉ triệu chứng)
| # | Lỗi quan sát | Nguyên nhân gốc | Cách chặn |
|---|---|---|---|
| 1 | Số trục taxonomy nêu mỗi chỗ một khác | LLM viết từng mục độc lập, không có "nguồn sự thật" chung | `check_axis_count` (chặn) + prompt: chốt số trục một lần |
| 2 | Khẳng định "không paper nào báo missing-modality" / ngược lại, trái sổ cái | Câu nói về corpus không đối chiếu ledger | `check_ledger_claims`, `check_limitation_denial` (chặn) |
| 3 | [3], [6] bị gọi là "prior survey" | LLM suy từ chủ đề, không từ tiêu đề; kho chỉ có 1 survey thật ([8]) | `check_prior_survey_claims` (chặn: [n] phải có tiêu đề survey) |
| 4 | "First comprehensive…" không có cơ sở | Văn phong quảng bá của LLM | `check_novelty_claims` (cảnh báo) + prompt cấm "first" |
| 5 | Kho thiếu paper nhưng gate vẫn qua | Độ phủ chỉ là cảnh báo | Kho ≤ `full_corpus_coverage_limit` (80) thiếu paper → **lỗi chặn** |
| 6 | Kết luận chung từ 1 nghiên cứu | Không nêu phạm vi bằng chứng | Prompt: phạm vi bằng chứng 1 nghiên cứu, gán nhãn taxonomy là của tác giả bài |
| 7 | PDF có ảnh hỏng, Figure đánh số lệch | Ảnh chết vẫn được đếm | `_drop_dead_images` đánh số lại Figure + tham chiếu |
| 8 | Timeline chồng nhãn | Không chống va chạm | `chart_scientific.py` giãn nhãn |

## Bài học quy trình
- Lỗi do LLM "bịa nhận định về corpus" → đừng sửa bằng prompt đơn thuần; thêm kiểm tra tất định đối chiếu dữ liệu (ledger, tiêu đề, số đếm) và **chặn** thay vì cảnh báo.
- Sửa gate không đổi bài đã sinh: phải restart celery worker rồi chạy lại research (đúng `workspace_id`) mới thấy hiệu lực.
- Kiểm tra đầu vào trước: kho phải có đủ loại nguồn mà bài định nói (survey thật, bảng so sánh cần ≥2 survey). Thiếu → hạ claim, không để LLM tự lấp.

## Còn tồn đọng
- Bảng so sánh survey trước cần survey thật (kho 1 → thêm 3–4 survey vào `papers_brain`).
- Đối chiếu "Table N" nhắc trong thân bài với nội dung bảng; metadata reference (vd. [37]); trích số liệu missing-modality cho ma trận suy giảm.
