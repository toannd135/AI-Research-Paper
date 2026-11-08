# Bàn giao: đánh giá Q1/Q2 lần 3 — Science QA + bằng chứng truy vết (2026-11-08)

Phạm vi: `docs/current-task.md` (A–E). Lần 2: `docs/handoff/danh-gia-q1-lan-2.md`.

## Đã làm (code + test; `pytest app/agent app/pipeline` pass; CHƯA chạy survey thật)
- A `quant_analysis`: modality đồng nghĩa + thiếu 1–3 + "X only"/"available X"; tên lạ → None. `modality_coverage_matrix` 15 tập (NR, Δ cùng nguồn, nhãn bối cảnh; khác nhãn = không so sánh) thay bảng dài.
- B `study_profile.py`: external val./CV/patient-wise/giao thức thiếu modality/uncertainty/code từ câu nguyên văn của chính paper, "Yes/No (p. X)" | NR; câu trích ở `validation_report.study_profile`. Đếm đưa vào EVIDENCE LIMITS.
- C `science_qa.py` → `validation_report.science_qa` + warnings. Chạy trên `survey_58ad3caf.md`: bắt đúng 2 câu "No source reports per-modality…", T1ce/T1c, HD95/95% Hausdorff, Swin UNETR [7] ở 2 nhóm taxonomy.
- D `review_protocol.py` + `docs/review-protocol.md`: người dùng khai báo tìm kiếm/sàng lọc thật → REVIEW FACTS + PRISMA tất định; sai số học → cảnh báo, không dùng.
- E prompt: bảng định vị so với survey trước, contribution kiểm chứng được, 6.2 clinical reliability theo từng chiều; REVIEW FACTS liệt kê survey trong kho; gate cảnh báo `novelty:`.

## Cố ý không làm
- Citation entailment bằng LLM (claim có được nguồn hỗ trợ không): cần gọi LLM + bộ đánh giá riêng; hiện chỉ có truy vết số.
- Independent reproduction: không xác định được từ chính paper → không có cột.
- Hồ sơ nghiên cứu chỉ dựa trên đoạn đã truy xuất → NR nhiều; muốn đầy đủ phải quét toàn văn (đổi retrieval, ngoài phạm vi).

## Đang chờ
- Người dùng: restart worker, chạy lại survey, giữ bản cũ `survey_58ad3caf.*` để so; xem `validation_report.science_qa`/`study_profile` và đối chiếu Table 3/5/7 với PDF gốc.
- Người dùng: tìm kiếm CSDL + sàng lọc thật → `review_protocol.json`; thêm survey trước + paper wishlist vào kho.
- Lint có sẵn (không do task): SIM114 format_sanitizer, W293 citation_cleaner, SIM201 synthesize_node, B007 dataset_catalog, vài test.
