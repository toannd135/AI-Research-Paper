# Bàn giao: sửa chất lượng survey theo nhận xét `survey_e329b04d.pdf` (2026-11-08)

## Đã làm (code + test; `pytest app/agent app/pipeline app/ai` pass; CHƯA chạy lại survey thật)
- 3.1 RQ một nguồn: `evidence/rq_sync.py` + blueprint mục 7 + tiêm vào chặng 1/2/5 + ép sau khi ghép; lệch RQ giữa 1.3 và 2.1 = lỗi chặn.
- 3.3 `report_structure.renumber_captions_report` (tham chiếu Table/Figure mơ hồ gán theo trùng từ/vị trí), `check_cross_references` (treo = chặn), `citation_cleaner.collapse_duplicate_citations` (`[1], [1]`), CSS bảng `pdf_renderer.py` (hết bẻ giữa từ; đã render thử bản cũ).
- 3.4/3.5 REVIEW FACTS thêm cấu hình retrieval + quy tắc đưa vào/loại thật; chặn tự nhận systematic/PRISMA; caption figure cụ thể + một đoạn phân tích chung các ảnh; cảnh báo caption chung chung/trùng/thiếu giấy phép.
- 3.2/3.6 `quant_analysis`: ma trận missing-modality, Δ vs full, biểu đồ theo modality, `evidence_limits` vào prompt; `reference_check.classify_publication` + cảnh báo preprint/thiếu metadata.
- Kèm: `openrouter_adapter` cắt mảng `models` ≤3 (lỗi 400 khi model ngoài danh sách fallback).

## Đang chờ
- Chạy lại survey brain tumor (restart worker) để xem: RQ có đồng nhất không, tham chiếu bảng, số record có `modality`, bảng/biểu đồ missing-modality có sinh ra không.
- Hạn chế còn lại: ma trận missing-modality phụ thuộc extractor lấy được `modality` từ PDF (có thể rỗng → chỉ ghi hạn chế); không có std/CI vì extractor chưa trích; reference chưa đối chiếu DOI ngoài (cần `REFERENCE_EXTERNAL_VERIFY=true`).
- Lỗi hiển thị chưa sửa: caption bảng bị in hai lần (dòng `**Table N: ...**` + caption trong khối table).
- Lint có sẵn (không do task này): SIM201 ở `synthesize_node`, W293 `citation_cleaner`, B007 `dataset_catalog`.
- Chưa commit (theo quy ước dự án); `frontend` submodule không đổi.
- Yêu cầu người dùng đang chờ (việc mới): "xóa tất cả các task cũ" trong `research_tasks` (hiện có 1 `done` 4e8e0871…, 1 `done` e329b04d… là bản vừa chạy, và các `failed`). Hỏi lại có giữ `e329b04d…` (nguồn của `data/exports/survey_e329b04d.pdf`) không trước khi xóa; xóa kèm `data/papers_brain/validation/<id>.json` hay không cũng cần hỏi. Không xóa `data/` ngoài phạm vi đó.
