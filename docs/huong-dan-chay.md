# Hướng dẫn chạy tuần tự từ đầu (Linux, hạ tầng Docker + API/worker trên máy)

Mọi lệnh chạy trong thư mục `paperai`, trừ khi có ghi khác.
Request mẫu: `data/requests/mri_brain_survey.json` (đã có `workspace_id` của workspace 52 paper).

## Bước 0. Cài đặt (chỉ làm lần đầu)
```bash
source venv/bin/activate
pip install -r requirements.txt -c requirements-constraints.txt
python -m playwright install chromium
npm ci --prefix app/pipeline/export/assets
```
Xuất PDF LaTeX cần Tectonic (`~/.local/bin/tectonic`, kiểm tra: `tectonic --version`).

## Bước 1. Bật hạ tầng: Postgres, Qdrant, Redis
```bash
docker compose up -d
```
Container phải tên `paperai-postgres-1` (không phải `paperai_bt-…`): dữ liệu 52 paper nằm ở bên này.

## Bước 2. Cập nhật DB (khi có migration mới)
```bash
source scripts/host_env.sh
alembic upgrade head
```

## Bước 3. API — tab 1, giữ tab mở
```bash
source scripts/host_env.sh
uvicorn app.main:app --reload
```
Kiểm tra: http://localhost:8000/docs

## Bước 4. Celery worker — tab 2, giữ tab mở
```bash
source scripts/host_env.sh
celery -A app.workers.celery_app worker -Q upload_queue,research_queue -l info
```
Mỗi lần sửa code backend: Ctrl+C rồi chạy lại lệnh này (task đang chạy sẽ bị ngắt).

## Bước 5. Frontend (không bắt buộc) — tab 3
```bash
cd ../frontend && npm run dev
```

## Bước 6. Kiểm tra workspace có đủ 52 paper
```bash
docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc \
  "select w.id, w.name, p.status, count(*) from papers p join workspaces w on w.id=p.workspace_id group by 1,2,3"
```
Cần thấy `MRI brain survey v2|done|52`. Nếu chưa có, tạo workspace và gán paper:
```bash
source scripts/host_env.sh
python scripts/assign_papers.py --dir data/papers_brain --email admin@gmail.com --workspace "MRI brain survey v2" --apply
```
Nếu tạo workspace mới thì sửa `workspace_id` trong `data/requests/mri_brain_survey.json` cho khớp `id` ở trên.

## Bước 7. Gửi câu hỏi research — tab 4
```bash
set -a; . ./.env; set +a
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r '.access_token // .token')
curl -s -m 300 localhost:8000/research/ -H "authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d @data/requests/mri_brain_survey.json | jq -c '{id,status,detail}'
TASK=<id vừa nhận>
```

## Bước 8. Theo dõi tiến độ (khoảng 20 phút trở lên)
```bash
docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc \
  "select status, length(coalesce(report,'')), left(coalesce(error,''),150) from research_tasks where id='$TASK'"
```
Bình thường: `pending` → `processing` → `done`, độ dài report > 0. `failed` thì xem cột lỗi và log ở tab worker.

Chuỗi dự phòng LLM khi gặp 429 (rate limit) hoặc 413 (request quá lớn):
OpenRouter khóa 1 (`OPENROUTER_MODEL`) → (lỗi bất kỳ) OpenRouter khóa 2 (`OPENROUTER_MODEL_2`, trống thì dùng `OPENROUTER_MODEL`) → (429/413) Groq (`GROQ_MODEL`).

## Bước 9. Xuất PDF LaTeX và BibTeX
```bash
mkdir -p data/exports
curl -s "localhost:8000/research/$TASK/pdf?engine=latex&template=ieee" \
  -H "authorization: Bearer $TOKEN" -o data/exports/paper_${TASK:0:8}_latex.pdf
curl -s "localhost:8000/research/$TASK/bib" -H "authorization: Bearer $TOKEN" -o data/exports/paper_${TASK:0:8}.bib
```
Bản một cột: thêm `&columns=1`. Mẫu CVPR: `template=cvpr`.

## Dừng
Ctrl+C ở các tab, rồi:
```bash
docker compose stop
```
Không dùng `docker compose down -v` (xoá volume chứa dữ liệu 52 paper).
