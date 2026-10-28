# Chiến lược test

## Công cụ
`pytest` (testpaths: `app`, `tests`; cấu hình trong `pyproject.toml`), `ruff`, Playwright (frontend e2e).

## Tầng test
| Tầng | Vị trí | Quy tắc |
|---|---|---|
| Unit | `app/<module>/tests/` | nhanh, không mạng/LLM thật; fake gateway, fixture DB sqlite/in-memory (`app/api/tests/conftest.py`) |
| Graph/agent | `app/agent/tests/test_graph.py` | `build_graph(llm=Fake)`; kiểm routing plan→…→synthesize, nhánh critique lặp |
| API | `app/api/tests/` | TestClient; kiểm quyền (user A không thấy dữ liệu user B), mã lỗi |
| Pipeline | `app/pipeline/tests/` | parser/chunk/figures/exporter trên PDF mẫu nhỏ |
| Retrieval | `tests/`, `eval/`, `scripts/eval_retrieval.py` | đo chất lượng, không chạy trong CI mặc định |
| E2E | `frontend/tests/*.spec.ts` | `npm run test:e2e` (login, home, research flow) |
| Acceptance LLM thật | thủ công | chạy theo ca trong handoff; không đưa vào CI |

## Bắt buộc
- Code mới hoặc sửa bug có test; bug phải có test tái hiện trước khi sửa.
- Đổi prompt/format báo cáo -> test postprocess/sanitizer/validator liên quan.
- Đổi API/schema -> test route + `test_models`.
- Trước khi báo xong: `ruff check app tests`, `pytest <module đã chạm> -q`; thay đổi rộng thì `pytest -q` toàn bộ; frontend đụng tới thì `npm run check`.

## Coverage
Không đặt ngưỡng cứng; ưu tiên phủ nhánh lỗi/fallback (LLM trả sai định dạng, nguồn rỗng, citation lạ, quyền truy cập).

## Lọc output khi chạy
`pytest -q 2>&1 | grep -E "FAIL|ERROR|passed|failed" | tail -30`
