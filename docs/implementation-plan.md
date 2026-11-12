# Kế hoạch triển khai

> Mẫu cho mọi task >1 tệp. Mỗi bước phải có cách kiểm chứng. Bản dưới là cho task hiện tại (xem `current-task.md`).

## Nguyên tắc
Thứ tự: schema/model -> logic thuần (có test) -> node/route -> tích hợp -> doc. Mỗi bước kết thúc bằng lệnh kiểm chứng xanh rồi mới sang bước sau.

## Các bước (Ledger dày hơn — kết quả thực nghiệm từ nhiều paper hơn; bàn giao `handoff/ledger-ket-qua-thuc-nghiem.md`)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | `collect_result_chunks`: mỗi paper trong phạm vi (kho nhỏ) lấy 3 chunk theo truy vấn "bảng kết quả + metric lĩnh vực"; search_node lưu `result_evidence` | `tools/ensure_coverage.py`, `nodes/search_node.py`, `state.py` | test: mỗi paper được gọi `search_hybrid(paper_id=)`; kho lớn/Qdrant lỗi → [] |
| 2 | analyze_node trích từ `evidence + result_evidence`; cảnh báo log khi <50% paper có kết quả | `nodes/analyze_node.py` | test: chunk chỉ có trong `result_evidence` vẫn vào ledger |
| 3 | Extractor: 6 chunk/paper, 3000 ký tự/chunk, ngân sách 2400s, `_KEY_RE` + prompt thêm sensitivity/specificity/precision/recall/PSNR/SSIM/Jaccard...; bỏ chunk trùng id | `evidence/extractor.py` | test `_paper_chunks` nhận PSNR/sensitivity, khử trùng |
| 4 | Doc + `ruff check app tests` + `pytest app/agent -q` | `docs/architecture.md` | xanh |

## Các bước (Đánh giá Q1/Q2 lần 4 — kiểm chứng trên bản cuối, task hiện tại; chi tiết phát hiện ở `current-task.md`)
Thứ tự bắt buộc (bước sau dùng kết quả bước trước). Mỗi bước: test mới + `ruff check` tệp đã sửa + `pytest <tệp test>` xanh.
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | `final_citation_list` (ánh xạ [n] mới → Citation) ; `run_quality_gate(..., numbered_citations=)`; gate lần 2 trên bản cuối, `validation_report` = gate cuối + `draft_gate` (số lỗi bản thô) | `citation_cleaner.py`, `quality_gate.py`, `synthesize_node.py` | test: sau remap, số [n] mới truy được đúng paper; gate cuối bắt giá trị lọt vào sau khi chèn bảng |
| 2 | `redact_untraced_cells(text, records)` thay ô UNTRACED trong bảng bằng "—" + dòng chú thích; chạy trước gate cuối | `evidence/redact.py` (mới), `synthesize_node.py` | test: ô không có nguồn → "—", ô TRACED/năm/Δ giữ nguyên, JSON bảng vẫn hợp lệ |
| 3 | Facts sổ cái + `check_ledger_claims` (N bản ghi/M paper, "exhaustive") + `check_internal_contradictions` ("no … all 15 subsets" vs "[n] evaluate all 15") ; `check_absence_claims` không bỏ sót khi groups==0 | `consistency_check.py`, `science_qa.py`, `synthesize_node.py` | test từng check có ca đúng/sai |
| 4 | `_collect_figures`: neo miền (IDF trong pool hình); hình kết quả không neo → bỏ; hình kiến trúc giữ | `synthesize_node.py` | test: caption abdominal/microscopy bị bỏ, caption BraTS giữ |
| 5 | Overclaim ra thân bài (necessary/always/zero…) ; quy tắc hedging trong `_global_standards` | `science_qa.py`, `synthesize_node.py` | test |
| 6 | `check_scope` chiều ngược (References vượt dải năm Abstract) + dải năm thật trong facts | `science_qa.py`, `synthesize_node.py` | test |
| 7 | Misattribution trên bản cuối (corpus = title catalog + tên model sổ cái) | `quality_gate.py` | test: "Swin UNETR [1]" với [1] = nnU-Net Revisited → cảnh báo |
| 8 | Doc + ADR + handoff | `docs/architecture.md`, `docs/decisions/`, `docs/handoff/` | đối chiếu |
Rủi ro: redact quá tay nếu `evidence` chỉ là chunk đã truy xuất (không phải cả PDF) → ô thật nhưng chưa truy xuất cũng bị "—"; chấp nhận vì chính sách gate là "không có nguồn thì không là số liệu". Gate lần 2 tốn thêm vài giây, không gọi LLM.

