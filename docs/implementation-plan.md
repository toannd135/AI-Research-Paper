# Kế hoạch triển khai

> Mẫu cho mọi task >1 tệp. Mỗi bước phải có cách kiểm chứng. Bản dưới là cho task hiện tại (xem `current-task.md`).

## Nguyên tắc
Thứ tự: schema/model -> logic thuần (có test) -> node/route -> tích hợp -> doc. Mỗi bước kết thúc bằng lệnh kiểm chứng xanh rồi mới sang bước sau.

## Các bước (Research Knowledge Model)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | Taxonomy + cấu trúc model (gaps/questions/claims/experiments) | `agent/research_model.py` | `pytest app/agent/tests/test_research_model.py` |
| 2 | Validator claim↔evidence | `agent/evidence/claim_validator.py` | unit test: claim có/không evidence, evidence lạ |
| 3 | `model_node` + state | `nodes/model_node.py`, `state.py` | test node với fake LLM, JSON sai -> fallback |
| 4 | Nối vào graph | `graph.py` | `test_graph.py`: critique -> model -> synthesize |
| 5 | Lưu DB + migration | `models/research_task.py`, `0008_*`, `tasks.py` | upgrade/downgrade; test model |
| 6 | API trả `research_model` | `routes/research.py`, `schemas.py` | `pytest app/api/tests/test_research_route.py` |
| 7 | Prompt synthesize dùng model | `synthesize_node.py`, `plan_node.py` | test synthesize + postprocess |
| 8 | Doc + handoff | `docs/*` | đối chiếu thủ công |

## Rủi ro
- LLM trả JSON hỏng -> luôn có fallback, không raise ra ngoài node.
- Task cũ không có `research_model` -> mọi nơi đọc phải chấp nhận `None`.
- Chạy migration nhầm DB -> chỉ chạy khi người dùng đồng ý.

## Định nghĩa xong
Toàn bộ tiêu chí trong `current-task.md` được tick.
