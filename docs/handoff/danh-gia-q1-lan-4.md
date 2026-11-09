# Bàn giao: đánh giá Q1/Q2 lần 4 (survey c5d84302)

## Đã làm
- Gate chạy lại trên bản cuối (`_verify_final_report`), `redact.py` che ô UNTRACED bằng NR; `draft_gate`, `redacted_cells` trong validation_report.
- `science_qa.py`: mâu thuẫn nội bộ "đủ 15 tập", ledger claims (exhaustive / N bản ghi từ M paper), tuyệt đối ở thân bài, phạm vi năm hai chiều; `quant_analysis.missing_modality_record_count`.
- `evidence_limits` đếm paper có bản ghi; `_review_facts` có dải năm xuất bản thật; `_global_standards` thêm HEDGING.
- `_collect_figures` neo miền theo từ hiếm; `quality_gate._misattribution_warnings`; `citation_validator` khớp theo ranh giới từ.
- Chuỗi dự phòng LLM: OpenRouter key1 → Groq → OPENROUTER_API_KEY_2. README có lệnh kiểm đủ 40 paper.
- Doc: architecture (Đợt 4), ADR 0007, current-task.

## Kiểm chứng
`pytest app/agent app/pipeline app/ai -q` pass; ruff sạch trên tệp đã sửa (SIM201 cũ ở synthesize_node chưa đụng).

## Đang chờ
- Người dùng restart worker (`celery -A app.workers.celery_app worker ...`) rồi tự chạy lại survey; không tự chạy.
- Không làm: PRISMA/CSDL/2 reviewer (việc người dùng), tách cột Dice %/tỉ lệ.
- Dọn tùy chọn: 2 vector Qdrant mồ côi; thư mục cache extract đã dời.