## Các bước (Sửa lỗi hệ thống theo đánh giá Q1/Q2 lần 2)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | Variant "Missing X" → tập modality; EVIDENCE LIMITS 3 mức; `study_profile_table` | `evidence/quant_analysis.py` | test: ablation thiếu modality → limits không nói "no source"; bảng profile có NR |
| 2 | Gộp `[n]–[n]` | `evidence/citation_cleaner.py` | test |
| 3 | Bỏ placeholder tác giả; xóa caption Figure thừa trước khối hình | `format_sanitizer.py`, `synthesize_node.py` | test sanitizer |
| 4 | Prompt survey (taxonomy, RQ, 4.5, 6.4, đơn vị Dice, không trích corpus) + REVIEW FACTS paper không truy xuất | `nodes/synthesize_node.py` | test prompt chứa quy tắc |
| 5 | WARNING cột Dice trộn thang | `evidence/consistency_check.py` | test |
| 6 | Doc | `docs/architecture.md` | đối chiếu |

## Các bước (đợt trước: spread/efficiency — đã xong)
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | Thêm `spread`, `spread_type` vào `ResultRecord` | `evidence/quant_check.py` | `test_records_roundtrip` + dữ liệu cũ không có trường |
| 2 | Extractor yêu cầu và kiểm chứng spread nguyên văn | `evidence/extractor.py` | test: spread có/không trong chunk, loại sai số lạ |
| 3 | `efficiency_table`, cột spread ở `delta_table`, cập nhật `evidence_limits` | `evidence/quant_analysis.py` | test bảng chỉ sinh khi đủ dữ liệu; NR cho ô thiếu |
| 4 | Caption biểu đồ nêu loại sai số | `nodes/synthesize_node.py` (`_CHART_BLOCK_RULE`) | test prompt chứa quy tắc |
| 5 | Doc + danh sách paper | `docs/architecture.md`, `docs/paper-wishlist.md` | đối chiếu thủ công |

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

### References phủ đủ 55 paper (2026-11-08)
- [x] Dọn task: không có task research đang chạy; xóa 3 dòng `research_tasks` failed; giữ 24 message `process_paper` trong `upload_queue` (nạp 24 paper pending).
- [x] `build_context(diversify=True)`: chia ngân sách token theo paper khi chunk đầu của mọi paper vượt `context_token_limit` (trung bình ~790 token/chunk → 55 paper cần ~44k > 22000). Kiểm chứng: `pytest app/ai/tests/test_context_builder.py`.
- [x] README: worker nghe `upload_queue,research_queue`.
- [ ] Chạy thật: papers `done|55`, survey mới có References 55 paper (quality gate không cảnh báo `độ phủ kho`).

