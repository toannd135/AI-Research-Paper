# ADR 0010: Metadata của PDF tải lên đọc lúc chạy research, không đoán

**Bối cảnh.** Metadata reference chỉ đến từ `catalog.json` soạn tay. PDF người dùng tải lên không có trong đó nên reference bị điền năm 2024, venue "arXiv preprint", tiêu đề UUID; số bài trong prompt cũng là số của catalog chung.

**Quyết định.** Khi bắt đầu research, dựng catalog cho đúng phạm vi lượt chạy: paper có trong `catalog.json` dùng bản đó, paper còn lại đọc từ chính PDF (metadata nhúng, chữ lớn nhất trang đầu, DOI, năm ghi rõ). Trường nào không đọc được thì để trống và reference ghi `Unknown authors` / `n.d.`.

**Đánh đổi.** Không thêm cột DB hay migration, nhưng PDF được mở lại mỗi lượt chạy (chỉ trang đầu). Tác giả chỉ có khi PDF nhúng metadata, nên nhiều reference sẽ thiếu tác giả; trung thực hơn là đoán. Muốn đủ hơn thì sau này cho người dùng sửa metadata.
