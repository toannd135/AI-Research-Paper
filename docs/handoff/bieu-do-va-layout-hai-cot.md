# Bàn giao: Chart Selection Policy + Figure Layout hai cột (2026-11-08)

Yêu cầu: đọc đánh giá PDF survey_58ad3caf (lạm dụng biểu đồ cột; hình đặt giữa trang làm thừa khoảng trắng) và cải tiến hệ thống.

## Nguyên nhân
- CSS `.columns-2 > figure.fig { column-span: all }` ép mọi hình trải 2 cột. Ngoài ra `browser_renderer.prepare_report_page` co SVG theo bề rộng TRANG nên hình bị letterbox.
- Prompt `_CHART_BLOCK_RULE` mặc định dùng grouped bar. `build_ledger_charts` vẽ cùng một ma trận hai lần (bar + heatmap). `modality_degradation_chart` dùng bar. Heatmap gặp một ô NR thì mất cả hàng.

## Đã làm (test: `pytest app/agent app/ai app/pipeline` pass)
- `app/pipeline/export/figure_layout.py` (mới): `chart_span` / `mermaid_span` trả về column (mặc định) hoặc wide; vẽ rộng 3.4 in hoặc 6.9 in; spec có thể ghi `"layout"`.
- `pdf_renderer.py`: chỉ hình `.wide` mới trải 2 cột; bỏ width/height cố định của SVG. `browser_renderer.py`: co SVG theo bề rộng figure. `typst_renderer.py`: hình wide dùng `scope: "parent"`.
- `chart_scientific.py`: thêm `dot`, `dumbbell`, `evidence_map`; heatmap giữ ô NR, Δ âm/dương dùng RdBu, toàn âm dùng Reds_r.
- `evidence/figure_policy.py` (mới): bar hai điều kiện ghép cặp đổi thành dumbbell; nhiều phương pháp × metric đổi thành dot. Cảnh báo (qua `display_check`) khi có >2 biểu đồ cột, hai hình trùng dữ liệu, hoặc hình chỉ lặp lại một bảng.
- `quant_analysis.py`: `modality_degradation_chart` thành heatmap Δ (14 tập × ≤5 phương pháp, một setting). Hồ sơ nguồn >12 dòng chuyển thành evidence map (tiêu chí × nguồn).
- `report_postprocess.py`: chart `"derived": true` không qua scrub; evidence_map do LLM viết bị bỏ; ledger fallback chỉ còn dot + heatmap.
- Prompt `_CHART_BLOCK_RULE`: chọn loại hình theo câu hỏi, 5 điều kiện bắt buộc, quy tắc layout.
- Doc: architecture.md, implementation-plan.md. Ảnh PDF mẫu đã kiểm tra bằng mắt.

## Đang chờ
- Chạy survey thật (README; worker phải nghe `upload_queue,research_queue`) để xem PDF mới: ≤2 biểu đồ cột, không trống cột, có heatmap Δ và evidence map.
- Bảng `.tbl` vẫn luôn trải 2 cột (kể cả bảng ít cột); có thể áp dụng cùng policy nếu PDF mới còn khoảng trắng quanh bảng.
- Lỗi ruff có sẵn từ trước (không thuộc thay đổi này): B905 trong pdf_renderer/chart_scientific `_pairs`, F541 trong typst_renderer, SIM201 trong synthesize_node, I001 trong test_llm_registry.
