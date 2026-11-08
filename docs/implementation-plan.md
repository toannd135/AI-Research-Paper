# Kế hoạch triển khai

> Mẫu cho mọi task >1 tệp. Mỗi bước phải có cách kiểm chứng. Bản dưới là cho task hiện tại (xem `current-task.md`).

## Nguyên tắc
Thứ tự: schema/model -> logic thuần (có test) -> node/route -> tích hợp -> doc. Mỗi bước kết thúc bằng lệnh kiểm chứng xanh rồi mới sang bước sau.

## Các bước (Research Knowledge Model)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | Taxonomy + cấu trúc model (gaps/questions/claims/experiments) | `agent/research_model.py` | `pytest app/agent/tests/test_research_model.py` |
| 2 | Validator claim↔evidence | `agent/evidence/claim_validator.py` | unit test: claim có/không evidence, evidence lạ |
| 3 | `model_node` + state | `nodes/model_node.py`, `state.py` | test node với fake LLM, JSON sai -> fallback |
| 4 | Nối vào graph | `graph.py` | `test_graph.py`: critique -> model -> synthesize |
| 5 | Lưu DB + migration | `models/research_task.py`, `0008_*`, `tasks.py` | upgrade/downgrade; test model |
| 6 | API trả `research_model` | `routes/research.py`, `schemas.py` | `pytest app/api/tests/test_research_route.py` |
| 7 | Prompt synthesize dùng model | `synthesize_node.py`, `plan_node.py` | test synthesize + postprocess |
| 8 | Doc + handoff | `docs/*` | đối chiếu thủ công |

## Rủi ro
- LLM trả JSON hỏng -> luôn có fallback, không raise ra ngoài node.
- Task cũ không có `research_model` -> mọi nơi đọc phải chấp nhận `None`.
- Chạy migration nhầm DB -> chỉ chạy khi người dùng đồng ý.

## Định nghĩa xong
Toàn bộ tiêu chí trong `current-task.md` được tick.

## Nâng chuẩn Survey theo đánh giá Q1–Q4 (prompt/cấu trúc, đã làm)
- `synthesize_node.py`: survey có mục 2 Review Methodology (RQ, corpus/search/selection, trích xuất & đánh giá chất lượng, so sánh survey có sẵn) rồi mới tới Taxonomy; đánh số lại 3–7. `_review_facts` chỉ đưa số liệu thật (corpus, truy vấn, số paper, ngày) — cấm bịa CSDL/PRISMA.
- Quy tắc so sánh Dice/HD95: chỉ so khi cùng dataset-version/split/vùng/metric; biểu đồ chỉ trong một bối cảnh so sánh được; ảnh phải ghi nguồn và giấy phép; `MAX_PROMPT_FIGURES` 8→4; survey cần ≥4 bảng (taxonomy, dataset+metric, so sánh, điểm mạnh/hạn chế).
- Kiểm chứng: `pytest app/agent -q` (test_paper_profiles có 2 test mới).

## Scientific Quality Gate P0 (đã làm, code tất định, không gọi LLM)
- `evidence/quant_check.py`: `ResultRecord`, `compare` (COMPARABLE / CONDITIONALLY_COMPARABLE / NOT_COMPARABLE / UNVERIFIED), `group_comparable`, `validate_record` (Dice miền hợp lệ, HD95 không âm, không tự đổi %↔tỷ lệ, bắt buộc nguồn PDF), `check_chart_block` (cấm trộn vùng WT/TC/ET hoặc nhiều metric trên một trục).
- `evidence/reference_check.py`: VERIFIED / PARTIALLY_VERIFIED / UNVERIFIED / CONFLICT (trùng tiêu đề) / INVALID (DOI, năm sai), chỉ dựa catalog, không gọi mạng.
- `evidence/traceability.py`: mỗi số trong ```table/```chart → [n] của hàng/caption → chunk chứa đúng con số (trang) + sha256 PDF; TRACED / UNTRACED / NO_CITATION.
- `evidence/quality_gate.py` gom thành `validation_report` (`passed`, `blocking`, `warnings`); gọi trong `synthesize_node` trước khi đánh số lại [n]; `tasks.py` ghi `<upload_dir>/validation/<task_id>.json`. Test: `app/agent/tests/test_quality_gate.py`.
- Dòng tác giả "PaperAI Automated Research Protocol" chỉ là placeholder: renderer PDF/LaTeX/Typst đã bỏ nó khỏi trang đầu. Mục theo đối tượng: `lecturer` không thêm mục nào; `student`/`professional` vẫn thêm mục cuối bài.

