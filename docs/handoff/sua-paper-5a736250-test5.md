# Sửa paper 5a736250 → test5 (2026-11-11)

Tiếp nối `sua-loi-chan-survey-5a736250.md` (9 bug trong mục "Bug còn lại" của tệp đó đã có trong code, trừ #9 được thay bằng bước mới dưới đây).
Bản sửa: `data/exports/paper_5a736250_test5.{md,pdf}` (22 trang). Sinh bằng `source scripts/host_env.sh; python scripts/repair_task_report.py 5a736250 --suffix test5`
(không gọi LLM, không ghi DB; đọc report+citations từ DB, untraced từ `validation/<task>.json`).

## Sửa hệ thống (có test, `pytest app/agent app/pipeline app/api` pass)
- `citation_cleaner`: đánh số lại [n] cả trong chuỗi JSON ```table/```chart và nhãn ```mermaid (trước: cụm `[2,38,48]` trong cây giữ chỉ số THÔ → [47]/[48]/[53] vượt 45 ref, số trong phạm vi cũng trỏ sai paper); không còn đổi nhầm mảng số JSON (`"values": [4]`).
- `strip_dangling_citations`: gỡ số ngoài phạm vi trong nhãn mermaid.
- `report_structure.finalize_structure_report`: `rebuild_paper_organization` (đoạn bố cục từ heading thật), `fix_internal_draft_refs` (bỏ "of the full manuscript/Draft Basis", "Table N of the Draft Basis" → "the corresponding source table", bỏ câu nói về graph LR/mermaid).
- `repair.py`: `soften_promotional_claims` (Abstract/Conclusion), `drop_duplicate_charts` (≥80% cặp x,y trùng → bỏ hình sau), chart rút hết điểm bị bỏ hẳn (không in ghi chú "A chart planned … withdrawn"), đoạn "Additional corpus studies" xếp [k] tăng dần.
- `figure_layout.compact_tree`: cây 2 tầng ≥12 lá → `graph TD`, lá xếp chồng bằng `~~~` (Figure 2 taxonomy trước đó không đọc được); nối vào pdf_renderer + typst_renderer.
- Catalog: tác giả Frontiers survey (c6a0b451), venue CVPR/AAAI, Metrics reloaded (Nature Methods 2024). Backup trong scratchpad phiên (có thể mất).
- Doc: `docs/architecture.md` (repair + fence citations).

## Kết quả test5
- 52/52 ref được cite, 0 cite ngoài phạm vi, 0 tham chiếu Table/Figure treo; Table 1→3, Figure 1→2 đúng; §5.5 lạc dưới §4 → 4.6.
- 6 điểm UNTRACED gỡ (chart BraTS 2017 bỏ hẳn), chart trộn vùng giữ WT, chart FeTA trùng bị bỏ.

## Còn lại (không sửa tất định được)
- "mmFormer matrix (Section 3.2)" — nội dung sai mục (LLM); "376 records from 12 papers" vs 52 studies chưa giải thích; Abstract "over 30 methods".
- Ref [29]/[50] ghi arXiv-năm kèm DOI tạp chí năm khác (catalog dùng bản arXiv).
- Script chỉ xuất md+pdf, chưa xuất LaTeX/Bib.

## Đang chờ
- Người dùng duyệt test5; có muốn ghi report đã sửa vào DB (task.report) không.
- ĐANG CHẠY research thật bằng hệ thống mới: task `865b8699-0509-4011-8039-066e8ed6ea50` (clone cấu hình 5a736250, cùng workspace),
  chạy đồng bộ `run_research(...)` với host_env, log ở scratchpad `run6.log`. Xong → xuất PDF (`report_to_pdf(sanitize(task.report), columns=2)`)
  ra `data/exports/paper_865b8699_test6.pdf`, so với test5 + `validation/865b8699-….json` (blocking).
- Chưa commit (repair.py, test_repair.py, scripts/repair_task_report.py là tệp mới).
