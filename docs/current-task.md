# Task đang thực hiện

> Cập nhật tệp này MỖI KHI đổi task. Claude đọc nó trước khi code. Trống/lỗi thời -> hỏi người dùng.

## Task hiện tại: đánh giá Q1/Q2 lần 3 — lớp Scientific Consistency QA + bằng chứng truy vết được
Người dùng: "đọc đánh giá và tiếp tục cải tiến hệ thống". Chỉ làm phần của HỆ THỐNG; tìm kiếm CSDL/sàng lọc/novelty thật là việc người dùng,
hệ thống chỉ được dùng đúng số liệu người dùng khai báo.

| # | Việc | Tệp |
|---|---|---|
| A | Chuẩn hóa modality chặt: đồng nghĩa (T1ce, T1Gd, T1 post-contrast…), thiếu 1/2/3 modality, cách viết "only X"/"available X"; ma trận 15 tập (giá trị hoặc NR, ghi nhóm bối cảnh; khác nhóm = không so sánh được) thay bảng dài | `evidence/quant_analysis.py` |
| B | Hồ sơ nghiên cứu theo câu nguyên văn (không LLM): external validation, cross-validation, patient-wise split, giao thức thiếu modality, uncertainty/calibration, code; "Yes (p. X)" hoặc NR = không thấy trong đoạn đã truy xuất | `evidence/study_profile.py`, `quant_analysis.study_profile_table` |
| C | Scientific Consistency QA: claim phủ định trái với record, thuật ngữ lẫn (T1c/T1ce), phạm vi năm Abstract vượt References, overclaim ở Abstract/Conclusion, một nguồn ở nhiều nhóm cùng trục taxonomy, bảng có NR mà không định nghĩa | `evidence/science_qa.py`, `quality_gate.py` |
| D | Giao thức review do người dùng khai báo `<upload_dir>/review_protocol.json`: kiểm tra số học PRISMA, đưa nguyên văn vào REVIEW FACTS, sơ đồ PRISMA tất định; không có tệp → giữ mô tả "retrieval coverage" | `evidence/review_protocol.py`, `synthesize_node._review_facts`, `consistency_check.check_review_claims` |
| E | Novelty/định vị: liệt kê survey có trong corpus; 0 survey → cảnh báo không chứng minh được novelty; prompt bảng định vị so với survey trước; mục 6.2 clinical reliability theo từng chiều | `synthesize_node.py`, `quality_gate.py` |

Không làm: citation entailment bằng LLM (chi phí + cần đánh giá riêng), tự dựng PRISMA/2 reviewer, tự tải paper.

## Tiêu chí hoàn thành
- [x] A–E có code + test; `pytest app/agent app/pipeline` pass; ruff không thêm lỗi
- [x] Doc: architecture, `docs/review-protocol.md` (mẫu tệp khai báo)
- [ ] Chạy lại survey thật (người dùng restart worker)

---

## Task trước (đã xong code): sửa lỗi hệ thống theo đánh giá Q1/Q2 lần 2
 (bản "Fusion Strategies and Missing-Modality Robustness…", `survey_58ad3caf`)
Người dùng: "đọc đánh giá, phải cải tiến hệ thống để chuẩn hóa đăng lên tạp chí Q1, Q2". Chỉ sửa lỗi do HỆ THỐNG sinh ra;
việc nghiên cứu thật (mở rộng corpus, PRISMA, 2 người đánh giá độc lập) là của người dùng, không tự dựng.

| # | Lỗi trong bài đánh giá | Nguyên nhân gốc | Sửa |
|---|---|---|---|
| 1 | Nói "không có degradation matrix" nhưng có bảng ablation thiếu modality | extractor ghi "Missing T1" vào `variant`, `_modality_groups` bỏ qua record có variant → `evidence_limits` báo 0 nhóm | suy tập modality từ variant "Missing/w/o X"; EVIDENCE LIMITS tách 3 mức (ablation từng modality / ma trận 15 tập / ma trận so sánh liên nghiên cứu) |
| 2 | Citation `[1]–[1]`, `[1]–[14]` cho cả corpus | không gộp dải trùng; LLM trích cả corpus cho câu nói về chính bài review | `citation_cleaner` gộp `[n]–[n]`; prompt cấm trích dẫn cho câu nói về corpus |
| 3 | Dòng "PaperAI Automated Research Protocol / Open-Source Automated Science Initiative" ở trang đầu | prompt + sanitizer chèn placeholder, renderer HTML không lọc | bỏ placeholder tại nguồn |
| 4 | Caption Figure tách khỏi hình, số Figure lệch | LLM viết "**Figure N: …**" trước khối ```image/chart (khối có caption riêng, renderer tự đánh số) | sanitizer xóa dòng caption thừa (dùng làm caption nếu khối chưa có) |
| 5 | Taxonomy tự nhận "orthogonal"; RQ đòi số liệu không có; bảng trùng; trộn đơn vị Dice; mô tả nhiều hơn phân tích | prompt | prompt: multi-axis framework, mỗi phương pháp 1 họ chính; RQ phải trả lời được bằng EVIDENCE LIMITS; mục 4.5 phân tích so sánh phê phán; 6.4 gap/vì sao/cách đánh giá; một đơn vị Dice mỗi cột; không lặp bảng số |
| 6 | Thiếu bảng đặc điểm nghiên cứu/chất lượng bằng chứng | chưa có | `study_profile_table` tất định từ `ResultRecord` (NR khi thiếu) |
| 7 | Trộn Dice tỷ lệ và % trong một cột | không có kiểm tra | `consistency_check`: WARNING khi cột Dice trộn thang |
| 8 | Không giải thích 21/31 paper | REVIEW FACTS chỉ có số | REVIEW FACTS nêu số paper corpus không được truy xuất (thật) |

## Phạm vi được phép đổi
`app/agent/evidence/*`, `app/agent/format_sanitizer.py`, `app/pipeline/export/pdf_renderer.py` (lọc placeholder bản cũ), `app/agent/nodes/synthesize_node.py` (prompt survey, REVIEW FACTS), test tương ứng, `docs/architecture.md`.

## Không đổi
Pipeline nạp paper, retrieval, LLM gateway, DB/migration, frontend, `.env`.

## Tiêu chí hoàn thành
- [x] 8 mục trên có code + test
- [x] `pytest app/agent -q` + `app/pipeline` pass; `ruff check` không thêm lỗi mới
- [x] `docs/architecture.md` khớp
- [ ] Chạy lại survey thật (chờ người dùng)
