# paperai — chỉ dẫn cho Claude

Paper research assistant: upload PDF -> parse/chunk -> hybrid RAG -> research agent (LangGraph) sinh paper có citation, xuất PDF/LaTeX/BibTeX.

## Đọc trước khi làm (theo nhu cầu, đừng đọc hết)
- Kiến trúc/luồng dữ liệu: `docs/architecture.md`
- Yêu cầu & acceptance: `docs/requirements.md`
- Quy tắc code: `docs/coding-standards.md`
- API: `docs/api-contracts.md` · DB: `docs/database-schema.md` · Test: `docs/testing-strategy.md`
- Việc đang làm: `docs/current-task.md` + `docs/implementation-plan.md`
- Quyết định kiến trúc: `docs/decisions/*.md`
- Bàn giao phiên trước: `docs/handoff/` (đọc tệp mới nhất liên quan)
- Frontend: `frontend/Claude.md`

## Quy trình vibe code (bắt buộc)
1. Đọc `docs/current-task.md`; nếu trống/sai thì hỏi người dùng, không tự đoán phạm vi.
2. Khảo sát code bằng CodeGraph (`codegraph_explore`) trước khi grep/Read.
3. Task >1 tệp: cập nhật `docs/implementation-plan.md` (bước + cách kiểm chứng) rồi mới code.
4. Viết/sửa test cùng lúc với code; chạy `ruff check app` và `pytest <phạm vi hẹp>` rồi mới báo xong.
5. Đổi API/DB/graph -> cập nhật doc tương ứng (api-contracts, database-schema, architecture) trong cùng thay đổi.
6. Quyết định có đánh đổi -> thêm ADR vào `docs/decisions/`.
7. Xong mốc -> ghi `docs/handoff/<chủ-đề>.md` (skill `/handoff`).

## Lệnh thường dùng
```bash
./scripts/run_local.sh                      # docker compose + alembic upgrade head
uvicorn app.main:app --reload
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info
alembic upgrade head | alembic revision -m "msg"
ruff check app tests && ruff format --check app tests
pytest app/agent -q                         # thu hẹp theo module
cd frontend && npm run check                # typecheck + lint + build; npm run test:e2e
```

## Ranh giới (không tự ý làm)
- Không commit/push, không chạy migration trên DB thật, không sửa `.env`, không xóa `data/`.
- `frontend` là submodule: sửa trong `frontend/src`, báo người dùng khi cần commit riêng.
- Không viết lại tệp không liên quan; thay đổi nhỏ nhất đủ dùng. Không thêm dependency khi chưa hỏi.
- Test không gọi LLM/mạng thật: dùng fake gateway (`build_graph(llm=...)`).
- Ngôn ngữ: UI/prompt/log/comment người dùng nhìn thấy bằng tiếng Việt; tên code bằng tiếng Anh.

## Bản đồ mã
`app/core` config/schemas/db · `app/ai` embedding+retrieval+LLM gateway · `app/pipeline` parser/chunk/vector/export/celery tasks ·
`app/api` routes+models · `app/agent` LangGraph · `app/workers` celery · `migrations/versions` alembic · `frontend/src` React (admin/client/auth/home).