### Chart Selection Policy + Figure Layout hai cột (2026-11-08) — theo đánh giá PDF survey_58ad3caf
Nguyên nhân: CSS `.columns-2 > figure.fig { column-span: all }` ép mọi hình trải 2 cột → Chromium cân bằng cột trước/sau hình, sinh khoảng trắng; prompt `_CHART_BLOCK_RULE` mặc định grouped bar; renderer thiếu dot/dumbbell/evidence map; heatmap một ô NR làm mất cả hàng.
- [x] `app/pipeline/export/figure_layout.py`: `chart_span(spec)`/`mermaid_span(code)` → `column` (mặc định) | `wide`; `chart_width(span)`. Test: `pytest app/agent/tests/test_figure_layout.py`.
- [x] `chart_scientific.py`: thêm `dot`, `dumbbell`, `evidence_map`; heatmap giữ ô NR (xám, chữ "NR"), Δ có âm/dương → colormap phân kỳ. Kích thước theo span. Test: `test_pdf_renderer.py::test_scientific_chart_types_render`.
- [x] `pdf_renderer.py`: figure một cột mặc định, `class="fig wide"` mới `column-span: all`; bar/line vẽ theo bề rộng cột. Typst: chart/mermaid `wide` dùng `scope: "parent"`. Test: hình một cột nằm trong 1 cột, không trải hết trang.
- [x] `evidence/figure_policy.py`: bar 2 series dạng điều kiện ghép cặp (validation/test, with/without, full/missing) → tự đổi sang `dumbbell`; cảnh báo quality gate khi >2 biểu đồ cột hoặc biểu đồ chỉ lặp lại bảng. Test: `pytest app/agent/tests/test_figure_policy.py`.
- [x] Prompt `_CHART_BLOCK_RULE`: chọn biểu đồ theo câu hỏi khoa học (dot/dumbbell/heatmap/evidence map/line), 5 điều kiện bắt buộc, trường `layout`. Doc: architecture.md.
- [x] `browser_renderer.prepare_report_page`: co SVG theo bề rộng figure (trước đây theo bề rộng trang → hình một cột bị letterbox, sinh khoảng trắng).
- [ ] Chạy thật survey mới, xem PDF: số biểu đồ cột ≤2, hình một cột không để trống cột.

### Sửa lỗi hệ thống theo đánh giá `survey-b1e8d2cc` (2026-11-09)
Nguyên nhân gốc đã kiểm chứng: (a) mọi regex trích dẫn chỉ nhận `[n]` đơn → `[7, 73]` không được đánh số lại/xóa, References dừng ở [36];
(b) research chạy bằng admin có phạm vi `None` → `ensure_coverage`/retrieval lấy chunk của paper mồ côi trong Qdrant (không có trong DB) → "Anonymous"/UUID;
(c) không kiểm tra "N papers" so với kích thước corpus (LLM suy 73 từ chỉ số [n] của chunk).
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | Tách cụm `[7, 73]`/`[3–5]` thành marker đơn trước khi đánh số lại; validator đếm số trong cụm | `evidence/citation_validator.py`, `evidence/citation_cleaner.py` | `pytest app/agent/tests/test_citation_validator.py app/agent/tests/test_citation_cleaner.py` |
| 2 | Phạm vi research = paper `done` trong DB (giao với phạm vi người dùng) → loại vector mồ côi | `pipeline/tasks.py` | test tasks/scope |
| 3 | REVIEW FACTS: "[n] là đoạn trích, không phải paper"; kiểm tra "N papers/studies" > corpus; reference không xác định danh tính (Anonymous/UUID) = lỗi trong validation_report | `nodes/synthesize_node.py`, `evidence/consistency_check.py` | test check |
| 4 | Cổng liên quan cho hình trích từ PDF (caption ↔ câu hỏi) | `nodes/synthesize_node.py::_collect_figures` | test |
| 5 | Mâu thuẫn: claim "no missing-modality result" khi bảng có hàng thiếu modality; cờ audit = "not found in retrieved passages"; mẫu số thống nhất | `evidence/science_qa.py`, `evidence/quant_analysis.py` | test |
Trạng thái: bước 1–4 xong (`pytest app/agent app/pipeline` 338 passed); bước 5 chưa làm.
Ngoài phạm vi (việc nghiên cứu của người dùng): PRISMA/tìm CSDL/sàng lọc/risk-of-bias thật.

### Fallback rate limit OpenRouter -> Groq (2026-11-09)
Khi provider chính OpenRouter trả 429, gọi lại cùng lời gọi trên Groq (`GROQ_MODEL`); chỉ kích hoạt khi có `GROQ_API_KEY`, lỗi khác không fallback.
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | OpenRouter 429 -> `LLMRateLimitError` kèm `retry_after` từ header | `llm_gateway/openrouter_adapter.py` | `pytest app/ai/tests/test_openrouter_adapter.py` |
| 2 | `FallbackGateway`: bắt `LLMRateLimitError` rồi gọi Groq; lỗi khác raise nguyên trạng | `llm_gateway/fallback.py` | `pytest app/ai/tests/test_fallback_gateway.py` |
| 3 | Chọn gateway: OpenRouter + Groq key -> `FallbackGateway`, không có key -> OpenRouter đơn lẻ | `llm_gateway/default.py` | `pytest app/ai/tests/test_default_gateway.py` |
Kiểm chứng tổng: `venv/bin/pytest app/ai/tests -q -p no:cacheprovider` (76 passed).

