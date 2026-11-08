# Bàn giao: sửa hệ thống theo đánh giá Q1/Q2 lần 2 (2026-11-08)

Bài bị đánh giá: `survey_58ad3caf` ("Fusion Strategies and Missing-Modality Robustness…"). Phạm vi + bảng nguyên nhân gốc: `docs/current-task.md`.

## Đã làm (code + test; `pytest app/agent`, `app/pipeline` pass; chưa chạy trên survey thật)
- `quant_analysis`: variant "Missing X"/"w/o X" → tập modality còn lại (sửa mâu thuẫn "không có degradation matrix" ↔ bảng ablation); EVIDENCE LIMITS 3 mức + cấm trích dẫn cho câu nói về corpus; `study_profile_table`.
- `consistency_check._check_dice_scale`: WARNING khi cột Dice trộn tỷ lệ/% (bắt đúng Table 3, 5 của bài cũ).
- `format_sanitizer`: bỏ tác giả/đơn vị giữ chỗ; bỏ caption "**Figure N: …**" thừa trên khối image/chart/table. `pdf_renderer` lọc placeholder ở bản Markdown cũ.
- `citation_cleaner`: `[n]–[n]` → `[n]`.
- Prompt survey: khung đa trục (không "orthogonal"), RQ phải trả lời được bằng bằng chứng, mục 4.5 Critical Comparative Analysis, 6.4 có gap/vì sao/cách đánh giá, quy tắc đơn vị Dice + NR + không lặp bảng; REVIEW FACTS nêu số paper corpus không được truy xuất.

## Cố ý không làm
- PRISMA, tìm kiếm đa CSDL, 2 người đánh giá, risk-of-bias: việc nghiên cứu thật của người dùng; hệ thống không được dựng giả.
- Không tự đổi Dice %↔tỷ lệ (traceability coi số đã đổi là không có nguồn) — chỉ cảnh báo + quy tắc prompt.
- Tham chiếu chéo "Figure N" trong văn bản vẫn có thể lệch với số renderer đánh lại.

## Đang chờ
- Restart worker + chạy lại survey để kiểm chứng (ma trận missing-modality, bảng hồ sơ, không còn cảnh báo trộn Dice).
- Người dùng mở rộng corpus (wishlist `docs/paper-wishlist.md`) — điều kiện bắt buộc để hướng Q1/Q2.
- `data/papers_brain/catalog.json` đang bị sửa ngoài task này.
- Lỗi lint có sẵn: SIM114 format_sanitizer, W293 citation_cleaner, SIM201 synthesize_node.
