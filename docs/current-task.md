# Task đang thực hiện

> Cập nhật tệp này MỖI KHI đổi task. Claude đọc nó trước khi code. Trống/lỗi thời -> hỏi người dùng.

## Task: Sửa lỗi chất lượng survey theo nhận xét bản `survey_e329b04d.pdf` (nhánh `feature/normalization`)
Bản trước (Research Knowledge Model) đã commit; task này sửa 4 nhóm lỗi người dùng chọn:
- **3.1** RQ phải có MỘT nguồn duy nhất, dùng giống nhau ở Introduction, Methodology, Discussion, Conclusion.
- **3.3** Kiểm tra nhất quán tài liệu: tham chiếu Table/Figure đúng số thật, không còn trích dẫn lặp `[1], [1]`, tiêu đề cột bảng không bị tách chữ.
- **3.4 + 3.5** Methodology chỉ nêu quy trình thật (không PRISMA/systematic nếu không làm); caption figure cụ thể, ghi nguồn + giấy phép; biểu đồ suy giảm khi mất modality (chỉ khi có số).
- **3.2 + 3.6** Ma trận missing-modality, ΔDice/ΔHD95 chỉ tính từ số trích được; thiếu dữ liệu (ma trận, std/CI) thì ghi rõ là hạn chế, KHÔNG bịa. References: phân loại preprint/đã xuất bản, thiếu venue/DOI.

Quyết định đã hỏi người dùng: thiếu dữ liệu -> ghi rõ hạn chế (không chặn export vì thiếu ma trận).

## Phạm vi được phép đổi
`app/agent/**` (synthesize_node, evidence/*), `app/pipeline/export/pdf_renderer.py` (CSS bảng), test tương ứng, doc liên quan.

## Không đổi
Pipeline nạp paper, retrieval, LLM gateway, auth, frontend, DB/migration, `.env`.

## Tiêu chí hoàn thành
- [x] Blueprint sinh RQ chuẩn; Introduction, 2.1 và Conclusion dùng đúng nguyên văn; RQ lệch giữa Intro và 2.1 -> lỗi chặn
- [x] Tham chiếu `Table N`/`Figure N` mơ hồ được gán theo ngữ cảnh; tham chiếu treo -> lỗi chặn
- [x] `[1], [1]` được gộp thành `[1]`; tiêu đề cột bảng không bị bẻ giữa từ
- [x] Bài tự nhận "systematic review"/PRISMA khi không làm -> lỗi chặn; caption figure chung chung/trùng -> cảnh báo
- [x] Ma trận missing-modality + ΔDice sinh từ `ResultRecord.modality`; khi thiếu, prompt nhận "EVIDENCE LIMITS" đúng số thật
- [x] validation_report có thống kê preprint / thiếu venue-DOI của References
- [x] `pytest app/agent app/pipeline app/ai -q` pass (không gọi LLM/mạng thật); `ruff check` sạch trên các tệp mới/đã sửa (46 lỗi lint có sẵn ở tệp khác, không thuộc task này)
- [ ] Chạy lại survey thật và đối chiếu kết quả (chờ người dùng restart worker)
- [x] Doc `architecture.md` khớp; ghi `docs/handoff/survey-quality-fixes.md`

## Câu hỏi mở
(điền khi gặp; hỏi người dùng thay vì đoán)