## Workspace (phiên/đề tài) — cách ly paper theo đề tài trong cùng một user
Mục tiêu: upload tập paper vào workspace A → research/chat của A chỉ truy xuất paper của A; workspace B (cùng user) không thấy paper A.
Thiết kế: `workspaces(id, user_id, name, created_at)`; `papers.workspace_id`, `research_tasks.workspace_id` (nullable, không FK cứng, giống `user_id`).
Phạm vi truy xuất (`allowed_paper_ids_for(db, user, workspace_id)`): có workspace → chỉ paper của workspace đó; không workspace → user thường chỉ thấy paper CHƯA gán workspace (paper đã gán không rò sang lượt không chỉ định phiên); admin không workspace → giữ nguyên (toàn bộ).
| # | Bước | Kiểm chứng |
|---|---|---|
| 1 | Model `Workspace`, thêm cột 2 bảng, migration 0009 (không chạy trên DB thật) | `pytest app/api/tests/test_models.py` |
| 2 | `scope.allowed_paper_ids_for(..., workspace_id)` | test scope |
| 3 | `/workspaces` (POST, GET); `/papers/upload?workspace_id=`; `GET /papers?workspace_id=`; `ResearchRequest.workspace_id`; chat theo workspace của research task; `run_research` dùng workspace | `pytest app/api -q` |
| 4 | `scripts/assign_papers.py --workspace TÊN` (tạo nếu chưa có) | `pytest app/pipeline/tests/test_seed.py` |
| 5 | Doc: api-contracts, database-schema, architecture, README | đối chiếu thủ công |
Không làm: frontend, xoá workspace (xoá từng paper như cũ), paper dùng chung nhiều workspace.

