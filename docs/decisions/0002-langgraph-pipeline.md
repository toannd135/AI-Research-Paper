# 0002 — Agent là đồ thị LangGraph tuyến tính có vòng critique
Trạng thái: accepted
**Bối cảnh:** cần quy trình kiểm soát được, test được từng bước, có lặp khi thiếu bằng chứng.
**Quyết định:** `plan -> search -> analyze -> critique -(thiếu)-> analyze | -(đủ)-> model -> synthesize`. Mỗi node nhận `llm` inject được; test bằng fake gateway.
**Hệ quả:** thêm bước = thêm node + edge + test routing; không có agent tự do gọi tool vô hạn.
