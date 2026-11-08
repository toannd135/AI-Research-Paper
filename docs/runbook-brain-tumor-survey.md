# Runbook: sinh Survey "Deep Learning-Based Brain Tumor Segmentation Using Multi-Modal MRI"

> Tệp này gom TOÀN BỘ yêu cầu và trạng thái. Phiên mới chỉ cần đọc tệp này rồi làm theo thứ tự các mục 3 → 6. Chi tiết kỹ thuật: `docs/implementation-plan.md`, bàn giao: `docs/handoff/survey-quality-gate.md`.

## 1. Mục tiêu
- Sinh một **Narrative Review (survey)** về đề tài trên, nguồn **chỉ** từ 31 PDF trong `data/papers_brain` (bản sao của `docs/papers`), **không** tìm nguồn ngoài.
- Bài không có thực nghiệm riêng: không bịa Dice/Accuracy/Loss, mọi số phải truy được về PDF nguồn kèm `[n]`.
- Đây là chuẩn nội bộ của PaperAI, không phải quy định xuất bản bắt buộc; chưa được gọi là "đạt Q1–Q4".

## 2. Tiêu chí hoàn thành của bài
- Cấu trúc: Title, Abstract (150–220 từ, không cite), 5 Keywords; 1 Introduction (Limitations of Existing Surveys, Research Gaps & RQ, Contributions, Organization); 2 Review Methodology; 3 Taxonomy; 4 Technical Methodologies; 5 Comparative Evidence Synthesis; 6 Discussion (có Table 4 điểm mạnh/hạn chế, Limitations of this Review); 7 Conclusion (trả lời từng RQ); Appendix A chỉ khi nguồn có chi tiết thật; References IEEE.
- References: có **tiêu đề, tác giả, năm thật** (không UUID/"Anonymous"); mục tiêu **≥ 25 paper khác nhau** được cite thật sự (không ép nếu kho không đủ; đếm số mục trong References để báo cáo đúng).
- Hình/bảng: mục tiêu 5–6 hình, ≥ 4 bảng (taxonomy, dataset+metric, so sánh định lượng, điểm mạnh/hạn chế); ảnh thật ≤ 4, caption ghi nguồn `[n]` + lưu ý giấy phép; không đọc số từ ảnh; không trộn WT/TC/ET hoặc Dice với HD95 trên một trục; chỉ so sánh trực tiếp khi cùng dataset version/split/vùng/metric.
- Review Methodology chỉ nêu quy trình thật (`_review_facts`): kho PDF nội bộ, số paper, truy vấn, ngày; **cấm** bịa CSDL (IEEE Xplore, PubMed...), số lượt sàng lọc, PRISMA.
- Không viết "first", "no previous study" khi chưa có tìm kiếm rộng; dùng "updated synthesis", "the reviewed corpus indicates".
- `validation_report.json` được ghi và đọc được (xem mục 5).

## 3. Dựng môi trường (stack riêng `paperai_bt`, KHÔNG đụng `data/papers`)
Kiểm tra trước, đừng dựng lại nếu đã chạy:
```bash
docker compose -p paperai_bt ps --format '{{.Name}} {{.Status}}'     # postgres/qdrant/redis phải Up (healthy)
curl -s localhost:8000/health | jq -c .                              # API
ps -eo pid,args | grep "[c]elery -A app.workers"                     # worker
docker exec paperai_bt-postgres-1 psql -U paperai -d paperai -tAc "select status,count(*) from papers group by 1;"   # kỳ vọng done|31
```
Nếu chưa chạy:
```bash
docker compose -p paperai_bt up -d postgres qdrant redis
export UPLOAD_DIR=data/papers_brain EXTERNAL_SEARCH_ENABLED=false CONTEXT_TOKEN_LIMIT=14000
alembic upgrade head                                                  # chỉ trên DB mới của stack này
uvicorn app.main:app --port 8000 &                                    # tự nạp PDF trong UPLOAD_DIR
celery -A app.workers.celery_app worker -Q research_queue -c 1 -l info &
```
- `data/papers_brain/` phải có đủ 31 PDF + `catalog.json` (metadata References) + `figures/`. Nếu thiếu: `cp docs/papers/*.pdf docs/papers/catalog.json data/papers_brain/` và `cp -r docs/papers/figures data/papers_brain/`.
- Cần nạp lại paper pending: dùng `process_paper.delay(id)` (worker `-Q upload_queue`) rồi chờ `done|31`. Worker nghe `upload_queue` khi nạp, `research_queue` khi sinh paper; **không để hai việc chạy xen nhau**.
- Dừng tiến trình: lấy PID bằng `ps` rồi `kill <pid>`. **Không** dùng `pkill -f`/`pgrep -f` với tên lệnh (tự giết shell). Xóa hàng đợi: `docker exec paperai_bt-redis-1 redis-cli flushall`.
- Biến môi trường chỉ đặt khi chạy (không sửa `.env`). Khóa OpenRouter nằm trong `.env`, không in ra log.

## 4. Điều kiện chạy: quota OpenRouter
- Lần chạy gần nhất chết do HTTP 429 `free-models-per-day` (50 request/ngày; mỗi paper ~12 lần gọi LLM). Hạn mức cấp lại **07:00 ngày 08/11/2026 (+07)** hoặc nạp 10 credit / đổi khóa (người dùng tự làm; **khóa cũ đã lộ trong log, cần revoke + tạo khóa mới**).
- Chỉ chạy khi `research_tasks` trống và hàng đợi trống (`redis-cli llen research_queue` = 0, `llen upload_queue` = 0).

