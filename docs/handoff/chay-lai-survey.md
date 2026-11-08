# Bàn giao: chạy lại survey brain tumor sau 5 phase (2026-11-08)

## Mục tiêu
Sinh survey "Deep Learning-Based Brain Tumor Segmentation with Multi-Modal MRI: Fusion Strategies and Missing-Modality Robustness", ≥25 reference, chỉ từ 31 PDF `data/papers_brain`; kiểm chứng 5 phase bằng chứng (chi tiết: `docs/handoff/survey-5-phase.md`, `docs/runbook-brain-tumor-survey.md`).

## Nhánh/trạng thái git
`feature/normalization`, nhiều tệp sửa + chưa theo dõi, CHƯA commit/push (theo CLAUDE.md không tự commit).

## Đã xong (chưa commit)
- 5 phase: `app/agent/evidence/{extractor,ledger,consistency_check,quant_analysis,external_verify,display_check}.py`, `pipeline/export/validation_gate.py`; `pytest app` pass.
- Sửa lỗi: decorator Celery `tasks.py`; `lower_is_better` thiếu HD95 `stats.py`.
- Extractor: log từng lô, timeout 90s/lô, ngân sách 360s (`extractor.py`); log trong `analyze_node.py`.
- PDF lần chạy cũ (task 4e8e0871, 16 reference): `~/Downloads/brain-tumor-survey-4e8e0871.pdf`.

## Quyết định đã chốt
Số liệu chỉ từ record khớp nguyên văn PDF; thiếu = NR; export 409 khi gate fail (`?draft=true`); hình/bảng là WARNING, không ép đủ số; không bịa số để lấp chart. ADR `docs/decisions/0006-*.md`.

## Việc còn lại
1. Khi task f4998490 xong: đếm References (mục tiêu ≥25), số ResultRecord trích được, số hình/bảng/chart, đọc `data/papers_brain/validation/<task_id>.json` (`passed`, `blocking`, `display_items`, `consistency`), xuất PDF `GET /research/<id>/pdf?draft=true`, báo cáo trung thực.
2. Nếu References <25: tìm vì sao chỉ ~16 paper vào context (`CONTEXT_TOKEN_LIMIT`, `search_node` top_k, `_diversify`).
3. Chưa làm: OpenAlex, kiểm tra ngôn ngữ khoa học mới, in "chưa xác định" cho DOI thiếu.

## Đang chờ
- Task `f4998490-1828-406e-8749-94630e4bb1c6` đang chạy (worker log: scratchpad `worker3.log`; stack `paperai_bt`, API :8000 chạy với `UPLOAD_DIR=data/papers_brain CONTEXT_TOKEN_LIMIT=22000`).
- Task cũ `c63caa95…` kẹt ở `processing` (worker bị kill), 2 dòng pending mồ côi: người dùng tự xóa. Khóa OpenRouter cũ cần revoke.

## Lệnh kiểm tra
`docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "select id,status,length(coalesce(report,'')) from research_tasks"` · `pytest app/agent app/api -q` · dừng tiến trình: `kill <pid>` lấy từ `ps`, không dùng `pkill -f`; dọn: runbook mục 9.