## Hệ thống hình theo đánh giá phần hình của `survey_c5d84302.pdf` (2026-11-09)
Đối chiếu đánh giá với report markdown (task c5d84302) + code. PDF sinh lúc 12:15, TRƯỚC commit 17:09 thêm ma trận 15 tập modality
(`modality_coverage_matrix`) và heatmap suy giảm (`modality_degradation_chart`) → hai hình "thiếu" đã có code, chỉ cần chạy lại survey.
Lỗi THẬT do hệ thống còn lại (đã xác minh trên markdown):
| # | Phát hiện | Việc | Tệp | Kiểm chứng |
|---|---|---|---|---|
| 1 | "Figure 7: Computational cost…" là đoạn chú thích mồ côi: khối chart bị validator bỏ nhưng đoạn `**Figure N:…**` vẫn còn → hai Figure 7 | Bỏ đoạn chú thích Figure không còn khối hình đi kèm (trước khi đánh số lại) | `evidence/report_structure.py`, `synthesize_node.py` | test: chart bị bỏ → chú thích + đánh số liên tục |
| 2 | Figure 5 trộn BraTS 2020 hidden test với 2021 validation, % với tỉ lệ trong một panel (LLM vi phạm luật) | Chặn chart so sánh có ≥2 edition/split/đơn vị trong caption/nhãn | `report_postprocess.py` | test: caption 2 năm/2 split → bị bỏ |
| 3 | Thay thế cho #2: so sánh full-modality theo TỪNG protocol | `protocol_panels`: dot chart mỗi setting (≥3 phương pháp) dựng từ record đã kiểm chứng; loại chart `panels` (small multiples, chú giải chung — cũng phủ dạng lưới line chart) | `quant_analysis.py`, `chart_scientific.py` | test render SVG + spec |
| 4 | Scatter chi phí/độ bền chỉ vài điểm | Scatter cần ≥4 điểm cùng setting (LLM và tất định); thay bằng evidence map "mức báo cáo chi phí" (Params/FLOPs/latency/training time/memory/energy × phương pháp) từ record | `report_postprocess.py`, `quant_analysis.py` | test |
| 5 | Không có sơ đồ hình thành corpus (khi không có review_protocol.json) | Sơ đồ luồng trung thực từ số đếm thật (corpus → được truy xuất → được trích dẫn → có số liệu), ghi rõ "không phải PRISMA" | `evidence/corpus_flow.py` (mới), `synthesize_node.py` | test |
| 6 | Taxonomy mermaid quá ngang, chữ nhỏ | `graph TD` có nhánh >4 con → `flowchart LR` | `report_postprocess.py` | test |
| 7 | Thiếu timeline + roadmap | Loại chart `timeline` (năm lấy từ References, không tin LLM) + luật prompt; roadmap gap→hướng→protocol bằng mermaid ở Stage 5 | `chart_scientific.py`, `synthesize_node.py` | test render + kiểm năm |
Không làm: hình định tính BraTS (hệ thống chỉ dùng hình có thật trong corpus; lọc hình lạc miền đã làm ở lần 4 #4 — không bịa ảnh).

## Kiểm tra bổ sung theo checklist hình thức Q1/Q2 (chỉ cảnh báo, tất định, không gọi LLM)
- `consistency_check._check_abstract_content`: Abstract phải nêu phương pháp review, số paper, phát hiện định lượng chính, đóng góp.
- `consistency_check.check_acronyms`: viết tắt dùng ≥3 lần mà chưa định nghĩa dạng "Tên đầy đủ (ACR)"; ≥8 viết tắt mà không có mục Abbreviations → cảnh báo (chưa TỰ SINH bảng viết tắt).
- `science_qa._TERM_GROUPS`: thêm nhóm thuật ngữ deepfake/đa phương thức (deepfake, multimodal, cross-modal, cross-dataset, cross-generator, vision-language, AUROC, Celeb-DF) và full-modal.
- `evidence/ledger_export.py` + `tasks._save_ledger_csv`: xuất sổ cái ra `<upload_dir>/ledger/<task_id>.csv` (supplementary: paper_file, dataset, split, metric, value, unit, trang/bảng, lỗi nội tại).
Kiểm chứng: `pytest app/agent/tests/test_report_checks.py app/agent/tests/test_science_qa.py app/agent/tests/test_evidence_pipeline.py`.
Chưa làm: tự sinh bảng viết tắt; kiểm caption bảng (đơn vị/protocol/nguồn); đối chiếu Journal fit; kiểm DPI/cỡ chữ hình.


## Repair tất định sau Quality Gate (survey brain `5a736250`, 2026-11-11)
Brief: `docs/handoff/sua-loi-chan-survey-5a736250.md`. Gate chỉ báo; thêm bước sửa tất định cho 4 nhóm lỗi chặn + 2 lỗi tham chiếu.
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| 1 | `repair_chart_regions`, `redact_untraced_chart_points`, `repair_ledger_claims`, `add_uncited_corpus` | `evidence/repair.py` (mới) | `pytest app/agent/tests/test_repair.py` |
| 2 | Nối vào `synthesize_node`: (d) trước dedupe; (a)(c) trước `finalize_structure_report`; (b) trong `_verify_final_report` | `nodes/synthesize_node.py` | `pytest app/agent/tests/test_synthesize_node.py` |
| 3 | `strip_dangling_citations` bắt `[n, Table k]`; ref Table/Figure khớp lại theo từ khoá caption | `evidence/report_structure.py` | `pytest app/agent/tests/test_report_structure.py` |
| 4 | Doc kiến trúc | `docs/architecture.md` | đối chiếu |
Kiểm chứng tổng: `venv/bin/python -m ruff check app` + `venv/bin/python -m pytest app/agent -q`. Bước chạy lại research (test5) để người dùng làm.

## Sửa hệ thống theo đánh giá reviewer `paper_5a736250_test5_latex.pdf` (2026-11-11)
Bàn giao: `docs/handoff/paper-review-improvements.md`. Sửa bộ sinh, không sửa tay bài test5. Ưu tiên lỗi học thuật.
| # | Việc | Tệp chính | Kiểm chứng |
|---|---|---|---|
| 1 ✅ | Citation trong caption/ô chart-table phải khớp paper_id nguồn của record; lệch → lỗi BLOCKING ở gate (+ repair tất định nếu map được) | quant_analysis/quant_check/quality_gate, chart_scientific | test_quality_gate, test_quant_* |
| 2 ✅ | Chặn claim "first survey/first framework…" chưa kiểm chứng; bảng so survey chỉ giữ survey cùng chủ đề | quality_gate, synthesize_node | test_quality_gate |
| 3 ✅ | RQ chỉ nêu một lần (Intro), kiểm tra cấu trúc bắt lặp (đặt ở `rq_sync.py`: `dedupe_rq_definitions`, `check_rq_repetition`) | rq_sync, quality_gate, synthesize_node | test_rq_sync |
| 4 ✅ | Phân loại bằng chứng: trực tiếp trên dataset đích / dataset khác / tham khảo kiến trúc | evidence_tiers (mới), quant_analysis.study_profile_table, synthesize_node._evidence_limits_text | test_evidence_tiers |
| 5 ✅ | Methodology tự sinh: loại survey, số bài, số record/bài có số liệu, giới hạn (không screening độc lập, không RoB/GRADE) | repair.ensure_methodology_disclosure, synthesize_node (_review_facts + gọi sau soften_novelty_claims) | test_quality_gate |
| 6 ✅ (xem mục a–g bên dưới) | Trình bày LaTeX: tác giả/affiliation/email TỰ ĐIỀN theo hệ thống PaperAI (người dùng chốt 2026-11-11, không lấy từ profile); bảng `\footnotesize` + tách bảng dài; taxonomy tách trục, bỏ cite ở nhãn lá; caption ngắn | latex_renderer, figure_layout | test_latex_renderer |
| 7 ✅ (mục h; chuẩn hoá references chưa làm) | Back matter: Data/Code Availability + placeholder Funding/CoI/Contributions; chuẩn hoá references | latex_renderer, bibliography | test_latex_renderer |
Kiểm chứng tổng: `venv/bin/python -m ruff check app` + `venv/bin/python -m pytest app/agent -q`.

### Việc 6–7 + lỗi trình bày LaTeX phát hiện khi xem test6 (2026-11-11) — ✅ a–h xong
| # | Việc | Tệp | Kiểm chứng |
|---|---|---|---|
| a | Taxonomy (cây mermaid gốc→trục→lá) xuất LaTeX thành hình bảng native: mỗi trục một cột, bỏ cite/`<br/>` ở nhãn lá | latex_renderer (`_taxonomy_figure`) | test_latex_renderer |
| b | Caption hình: bỏ cụm ≥4 trích dẫn (caption ngắn) | latex_renderer `_clean_caption` | test_latex_renderer |
| c | Font toán kiểu Times (newtxmath) thay Computer Modern | latex_renderer `_COMMON_PACKAGES` | biên dịch test6, `pdffonts` không còn CMR/CMMI |
| d | Font hình thống nhất Liberation Sans (Arial) 8pt cho chart matplotlib + Mermaid | chart_scientific, pdf_renderer, browser_renderer | test chart + pdffonts |
| e | Sơ đồ corpus flow vẽ ngang (LR), trải cả trang; timeline thấp hơn khi ít sự kiện | corpus_flow, figure_layout, chart_scientific | test_corpus_flow/figure_layout |
| f | IEEE: "Table N" trong thân bài → số La Mã (trừ "Table N of [k]"/locator trong []) | latex_renderer | test_latex_renderer |
| g | Evidence map: nhãn trục to hơn | chart_scientific | xem ảnh |
| h | Back matter: Data/Code Availability (sự thật hệ thống) + placeholder Funding/CoI/Contributions nếu bài chưa có | latex_renderer | test_latex_renderer |
Kiểm chứng tổng: pytest app/agent app/pipeline app/api; xuất lại `data/exports/paper_5a736250_test6_latex.pdf` và xem ảnh trang.
