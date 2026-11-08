# Bàn giao: chuẩn Survey + Scientific Quality Gate (2026-11-07)

## Đã làm
- `synthesize_node.py` (survey): mục 2 Review Methodology (RQ, corpus/search/selection, trích xuất, so sánh survey có sẵn), Taxonomy→3, Methodologies→4, Evidence→5, Discussion→6, Conclusion→7; `_review_facts` (chỉ số liệu thật); `_DISPLAY_ITEMS_RULE` (figure/table, không bịa số); `_source_coverage_rule` (≥25 paper nếu đủ); quy tắc so sánh Dice/HD95; `MAX_PROMPT_FIGURES`=4; ảnh chỉ để minh họa, không phải số liệu.
- Retrieval: `search_node` top_k 30/candidate_k 60; `build_context(diversify=True)` (mỗi paper 1 chunk trước); chạy với `CONTEXT_TOKEN_LIMIT=14000` (env, chưa đổi mặc định).
- `catalog.json` phải nằm trong upload_dir (đã copy vào `data/papers_brain/`) thì References mới có tiêu đề/tác giả thật.
- Quality Gate P0 trong `app/agent/evidence/`: `quant_check.py`, `reference_check.py`, `traceability.py`, `quality_gate.py`; `validation_report` trong state, ghi `<upload_dir>/validation/<task_id>.json` (tasks.py). Test: `app/agent/tests/test_quality_gate.py`. `pytest app` pass.
- Plan/việc còn lại ghi ở `docs/implementation-plan.md`.

## Môi trường đang chạy (stack riêng, compose project `paperai_bt`)
- Docker: postgres/qdrant/redis (cổng 5433/6333/6380); API :8000; worker Celery `-Q research_queue -c 1`.
- Chạy với `UPLOAD_DIR=data/papers_brain EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=14000`. 31/31 PDF đã nạp. Không sửa `.env`.
- Task sinh paper gần nhất thất bại: OpenRouter 429 hết hạn mức free (50 req/ngày), reset 07:00 08/11/2026 (+07).

## Đang chờ
- LÀM TIẾP: thực thi lộ trình P0 trong `docs/implementation-plan.md` mục "Lộ trình theo đánh giá #3" (bước 1→6, tuần tự). Mở đầu bằng structured evidence extraction.
- Chạy lại sinh paper sau 07:00 (hoặc nạp credit/đổi khóa) để kiểm chứng: References ≥25 paper + tiêu đề thật, cấu trúc mục 2–7, validation_report.
- Quyết định: chặn export khi `validation_report.passed=false`; trích `ResultRecord` có cấu trúc từ PDF; Crossref/OpenAlex; mục student/professional ra ngoài phần chính.
- Khóa OpenRouter đã lộ trong log phiên → nên đổi.
- Cleanup: dừng stack `docker compose -p paperai_bt down` khi xong (không xóa `data/`).
