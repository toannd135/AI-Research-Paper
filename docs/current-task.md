# Task đang thực hiện

> Cập nhật tệp này MỖI KHI đổi task. Claude đọc nó trước khi code. Trống/lỗi thời -> hỏi người dùng.

## Task: Research Knowledge Model (nhánh `vinh-diagram`)
Mô hình hóa dự án nghiên cứu thành dữ liệu có cấu trúc (gaps, questions, claims, experiments) thay vì chỉ văn bản; mỗi claim được kiểm chứng với evidence.

## Trạng thái (từ git, chưa commit)
- Có: `app/agent/research_model.py` (taxonomy contribution/methodology/paper type), `nodes/model_node.py`, `evidence/claim_validator.py`, `test_research_model.py`, migration `0008_research_model.py`, cột `research_tasks.research_model`, field `research_model` trong `ResearchTaskResponse`, node `model` trong graph (critique -> model -> synthesize).
- Sửa: `plan_node`, `synthesize_node`, `state.py`, `tasks.py`, `routes/research.py`, `schemas.py`.

## Phạm vi được phép đổi
`app/agent/**`, `app/api/models/research_task.py`, `app/api/routes/research.py`, `app/core/schemas.py`, `app/pipeline/tasks.py`, `migrations/versions/0008_*`, test tương ứng, và doc liên quan.

## Không đổi
Pipeline nạp paper, retrieval, LLM gateway, auth, frontend (trừ khi được yêu cầu riêng), migration 0001–0007.

## Tiêu chí hoàn thành
- [ ] `pytest app/agent app/api -q` pass; `ruff check app tests` sạch
- [ ] `alembic upgrade head` (DB dev) rồi `downgrade -1` + `upgrade head` chạy được
- [ ] Task cũ (research_model = NULL) vẫn đọc được qua `GET /research/{id}`
- [ ] Graph vẫn chạy khi `model_node` lỗi/LLM trả JSON sai (suy giảm, không sập task)
- [ ] claim không có evidence bị đánh dấu trong report/research_model
- [ ] `docs/api-contracts.md`, `docs/database-schema.md`, `docs/architecture.md` khớp code
- [ ] Ghi `docs/handoff/research-model.md` khi xong mốc

## Câu hỏi mở
(điền khi gặp; hỏi người dùng thay vì đoán)
