# Bàn giao: sửa lỗi hệ thống theo đánh giá `survey-b1e8d2cc` (2026-11-09)

## Đã xong (chưa commit)
- Worker: `task_time_limit` 7200 / soft 6900 (`app/workers/celery_app.py`).
- Trích xuất (`evidence/extractor.py`): ngân sách tổng `MAX_TOTAL_SECONDS=1500` (quá thì bỏ lô còn lại);
  cache phản hồi LLM thô theo lô ở `data/cache/extract/` (khóa sha256 prompt+model+đoạn văn; `_verify` vẫn chạy lại). `.gitignore` thêm `data/cache/`.
- Nguyên nhân gốc lỗi References/"73 papers" và cách sửa:
  - `[7, 73]` lọt mọi regex `[n]` → `citation_validator.expand_citation_clusters`, dùng trong `citation_cleaner`, `strip_dangling_citations`, quality gate.
  - Admin chạy research với phạm vi `None` → lấy cả vector mồ côi trong Qdrant → "Anonymous"/UUID. `tasks._research_scope`: phạm vi = paper `done` trong DB.
  - REVIEW FACTS: `[n]` là đoạn trích, không phải paper; `consistency_check.check_paper_counts` (chặn) khi "N papers" > kho.
- Hình PDF lạc đề: `_collect_figures(citations, question)` cần caption chung ≥2 từ nội dung với câu hỏi.
- Test: `pytest app/agent app/pipeline` → 338 passed. Ruff: chỉ còn lỗi có từ trước (SIM201 synthesize_node:821, W293 citation_cleaner:189).

## Đang chờ
- Bước 5 (chưa làm): mâu thuẫn "no missing-modality result" ↔ hàng thiếu modality trong bảng (`science_qa.check_absence_claims` bỏ sót khi groups==0);
  cờ audit regex nghĩa là "không thấy trong đoạn truy xuất" → đổi cách diễn đạt "0/73"; thống nhất mẫu số (73 citation vs 23 nguồn có bằng chứng, `quant_analysis.py` ~392/420-475).
- Hạ tầng: DB `papers` có 2 done / 38 pending (hàng đợi đã purge). Qdrant còn vector mồ côi; cần nạp lại 38 paper rồi chạy lại survey.
- ADR cho quyết định ngân sách thời gian trích xuất (thay "chạy đủ mọi lô") chưa viết.
- README dòng 76 đã sửa (done|N, hiện 40). 38 paper pending đã được đẩy lại vào upload_queue (chờ worker).

## Ngoài phạm vi hệ thống
PRISMA, tìm kiếm CSDL, sàng lọc 2 người, risk-of-bias — việc nghiên cứu của người dùng (khai báo qua `review_protocol.json`).
