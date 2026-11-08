# Bàn giao: 5 phase nâng cấp bằng chứng khoa học (2026-11-08)

## Đã làm (code + test, `pytest app` pass; CHƯA chạy trên paper thật)
- P1 `evidence/extractor.py` · P2 `ledger.py` + chặn export (`pipeline/export/validation_gate.py`, `?draft=true`) · P3 `consistency_check.py` · P4 `quant_analysis.py` · P5 `external_verify.py`, VERIFIED→CATALOG_MATCHED, Abstract 150–220 từ (trong consistency).
- Hình/bảng theo paper_type: `display_check.py` (WARNING). Prompt chart: mục tiêu 3 loại khác nhau khi đủ số liệu thật; `build_ledger_charts` bù barh/bar/heatmap.
- Sửa lỗi: decorator Celery sai chỗ (`tasks.py`); `lower_is_better` thiếu HD95 (`stats.py`).
- Plan/ADR: `docs/implementation-plan.md`, `docs/decisions/0006-*.md`.

## Đang chờ
- Restart worker + chạy lại survey (mất ~12 phút + thêm ~⌈paper/5⌉ lần gọi LLM) để xem: số `ResultRecord` trích được, ledger có đủ ≥3 phương pháp cùng setting, số chart/bảng, `validation_report.display_items/consistency`.
- Rủi ro: parser PDF có thể làm chunk bảng khó đọc → ít record; khi đó chart/Δ sẽ ít (không bịa).
- Chưa làm: kiểm tra "ngôn ngữ khoa học" mới (giữ bước dịch cũ); DOI thiếu chỉ bị bỏ khỏi References (không in "chưa xác định"); OpenAlex; citation-to-claim (P1 của plan).
- 2 dòng research_tasks pending mồ côi + stack paperai_bt vẫn chạy; khóa OpenRouter cũ cần revoke.
