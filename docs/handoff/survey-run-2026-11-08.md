# Bàn giao: chạy survey brain tumor lần 1 sau reset quota (2026-11-08)

## Kết quả (task 4e8e0871-7790-497c-8550-652687133f1e, status=done, ~12 phút)
- Báo cáo ~10.7k từ; đủ cấu trúc mục 1–7, Appendix A, References. Chưa dán nhãn "đạt" tiêu chí runbook mục 2.
- **References: chỉ 16 mục (mục tiêu ≥25)** — corpus 31 PDF nhưng chỉ 16 paper được retrieve/cite (thân bài cũng tự nói vậy ở 6.3). Tiêu đề/tác giả/năm có thật, không UUID/Anonymous.
- Khối: mermaid 2, chart 1, image 2, table 1 (mục tiêu ≥4 bảng, 5–6 hình → **chưa đạt**). Văn bản nhắc Table 1–4 và Figure 1–4, chưa đối chiếu khớp số thứ tự với khối thật.
- validation_report (`data/papers_brain/validation/<task_id>.json`): `passed=false`; 1 BLOCKING: 44 giá trị bảng/biểu đồ UNTRACED (TRACED 20, NO_CITATION 0). References 16/16 nhãn VERIFIED (cần đổi thành CATALOG_MATCHED, P0 bước 5).
- Không thấy "PRISMA/IEEE Xplore/PubMed"; "first" chỉ xuất hiện theo nghĩa thông thường.

## Đã sửa
- `app/pipeline/tasks.py`: decorator `@celery_app.task` bị gắn nhầm vào `_save_validation_report` → `run_research.delay` lỗi AttributeError. Đã chuyển lại; chưa có test cho việc này.

## Đang chờ
- 2 dòng `research_tasks` status=pending mồ côi (từ 2 lần gọi lỗi) + 1 dòng failed cũ; người dùng tự xóa nếu muốn.
- Tăng độ phủ corpus (16→≥25 paper) và số bảng/hình; điều tra 44 giá trị UNTRACED (số bảng lấy từ đâu, có phải lệch định dạng khi so khớp).
- Tiếp P0 bước 1→6 trong `docs/implementation-plan.md`. Revoke khóa OpenRouter cũ.
- Stack paperai_bt, uvicorn, celery vẫn đang chạy; dọn theo runbook mục 9.