## Việc còn lại (chưa làm)
- Chặn export khi `validation_report.passed = false` (routes export) và vòng "Return to Agent" để sửa/sinh lại.
- Trích `ResultRecord` có cấu trúc từ PDF (dataset version, split, region, trang/bảng) — hiện gate chỉ kiểm tra số trong ```table/```chart bằng khớp nguyên văn trong chunk, chưa dựng record đầy đủ.
- Reference lớp A qua Crossref/OpenAlex (mạng) và lớp B: luận điểm có nằm trong paper không.
- Citation Coverage Checker, Taxonomy Validation, hồ sơ khai báo dùng AI trong bản thảo, chạy hồi quy full survey sau khi OpenRouter có quota.

## Lộ trình theo đánh giá #3 (chưa làm — thực thi ở phiên mới, theo thứ tự, KHÔNG làm song song)
Nguyên tắc: hoàn thiện Narrative Review (đề tài Brain Tumor Segmentation làm benchmark) trước; chưa mở rộng Original Research / Systematic Review / reviewer agents. Chuỗi cần chứng minh: PDF → Evidence → QuantitativeResult → Claim → Citation → Manuscript → Validation Report.

### P0 (bắt buộc trước khi gọi là publication-ready)
1. Structured evidence extraction: trích `QuantitativeResult` từ PDF (model, dataset, dataset_version, split, region, metric, value, source_document_id, page, table; trường paper không nêu để `None`, KHÔNG để LLM điền). Mức provenance thấp hơn nếu không có tọa độ ô bảng.
2. Chuẩn hóa `QuantitativeResult` + comparability dùng record thật (đổi tên trạng thái cho thống nhất: COMPARABLE / PARTIALLY_COMPARABLE / NOT_COMPARABLE; mở rộng điều kiện: evaluation protocol, cỡ mẫu, model variant).
3. Traceability end-to-end claim → result → evidence → PDF → page/table (chứng minh bằng chạy thật, không chỉ có module).
4. Quality gate thành cổng thật: phân BLOCKING / WARNING / INFO; BLOCKING chặn export bản gắn nhãn publication-ready (routes export + vòng sửa/sinh lại); report ≠ quyền export.
5. `reference_check`: không dùng nhãn VERIFIED khi chỉ khớp catalog → đổi thành CATALOG_MATCHED; VERIFIED chỉ khi có nguồn độc lập (P1).
6. Chạy lại 1 Narrative Review đầy đủ từ corpus 31 PDF sau khi OpenRouter có quota (07:00 08/11), lưu output + validation_report, đánh giá thủ công từng claim/số liệu/citation/hình/bảng.

### P1
7. External Reference Verification (Crossref, OpenAlex; xung đột → CONFLICT, kiểm tra tay). 8. Citation-to-claim (`CitationSupport`: DIRECT/PARTIAL/CONTRADICTS/CONTEXT_ONLY/UNSUPPORTED) + đo: unique references used, citation coverage, correctness, source diversity (không ép đủ 25). 9. AI Disclosure checker theo chính sách tạp chí (không chèn câu chung). 10. Figure/Table checker: số thứ tự không trùng/thiếu, caption, được nhắc trong thân bài, nguồn + giấy phép (ưu tiên hình tự vẽ từ dữ liệu đã trích). 11. Novelty: cấm "first/no previous study" khi chưa có tìm kiếm rộng; dùng "updated synthesis", "the reviewed corpus indicates".

