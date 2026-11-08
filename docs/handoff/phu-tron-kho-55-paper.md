# Bàn giao: phủ trọn kho 55 paper (2026-11-08)

## Đã làm
- Thêm 24 PDF arXiv vào `data/papers_brain` (kho 31 -> 55), `catalog.json` đủ 55 mục. Nhập 24 record vào DB (`import_existing_papers` với `UPLOAD_DIR=data/papers_brain`).
- Phủ kho: `app/agent/tools/ensure_coverage.py` (bổ sung ≥1 chunk/paper, gọi trong `search_node`), `app/agent/evidence/coverage.py` (`coverage_target`, `uncited_papers`), `qdrant_client.list_paper_ids`, cảnh báo `độ phủ kho: x/y` trong `quality_gate`, setting `full_corpus_coverage_limit=80` (0 = tắt).
- Từ task trước: `ResultRecord.spread/spread_type`, `efficiency_table`, cột Spread (xem `survey-quality-fixes.md`, `danh-gia-q1-spread-efficiency.md`).
- Test: `pytest app/agent app/ai app/pipeline -q` pass; `conftest.py` mới chặn test chạm Qdrant thật.

## Đang chờ (chưa đảm bảo 55 reference)
1. DB: 31 `done`, 24 `pending`. Hai worker đang chạy chỉ nghe `research_queue`, KHÔNG ai nghe `upload_queue`. Người dùng chạy:
   `UPLOAD_DIR=data/papers_brain celery -A app.workers.celery_app worker -Q upload_queue -c 1 -l info`
2. Restart worker `research_queue` để nạp code phủ kho.
3. Chạy lại survey, đếm References so với 55.
4. Quyết định mở: gate hiện chỉ CẢNH BÁO khi thiếu; muốn cứng thì chặn export hoặc hậu kỳ tự thêm câu cite cho paper bị sót.

## Lưu ý
- RFNet không có trên arXiv, chưa tải. Danh sách còn lại: `docs/paper-wishlist.md`.
- Thư mục `data/papers_brain` nặng ~297 MB; chưa commit gì. `m frontend` trong git status không do phiên này.
- PDF `data/exports/survey_58ad3caf.pdf` là bản HTML (Typst lỗi `unknown variable: ap`).