## 5. Sinh paper và kiểm tra
```bash
set -a; . ./.env; set +a
TOKEN=$(curl -s localhost:8000/auth/login -H 'content-type: application/json' \
  -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | jq -r '.access_token // .token')
curl -s localhost:8000/research/ -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' -d @req.json | jq -c '{id,status}'
```
`req.json` (đã gồm câu trả lời làm rõ; lần đầu không có thì API trả `needs_clarification`):
```json
{"question":"Deep Learning-Based Brain Tumor Segmentation Using Multi-Modal MRI","audience":"lecturer","field":"computer_vision","contribution_type":"survey",
 "clarification_answers":{
  "What is the primary goal or output of this research report?":"Comprehensive literature review/survey paper",
  "Which specific tumor types or segmentation tasks are in scope?":"Glioma (whole tumor, core, enhancing core) per BraTS",
  "Which MRI modalities and preprocessing aspects should be emphasized?":"Standard 4-modality (T1, T1ce, T2, FLAIR) + fusion strategies; missing modality robustness",
  "What is the intended audience and approximate length of the final report?":"Journal paper (8-12 pages, technical depth)"}}
```
Theo dõi: `select status,length(coalesce(report,'')) from research_tasks;` và `grep -E "ERROR|Traceback|Executing Synthesis" <log worker>`. Task mất ~20 phút. Lỗi 429 → quay lại mục 4.

Sau khi `done`, kiểm tra và **báo cáo trung thực** (kể cả khi chưa đạt):
1. `select report from research_tasks;` → lưu ra tệp; liệt kê mục `#`/`##`; đếm khối `mermaid`/`chart`/`image`/`table`; số mục trong References và tiêu đề có thật không; lệch số "Figure N" giữa chữ và hình.
2. Đọc `data/papers_brain/validation/<task_id>.json`: `passed`, `blocking`, `warnings`, đếm TRACED/UNTRACED/NO_CITATION.
3. Ghi kết quả vào `docs/handoff/` (không báo "xong" nếu chưa đạt tiêu chí mục 2).

## 6. Lộ trình cải tiến (làm TUẦN TỰ, không song song; chi tiết trong `docs/implementation-plan.md` mục "Lộ trình theo đánh giá #3")
**P0:** (1) structured evidence extraction → `QuantitativeResult` (trường paper không nêu = `None`, không để LLM điền); (2) chuẩn hóa comparability COMPARABLE / PARTIALLY_COMPARABLE / NOT_COMPARABLE trên record thật; (3) traceability claim→PDF→trang/bảng chứng minh bằng chạy thật; (4) quality gate thành cổng thật: BLOCKING chặn export bản publication-ready, WARNING/INFO không chặn; (5) đổi nhãn `reference_check` VERIFIED → CATALOG_MATCHED (VERIFIED chỉ khi có nguồn độc lập); (6) chạy lại 1 paper đầy đủ + chấm thủ công.
**P1:** Crossref/OpenAlex; citation-to-claim (`CitationSupport`); AI disclosure theo tạp chí; figure/table checker (số thứ tự, caption, được nhắc, nguồn/giấy phép); quy tắc novelty.
**Chỉnh prompt nhỏ:** Intro 1.3 chỉ giới thiệu RQ, 2.1 nêu cách dùng corpus để trả lời RQ (tránh trùng); 5.3 Qualitative chỉ sinh khi corpus có ảnh đối chiếu được; Appendix A chỉ sinh khi nguồn có chi tiết; metadata tác giả thật thêm ở bước export.
**Bộ test cài lỗi (gate phải bắt hết mới coi xong):** DOI đúng nhưng title sai · citation không hỗ trợ claim · Dice WT gán thành ET · hai dataset version trong một chart · số liệu không có page provenance · hình không được nhắc trong thân bài · bảng lệch số thứ tự · claim novelty tuyệt đối không có bằng chứng.
**Việc cần xác minh:** đánh giá bên ngoài nhắc "56 PDF" trong khi kho chỉ có 31 PDF — tìm xem 56 là gì rồi thống nhất.

## 7. Quy tắc làm việc (từ `CLAUDE.md` của dự án)
- Không commit/push, không sửa `.env`, không xóa `data/`, không chạy migration trên DB thật; `frontend` là submodule.
- Task >1 tệp: cập nhật `docs/implementation-plan.md` trước; viết test cùng code; chạy `ruff check app tests` + `pytest <phạm vi hẹp>` rồi mới báo xong; đổi API/DB/graph thì cập nhật doc tương ứng.
- Test không gọi LLM/mạng thật (fake gateway). Comment/log/thông báo lỗi bằng tiếng Việt, tên code tiếng Anh; đầu ra hệ thống (bài báo) tiếng Anh.
- Không viết lại tệp không liên quan; không thêm dependency khi chưa hỏi.

## 8. Đã có sẵn (không làm lại)
- Prompt/cấu trúc survey mục 2–7, `_review_facts`, `_source_coverage_rule` (≥25 paper), quy tắc figure/table và Dice/HD95, ảnh chỉ để minh họa; `search_node` top_k 30/candidate_k 60; `build_context(diversify=True)`.
- Quality Gate P0 (`app/agent/evidence/{quant_check,reference_check,traceability,quality_gate}.py`), test `app/agent/tests/test_quality_gate.py`; `pytest app` pass (lần chạy cuối).
- Chưa kiểm chứng trên paper thật; gate mới chỉ báo cáo, chưa chặn export.

## 9. Dọn dẹp khi xong
`docker compose -p paperai_bt down` (không xóa volume/`data/`); dừng uvicorn và celery bằng `kill <pid>`.
