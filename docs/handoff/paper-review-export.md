# Bàn giao: paper-review-export (2026-11-11, lần 2)

## Mục tiêu
Kế hoạch "Sửa hệ thống theo đánh giá reviewer `paper_5a736250_test5_latex.pdf`" + mục "Việc 6–7 + lỗi trình bày LaTeX" (`docs/implementation-plan.md`, cuối tệp). Việc 1–7 xong, trừ chuẩn hoá references.

## Nhánh/trạng thái git
- paperai: CHƯA commit (LaTeX phiên trước + việc 1–7). Không tự commit.
- frontend: commit 4332f84 chưa push.

## Đã xong (chưa commit; `pytest app` xanh)
- 3–5 evidence: `rq_sync.dedupe_rq_definitions`/`check_rq_repetition`; `evidence/evidence_tiers.py`; `repair.ensure_methodology_disclosure`.
- 6–7 LaTeX (`app/pipeline/export/latex_renderer.py`): `_system_author` (Settings `paper_author_*`, email rỗng), `taxonomy_figure` + `figure_layout.two_level_tree`, `_trim_caption_cites`, `roman_table_refs` (bỏ qua dòng caption), `back_matter`, newtxmath trước `fontspec[no-math]`, nháy TeX, kẻ mảnh giữa nhóm ô gộp.
- Font hình Liberation Sans 8pt: `chart_scientific.FIGURE_FONT`, pdf_renderer, browser_renderer (Mermaid). Timeline thấp hơn; evidence map nhãn 7pt.
- `corpus_flow`: LR, nhãn ngắn (`CORPUS_FLOW_MARK` mới + `_LEGACY_MARK`); `figure_layout.mermaid_span`: LR ≥4 nút → wide.
- `report_structure.fix_internal_draft_refs`: chỉ bỏ qua dòng caption `**Figure N:` (câu mở đầu `**Figure 2** …` vẫn lọc render-meta).
- Test: cuối `test_latex_renderer.py`, `test_figure_policy.py`, `test_report_structure.py`.
- Bản thử: `data/exports/paper_5a736250_test6_latex.pdf` (16 trang; script `scratchpad/export_test6.py` áp repair mới lên test5.md rồi `compile_latex_pdf`).

## Quyết định đã chốt
- Tác giả trang đầu tự điền PaperAI; không bịa email. Funding/CoI/Contributions là chỗ trống `[To be completed by the authors.]`.
- Font hình sans (Liberation Sans) — IEEE chấp nhận; thân bài + toán Times.

## Việc còn lại
- Tiếp theo: chuẩn hoá references (plan task 7 phần sau) — `app/pipeline/export/bibliography.py` (`parse_references`, `references_to_bibtex`).
- Câu LLM "with representative citations at the leaves" trong test5 không còn đúng với hình taxonomy mới — cân nhắc thêm vào prompt synthesize: taxonomy figure không có trích dẫn.
- Lint có sẵn chưa sửa: SIM201 synthesize_node, B905 pdf_renderer/chart_scientific, typst_renderer, RUF059 test_report_structure:140.

## Đang chờ
- Người dùng: restart celery worker + chạy lại research để thấy hiệu quả việc 1–5 trên bài mới.
- Người dùng: quyết định commit paperai; push frontend 4332f84.

## Lệnh kiểm tra
- `venv/bin/python -m pytest app -q -p no:cacheprovider` (xem exit code)
- `pdffonts data/exports/paper_5a736250_test6_latex.pdf` (không còn CMR/CMMI)
