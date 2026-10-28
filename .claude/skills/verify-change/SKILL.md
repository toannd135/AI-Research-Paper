---
name: verify-change
description: Kiểm chứng trước khi báo hoàn thành một thay đổi - lint, test phạm vi hẹp, đối chiếu doc và tiêu chí task.
---
# Kiểm chứng thay đổi
1. `git status --short` + `git diff --stat`: chỉ có tệp trong phạm vi `docs/current-task.md`.
2. `ruff check app tests` (sửa lỗi do mình gây ra).
3. `pytest <thư mục module đã chạm> -q 2>&1 | grep -E "FAIL|ERROR|passed|failed" | tail -30`. Thay đổi lan rộng -> `pytest -q` toàn bộ.
4. Frontend đụng tới: `cd frontend && npm run check`.
5. Đối chiếu doc: api-contracts / database-schema / architecture còn khớp code không.
6. Tick từng mục "Tiêu chí hoàn thành" trong `docs/current-task.md`; mục chưa làm được thì nói rõ.
7. Báo cáo ngắn: đã đổi gì, lệnh đã chạy + kết quả thật, việc còn lại. Không commit/chạy migration khi chưa được hỏi.
