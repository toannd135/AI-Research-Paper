# Bàn giao: paper-review-improvements (2026-11-11, lần 3)

## Mục tiêu
Sửa HỆ THỐNG sinh paper theo đánh giá reviewer về `data/exports/paper_5a736250_test5_latex.pdf` (không sửa tay bài test5). Kế hoạch: `docs/implementation-plan.md` mục cuối "Sửa hệ thống theo đánh giá reviewer…".

## Nhánh/trạng thái git
- paperai: chưa commit (thay đổi LaTeX phiên trước + việc 1–2 phiên này). Không tự commit.
- frontend: commit 4332f84 chưa push (người dùng tự push).

## Đã xong (pytest app/agent app/api xanh; ruff các tệp đã sửa sạch, lỗi ruff còn lại là có sẵn)
1. Nguồn số liệu chart/table: `traceability.extract_numeric_claims` lấy [n] theo nhãn điểm → tên series → caption; `mark_misattributed` (gọi trong `quality_gate.trace_text_records`) đổi điểm cite nhầm paper (theo sổ cái `state["results"]`) thành UNTRACED → repair gỡ; gate BLOCKING "trích dẫn sai nguồn số liệu" (`check_record_attribution`).
2. Novelty: `consistency_check.check_novelty_claims` → BLOCKING, chỉ câu tự nhận (`_SELF_REF_RE`); repair `repair.soften_novelty_claims` (gọi sau `soften_promotional_claims` trong synthesize_node). `_prior_surveys_fact` chỉ giữ survey cùng chủ đề (≥2 từ chung với câu hỏi).
3. RQ chỉ nêu một lần: `rq_sync.dedupe_rq_definitions` (gọi ngay sau `enforce_rqs` trong synthesize_node) + `check_rq_repetition` BLOCKING ở gate; prompt mục 2.1 đổi thành 'Review Scope' không liệt kê RQ.
4. Phân tầng bằng chứng: `evidence/evidence_tiers.py` (`classify_evidence`, `tiers_fact`) → prompt (cạnh EVIDENCE LIMITS) + bảng Evidence profile ghi '(other dataset)'. Test: `test_evidence_tiers.py`.
5. Methodology: `repair.ensure_methodology_disclosure` chèn đoạn 'Review type and limitations' cho ý còn thiếu (chỉ khi không có protocol); `_review_facts` thêm GRADE. Test cuối `test_quality_gate.py`.
Test mới ở `app/agent/tests/test_quality_gate.py` (cuối tệp + quanh novelty/prior surveys). Doc: `docs/architecture.md` mục (4b)–(4e) + dòng RQ một nguồn.

## Quyết định đã chốt
- Tác giả/affiliation/email trang đầu: TỰ ĐIỀN theo hệ thống PaperAI (người dùng chốt), không lấy profile/form.
- Ưu tiên lỗi học thuật trước trình bày. Engine PDF mặc định latex.

## Tệp quan trọng
- app/agent/evidence/traceability.py (`extract_numeric_claims`, `mark_misattributed`, `check_record_attribution` cuối tệp)
- app/agent/evidence/quality_gate.py (`trace_text_records`, `run_quality_gate`), consistency_check.py (`check_novelty_claims`), repair.py (`soften_novelty_claims`)
- app/agent/nodes/synthesize_node.py (`_prior_surveys_fact`, chỗ gọi `soften_novelty_claims`)

## Việc còn lại (theo thứ tự)
6. LaTeX: tác giả PaperAI tự điền; bảng `\footnotesize` + tách bảng dài; taxonomy tách trục, bỏ cite ở nhãn lá; caption ngắn — `latex_renderer.py`, `figure_layout.py`.
7. Back matter: Data/Code Availability + placeholder Funding/CoI/Contributions; chuẩn hoá references — `latex_renderer.py`, `bibliography.py`.
Còn lại chỉ phần export (6–7), độc lập với evidence.

## Đang chờ
- Người dùng: push frontend 4332f84; quyết định commit paperai.
- Người dùng restart celery worker + chạy lại research test5 để xem hiệu quả việc 1–5.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app/agent app/api -q` (in không có dòng tóm tắt; xem exit code)
- `venv/bin/python -m ruff check <tệp đã sửa>`
