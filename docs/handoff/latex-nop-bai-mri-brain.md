# Bàn giao: sửa xuất LaTeX để nộp bài MRI brain (2026-11-11)

## Mục tiêu
Xuất PDF nộp bài (52 paper, workspace "MRI brain survey v2" `24b391d6-7372-4b1e-afca-8485542b2bca`) đúng layout; bảng/hình kiểu "**Table 1.**"/"**Figure 1.**".

## Nhánh/trạng thái git
- paperai `feature/normalization`, HEAD `6fbbb69`; 20 tệp thay đổi CHƯA commit (gồm việc phiên này). Không tự commit.

## Đã xong (chưa commit)
- PDF nộp: `data/exports/paper_5a736250_submission.pdf`; nguồn: `data/exports/paper_5a736250_submission_latex.zip`.
- Dọn report trước LaTeX (trích dẫn theo thứ tự xuất hiện, bỏ cụm nội bộ, RQ lặp, trích dẫn treo).
- Caption kiểu nhãn đậm + bảng số Ả Rập; `\nocite{*}`; nhãn/ref mục; map ⊃⊂; bỏ `---`.
- Legend biểu đồ vừa cột, 7 marker. Gateway: 413 → fallback; `OPENROUTER_MODEL_2`; content rỗng → model kế.
- `docs/huong-dan-chay.md`. DB: task/paper kẹt → failed; 52 paper sang workspace mới.

## Quyết định đã chốt
- Bảng số Ả Rập (theo mẫu người dùng), bỏ `roman_table_refs` khỏi luồng.
- Không tự điền Funding/CoI/Author Contributions.

## Tệp quan trọng
- `app/pipeline/export/publication_prep.py:53` `renumber_citations`, `:105` `prepare_report_for_latex`.
- `app/pipeline/export/latex_renderer.py:71` `_CAPTION_STYLE`, `:345` `_section_ref_tokens`, `:637` gọi prepare.
- `app/pipeline/export/chart_scientific.py` (legend), `app/ai/llm_gateway/{base,retry,groq_adapter,fallback,default,openrouter_adapter}.py`.
- `docker/latex-warmup/paper.tex` (đã thêm gói caption).

## Việc còn lại
1. (Tiếp theo) Người dùng xem PDF mới, so với `data/exports/paper_5a736250_test7_ieee.pdf`, báo lỗi còn lại.
2. Rút bài từ 16 xuống 8–12 trang khi người dùng chọn phần cắt.
3. Chạy lại research: restart worker rồi bước 7 `docs/huong-dan-chay.md`.

## Đang chờ
- Người dùng: nội dung Funding/CoI/Author Contributions; chọn phần cắt.
- 52 paper nay ở workspace "MRI brain survey v3" `2e7beae0-65f5-4173-a638-c403f227f9d0` (v2 rỗng).
- Task mới `7af6af38-b6c9-4b61-b61a-992706e150d2` đang `processing` (tạo 22:24, chưa lỗi lúc 22:35). Kiểm tra:
  `docker exec paperai-postgres-1 psql -U paperai -d paperai -tAc "select status,length(coalesce(report,'')),left(coalesce(error,''),150) from research_tasks where id='7af6af38-b6c9-4b61-b61a-992706e150d2'"`
  Xong → `curl -o data/exports/paper_7af6af38.pdf "localhost:8000/research/7af6af38-b6c9-4b61-b61a-992706e150d2/pdf?engine=latex&template=ieee&draft=true"` (cần token admin).

## Lệnh kiểm tra
- `source venv/bin/activate; pytest app/agent/tests -q -k "latex or pdf or report_structure or chart or figure"; pytest app/ai -q`
- `ruff check app/pipeline/export/publication_prep.py app/pipeline/export/latex_renderer.py` (B905 ở chart_scientific.py:41 có sẵn).