### Chỉnh prompt nhỏ (làm cùng P0)
- Intro 1.3 chỉ giới thiệu RQ + lý do; 2.1 giải thích corpus/phương pháp dùng để trả lời RQ (tránh trùng). 5.3 Qualitative chỉ sinh khi corpus có ảnh đối chiếu được. Appendix A chỉ sinh khi nguồn có chi tiết thật. Metadata tác giả thật thêm ở bước export.

### P2: Journal discovery/profile/template adapter, reviewer agents, benchmark & regression.

### Bộ test cài lỗi cố ý (gate phải bắt được hết mới coi là xong)
DOI đúng nhưng title sai · citation không hỗ trợ claim · Dice WT gán thành ET · hai dataset version trong một chart · số liệu không có page provenance · hình không được nhắc trong thân bài · bảng lệch số thứ tự · claim novelty tuyệt đối không có bằng chứng.

### Cần kiểm tra
- Đánh giá nhắc "56 PDF"; bàn giao và catalog chỉ có 31 PDF — xác minh con số 56 từ đâu rồi thống nhất.
- Khóa OpenRouter đã lộ trong log phiên: người dùng revoke + tạo khóa mới, kiểm tra cả lịch sử commit/biến môi trường.

### Survey: tối thiểu 3 biểu đồ số liệu thật (2026-11-08)
- Vấn đề: lần chạy 4e8e0871 chỉ có 1 chart, lại dùng giá trị "relative" tự đặt + null (vi phạm quy tắc không bịa số).
- Bước 1: `synthesize_node.py` mục 5.4 survey yêu cầu ≥3 khối ```chart, mỗi khối đúng MỘT setting (dataset+version, vùng, metric), chỉ số thật có [n], cấm null/"relative"/số đọc từ ảnh. Kiểm chứng: `pytest app/agent/tests/test_synthesize_node.py`.
- Bước 2: `report_postprocess.py` thêm `build_ledger_charts(draft, n)` (mỗi nhóm metric+dataset ≥3 phương pháp, một chart/nhóm) và `postprocess_report(..., min_charts)`; bù chart từ ledger khi thiếu. Survey truyền `min_charts=3`. Kiểm chứng: `pytest app/agent/tests/test_report_postprocess.py`.
- Giới hạn trung thực: nếu ledger không đủ 3 nhóm ≥3 phương pháp thì KHÔNG bịa; chỉ bù được bấy nhiêu và ghi log cảnh báo.
- Bước 3 (đã làm): bỏ chữ "mandatory" — prompt chỉ đặt MỤC TIÊU 3 chart khác loại khi số liệu thật đủ (không bịa/độn số). Thêm `app/agent/evidence/display_check.py` (hạn mức hình/bảng theo paper_type: review 5–9/3–6, original_research 4–7/3–5, system 5–9/3–5 — benchmark nội bộ, KHÔNG phải chuẩn Q1–Q4) vào `quality_gate` → `validation_report.display_items` + WARNING (không chặn). Test: `app/agent/tests/test_display_check.py`.

### Nâng cấp 5 phase theo đánh giá (2026-11-08) — kiểm chứng: `pytest app/agent app/api -q` + `ruff` trên file đã sửa
- **P1 Evidence Extraction** — `app/agent/evidence/extractor.py`: LLM (gateway giả khi test) trích `ResultRecord` theo lô ≤5 paper; mỗi bản ghi PHẢI có giá trị xuất hiện NGUYÊN VĂN trong chunk của paper đó (lấy trang từ chunk), trường dataset/version/split không thấy trong chunk → `None`. Hiệu quả phụ (Params/GFLOPs/inference time) là record metric riêng. `analyze_node` ghi `state["results"]`. Tốn thêm ~⌈số paper/5⌉ lần gọi LLM mỗi paper.
- **P2 Grounded synthesis** — `ledger.py`: ledger dựng bằng code từ record (thay bảng LLM tự ghi), thiếu vùng/metric → `NR`; prompt cấm kết luận hơn/kém khi không COMPARABLE. Export PDF/LaTeX/BibTeX trả 409 khi `validation_report.passed=false` (`?draft=true` để vẫn tải bản nháp) → cập nhật `docs/api-contracts.md`.
- **P3 Consistency** — `consistency_check.py` (WARNING, không chặn): RQ Intro↔Conclusion, tên method theo [n] giữa các bảng, biến thể tên dataset, số trong Abstract có trong thân bài, đánh số Table/Figure, cân bằng công thức `$`/`{}`.
- **P4 Quant analysis** — `quant_analysis.py`: bảng Δ so với tốt nhất trong nhóm COMPARABLE (HD95 thấp hơn là tốt), Δ ablation (cùng paper+setting, có `variant`), scatter Dice–Params; khối `derived:true` được traceability bỏ qua. Chỉ sinh khi đủ điều kiện.
- **P5 Publication** — `VERIFIED`→`CATALOG_MATCHED` (VERIFIED chỉ khi Crossref khớp DOI+tiêu đề, `external_verify.py`, tắt mặc định `REFERENCE_EXTERNAL_VERIFY=false`, fetcher tiêm được để test không dùng mạng); kiểm tra độ dài Abstract 150–220 từ. Kiểm tra "ngôn ngữ khoa học" giữ nguyên bước dịch/làm sạch hiện có (không thêm mới).

## Sửa chất lượng survey theo nhận xét `survey_e329b04d.pdf` (task hiện tại)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | RQ một nguồn: blueprint sinh RQ chuẩn, tiêm vào chặng 1/2/5, `rq_sync` ép nguyên văn + check lệch Intro↔2.1 (chặn) | `evidence/rq_sync.py`, `synthesize_node.py`, `consistency_check.py`, `quality_gate.py` | `pytest app/agent/tests/test_rq_sync.py` |
| 2 | Tham chiếu Table/Figure mơ hồ gán theo ngữ cảnh; tham chiếu treo = chặn | `evidence/report_structure.py`, `display_check.py`, `quality_gate.py` | `pytest app/agent/tests/test_report_structure.py` |
| 3 | Gộp `[1], [1]`; CSS tiêu đề cột không bẻ giữa từ | `evidence/citation_cleaner.py`, `pipeline/export/pdf_renderer.py` | test cleaner + `pytest app/pipeline -q` |
| 4 | Ma trận missing-modality, Δ so với full, biểu đồ suy giảm; `evidence_limits` | `evidence/quant_analysis.py` | `pytest app/agent/tests/test_evidence_pipeline.py` |
| 5 | Methodology trung thực (check systematic/PRISMA), caption figure, tham số retrieval trong REVIEW FACTS, EVIDENCE LIMITS vào prompt | `synthesize_node.py`, `consistency_check.py`, `display_check.py` | test check + test prompt |
| 6 | Thống kê preprint / thiếu venue-DOI trong validation_report | `evidence/reference_check.py`, `quality_gate.py` | `pytest app/agent/tests/test_reference_check.py` |
| 7 | Doc + handoff | `docs/architecture.md`, `docs/handoff/` | đối chiếu thủ công |

Rủi ro: ép RQ bằng regex có thể ghi đè sai nếu số dòng RQ khác chuẩn -> chỉ ép khi số RQ khớp, ngược lại để nguyên và gate báo lỗi. Không bịa số để lấp ma trận.

### Mở rộng extractor cho metric phát hiện deepfake (2026-11-08)
- `evidence/extractor.py`: `_KEY_RE` + prompt thêm AUC/EER/ACC/F1/AP (region = null); `evidence/stats.py`: EER là "thấp hơn là tốt". Ma trận missing-modality vẫn chỉ cho MRI (không đổi). Kiểm chứng: `pytest app/agent/tests/test_evidence_pipeline.py` (thêm test deepfake).
