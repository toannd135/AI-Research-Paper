# Bàn giao: Paper đa đối tượng, đa lĩnh vực

## Mục tiêu
Paper có ảnh thật (có nguồn), số liệu/biểu đồ từ dữ liệu thật, khung theo lĩnh vực, điều chỉnh theo đối tượng
(giảng viên / sinh viên / người đi làm). Kế hoạch: docs/plans/paper-da-doi-tuong.md.

## Nhánh / trạng thái git
- Nhánh `feature/login`. Phase 2 (P0) + 3 việc tinh chỉnh đã cài, CHƯA commit. `frontend` là submodule: sửa nằm trong frontend/src.

## Đã xong
- P0: profiles.py (6 lĩnh vực, 3 đối tượng), API/DB (migration 0007), plan_node đoán field, search_node lọc miền theo field,
  prompt theo field/audience, ảnh thật từ PDF (app/pipeline/figures.py) + khối ```image + render Typst/HTML kèm "Source:".
- Trích hình (figures.py): gộp ảnh ghép (a)/(b), lọc icon/thanh dẹt, hình VECTOR (page.get_drawings, kind "vector"),
  chú thích bên cạnh, không lấy chú thích khác cột; bảng kẻ ngang bị loại.
- Postprocess ghi log WARNING khi bỏ khối image (ref lạ / trùng).
- Frontend: 2 select "Đối tượng đọc" + "Lĩnh vực" ở InitialState.tsx, gửi ở cả 2 lần gọi POST /research. typecheck/build pass.
- Typst: sửa lỗi toán do LLM viết (QK, PE: quote tên 2 chữ hoa; từ trần pos/softmax/argmax: vòng sửa
  `_compile_with_math_repair` quote biến lạ rồi biên dịch lại).
- Test: `pytest app -q` pass (cả bộ, gồm test mới cho profiles, figures, Typst, appendix).

## Acceptance với LLM thật — ĐẠT cả 3 ca (PDF Typst + HTML đều ra)
- cs_lecturer (nemotron/OpenRouter): field=computing, LLM tự chèn 2 ảnh thật (Figure 1, 2 của "Attention Is All You Need") kèm nguồn.
- med_professional (nemotron): field=medicine, có Executive Summary (sau Abstract) + Practical Implications (bảng 5 cột). Không có ảnh vì chưa upload paper y tế.
- econ_student (Groq gpt-oss-120b vì OpenRouter hết 50 lượt free/ngày, reset 07:00 23/10): field=economics; model BỎ QUA Key Takeaways/Glossary
  → đã thêm `_generate_audience_appendix` (synthesize_node.py): thiếu tiêu đề trong profiles["end_headings"] thì gọi LLM 1 lần
  viết riêng các mục đó; kiểm chứng với Groq thật: sinh đúng, có trong PDF.
- Lỗi Typst phát hiện qua acceptance và đã sửa (đều có test): QK/PE (tên 2 chữ hoa), từ trần trong công thức (pos/softmax/argmax:
  `_compile_with_math_repair`), header_groups sai span (bỏ nhóm, không làm hỏng cả PDF), `\[..\]`/`\(..\)` (chỉ đổi khi giống LaTeX), `p<0.05` (escape `<`).
- Kết quả/PDF mẫu nằm ở thư mục scratchpad của phiên (acc/, acc2/), không thuộc repo.

## Đã làm thêm theo yêu cầu
- `alembic upgrade head` đã chạy: DB postgres localhost:5433 đang ở 0007.
- Đã trích lại hình cho 2 paper trong data/papers (data/ bị gitignore).

## Đang chờ
- Người dùng quyết định commit (chưa commit gì; `frontend` là submodule có sửa 7 tệp trong frontend/src).
- Mục "lỗi khác bạn đang gặp": người dùng chưa mô tả.
- Chưa thử ảnh thật trong bài y tế/kinh tế (cần upload PDF đúng chủ đề rồi chạy lại).
- P1 còn lại: D1 dữ liệu mở (World Bank/OWID), D2 chart scatter/box, I3 ảnh ngoài có giấy phép, T1 trích bảng số từ PDF.

## Lệnh kiểm tra
- `pytest app -q 2>&1 | tail -20`
