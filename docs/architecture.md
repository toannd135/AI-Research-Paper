# Kiến trúc

## Thành phần
| Khối | Công nghệ | Vai trò |
|---|---|---|
| API | FastAPI (`app/main.py`, `app/api/routes`) | auth, papers, research, chat, sources |
| Worker | Celery + Redis (`app/workers`, `app/pipeline/tasks.py`) | `process_paper` (upload_queue), `run_research` (research_queue; time limit 1h) |
| DB | PostgreSQL + SQLAlchemy + Alembic | users, papers, research_tasks, conversations, messages |
| Vector | Qdrant (`app/pipeline/vector_store`) | collection `paper_chunks` |
| AI | `app/ai` | bge-m3 embedding, BM25 + vector -> hybrid, bge-reranker, context builder, LLM gateway đa nhà cung cấp |
| Agent | LangGraph (`app/agent`) | research pipeline có citation |
| Export | `app/pipeline/export` | Chromium (mặc định), Typst, LaTeX, BibTeX |
| Frontend | React+TS+Vite+antd (`frontend/`, submodule) | admin, client, auth, home |

## Luồng 1: nạp paper
upload `POST /papers/upload` -> lưu file `data/papers` (hash chống trùng) -> Celery `process_paper` -> parse PDF (`pipeline/parser`) -> chunk (`pipeline/chunking`) -> embed -> Qdrant; trích hình (`pipeline/figures.py`). Trạng thái ở `papers.status`.

## Luồng 2: research agent (`app/agent/graph.py`)
```
plan -> search -> analyze -> critique --(thiếu evidence)--> analyze
                                  \--(đủ)--> model -> synthesize -> END
```
- plan: làm rõ câu hỏi, đoán field/audience/contribution_type (`clarify.py`, `profiles.py`, `research_model.py`).
- search: RAG nội bộ (`tools/search_papers`, `retrieve_evidence`) + OpenAlex (`tools/search_external_papers`, lọc miền theo field).
- analyze/critique: trích finding, chấm đủ/thiếu. analyze còn trích `ResultRecord` có cấu trúc (`evidence/extractor.py`, lô ≤5 paper, giá trị phải có nguyên văn trong chunk) vào `state["results"]` và dựng Quantitative Evidence Ledger bằng code (`evidence/ledger.py`, thiếu = NR).
- search (chế độ chỉ-nội-bộ và phần nội bộ của chế độ có OpenAlex): `tools/ensure_coverage.py` bổ sung ≥1 chunk cho MỌI paper trong kho (Qdrant, theo phạm vi chủ sở hữu) khi kho ≤ `full_corpus_coverage_limit` (mặc định 80, 0 = tắt); `evidence/coverage.py` đặt mục tiêu cite = toàn bộ paper (kho lớn hơn: tối thiểu 25); quality gate cảnh báo `độ phủ kho: x/y` khi paper trong kho chưa được cite. `ai/context_builder.build_context(diversify=True)` (analyze) đặt chunk tốt nhất của mỗi paper lên trước; nếu tổng các chunk đầu vượt `context_token_limit` thì chia đều ngân sách theo paper (tối thiểu 150 token) và cắt ngắn chunk đầu theo ranh giới từ, để mọi paper đều vào context và được cite.
- Hình (Chart Selection Policy + Figure Layout): `evidence/figure_policy.py` đổi biểu đồ cột hai điều kiện ghép cặp (validation/test, có/không, full/thiếu) → `dumbbell`, nhiều phương pháp × metric → `dot` (chỉ đổi cách vẽ, giữ số) và cảnh báo quality gate khi >2 biểu đồ cột, hai hình cùng dữ liệu hoặc hình chỉ lặp một bảng. Hình tất định từ record: heatmap Δ so với full-modality của chính nguồn (14 tập thiếu × phương pháp, ô NR, một setting) và evidence map (tiêu chí × nguồn, Yes/No/NR từ câu nguyên văn) thay bảng hồ sơ khi >12 nguồn; khối `"derived": true` không qua scrub. Đợt hình (2026-11-09): `report_structure.align_figure_captions` đánh số '**Figure N:**' theo THỨ TỰ KHỐI hình (khớp renderer, kể cả khối tự chèn) và bỏ chú thích + câu nhắc tới hình ma (khối đã bị loại); `report_postprocess.reject_mixed_protocol` bỏ chart so sánh trộn phiên bản dataset/split/đơn vị trên một trục (chạy sau Chart Selection Policy), scatter cần ≥4 điểm; `quant_analysis.protocol_panels` thay bằng lưới `panels` (mỗi ô một setting, chú giải chung); `timeline` chỉ giữ mốc có năm trùng năm của reference [n]; mermaid TD có tầng >6 nút → LR; `evidence/corpus_flow.py` vẽ sơ đồ hình thành corpus từ số đếm của lần chạy (ghi rõ không phải PRISMA) khi không có review_protocol. Ledger fallback: dot + heatmap, không vẽ lại ma trận bằng bar. `pipeline/export/figure_layout.py`: PDF hai cột đặt hình trong MỘT cột (vẽ 3.4 in); chỉ `wide` (CSS `column-span: all`, Typst `scope: "parent"`) khi nhãn không đọc được trong một cột hoặc spec ghi `"layout": "wide"`.
- synthesize: sau khi ghép bài chạy Quality Gate (`evidence/quality_gate.py`: reference, truy vết số, so sánh được, hình/bảng, nhất quán) → `validation_report`; chèn bảng Δ/ablation/scatter suy ra từ record (`evidence/quant_analysis.py`, khối `derived:true`). Export PDF/LaTeX trả 409 khi `passed=false` (trừ `?draft=true`).
  - RQ một nguồn: blueprint (mục 7) sinh RQ chuẩn → `evidence/rq_sync.py` tiêm vào chặng 1/2/5 và ép nguyên văn vào mọi mục "Research Questions" sau khi ghép; RQ lệch giữa các mục = lỗi chặn (`validation_report.research_questions`).
  - Sau `finalize_structure_report` (đánh số lại Table/Figure, tham chiếu mơ hồ gán theo ngữ cảnh): tham chiếu treo = lỗi chặn, gán theo vị trí = cảnh báo; gộp vào report bằng `quality_gate.merge_structure_issues`.
  - `consistency_check.check_review_claims`: tự nhận systematic review/PRISMA mà không phủ định = lỗi chặn. `display_check.check_figure_captions`: caption chung chung/trùng, ảnh thiếu nguồn [n]/giấy phép = cảnh báo. `reference_check.classify_publication`: thống kê preprint/đã xuất bản, cảnh báo thiếu metadata.
  - `quant_analysis`: ma trận missing-modality (`ResultRecord.modality`), Δ so với full CHỈ khi cùng nguồn báo full, biểu đồ theo tập modality; `efficiency_table` (Params/GFLOPs/InferenceTime theo phương pháp, ô thiếu = NR, caption nói rõ không so sánh trực tiếp giữa nguồn); `ResultRecord.spread`/`spread_type` (SD|SE|CI95) chỉ giữ khi số `± x` in nguyên văn trong chunk, hiện ở cột Spread của bảng Δ (bỏ cột khi không nguồn nào báo) và ở Notes của ledger; `evidence_limits` đưa giới hạn thật (số bản ghi có spread, ma trận thiếu) vào prompt Limitations. Thiếu số liệu thì ghi hạn chế, không chặn export.
  - Đợt đánh giá Q1/Q2 lần 2: biến thể ablation 'Missing X'/'w/o X' được hiểu là tập modality còn lại (vào ma trận missing-modality, không lặp ở bảng ablation); EVIDENCE LIMITS tách 3 mức (ablation từng modality / ma trận đủ 15 tập / ma trận liên nghiên cứu) và cấm trích dẫn cho câu nói về chính corpus; `study_profile_table` (hồ sơ bằng chứng mỗi nguồn, NR khi thiếu, ≥3 nguồn). `consistency_check._check_dice_scale`: cảnh báo cột Dice trộn tỷ lệ và %. `format_sanitizer`: bỏ dòng tác giả/đơn vị giữ chỗ và caption '**Figure N: …**' thừa trên khối hình; `citation_cleaner` gộp `[n]–[n]`. REVIEW FACTS nêu số paper corpus không được truy xuất.
  - Đợt 3: `quant_analysis.canon_modality`/`_variant_modalities` (đồng nghĩa T1ce/T1Gd/T1 post-contrast…, thiếu 1–3 modality, 'X only'/'available X'); `modality_coverage_matrix` (đủ 15 tập, NR, nhãn bối cảnh A/B…, thay bảng dài). `study_profile.py`: thuộc tính external validation/CV/patient-wise/giao thức thiếu modality/uncertainty/code từ CÂU NGUYÊN VĂN của chính paper (bỏ câu có 'et al.'/[n]), 'Yes/No (p. X)' hoặc NR; câu trích nằm ở `validation_report.study_profile`. `science_qa.py` (WARNING): claim phủ định trái bằng chứng, thuật ngữ lẫn, phạm vi năm vượt References, overclaim Abstract/Conclusion, một nguồn nhiều nhóm cùng trục taxonomy, NR không định nghĩa. `review_protocol.py`: giao thức do người dùng khai báo (`<upload_dir>/review_protocol.json`, mẫu `docs/review-protocol.md`) → REVIEW FACTS + sơ đồ PRISMA tất định; `check_review_claims` theo loại review đã khai báo. REVIEW FACTS liệt kê survey có trong kho; gate cảnh báo `novelty:` khi không cite survey nào.
  - Đợt 4 (Q1/Q2 lần 4): gate chạy LẦN 2 trên BẢN CUỐI (`synthesize_node._verify_final_report`, sau bảng/đánh số lại [n]; `run_quality_gate(..., numbered_citations)` ánh xạ [k] → paper). Ô số UNTRACED trong bảng bị thay bằng `NR` + chú thích caption (`evidence/redact.py`, bỏ qua bảng `derived`); `validation_report.redacted_cells`, `draft_gate` = tóm tắt gate bản thô. Check mới (WARNING): mâu thuẫn nội bộ 'đủ 15 tập', 'exhaustive'/'N bản ghi từ M paper' sai, câu tuyệt đối ở thân bài, dải năm Abstract ≠ References, gán sai nguồn trên bản cuối (`citation_validator` so khớp theo ranh giới từ). `_collect_figures` neo miền theo từ hiếm của câu hỏi (pool ≥6 hình; hình kiến trúc được miễn). Chuỗi LLM dự phòng 429: OpenRouter khóa 1 → Groq → OpenRouter khóa 2.
  - Đợt 4 (đánh giá `survey-b1e8d2cc`, 2026-11-09): `run_research` giới hạn phạm vi truy xuất = paper `done` trong DB (giao với phạm vi người dùng; admin không còn `None`) để vector mồ côi trong Qdrant không thành reference "Anonymous"/UUID. `citation_validator.expand_citation_clusters` tách `[7, 73]`/`[3–5]` thành marker đơn trước khi đánh số lại (`citation_cleaner`), xóa marker treo (`report_structure.strip_dangling_citations`) và đếm số đã cite (quality gate). REVIEW FACTS ghi rõ `[n]` là đoạn trích, không phải paper; `consistency_check.check_paper_counts` chặn "N papers/studies" > số paper trong kho. `synthesize_node._collect_figures(citations, question)` chỉ đưa hình có caption chung ≥2 từ nội dung với câu hỏi.
- model: dựng Research Knowledge Model (gaps, questions, claims, experiments) — `model_node.py`.
- synthesize: viết paper; hậu xử lý `report_postprocess.py`, `format_sanitizer.py`; kiểm chứng `evidence/` (citation_validator, hallucination_detector, claim_validator, stats, claim_scan, report_structure).
  - `stats.py`: Welch t-test + Cohen's d trên số liệu từng lần chạy (`experiments`) của người dùng; không đủ ≥2 lần chạy thì chỉ cảnh báo, khác biệt không có ý nghĩa thì claim thành `unsupported`.
  - `claim_scan.py`: sau khi ghép bài, quét câu khẳng định cho claim `unsupported`/`hypothesis` và nhờ LLM hạ giọng; câu không sửa được ghi vào `research_model.validation.leaked_claims`.
- State: `app/agent/state.py` (`ResearchState`). Inject LLM giả khi test: `build_graph(llm=fake)`.

## Luồng 3: chat với paper
`POST /chat` -> hybrid retrieval -> context_builder (giới hạn `context_token_limit`) -> LLM gateway -> trả lời + citations, lưu `messages`.

## LLM gateway (`app/ai/llm_gateway`)
Adapter: anthropic, openai, gemini, groq, openrouter; `registry.py` chọn theo `agent_provider`/model; `retry.py` backoff + fallback model OpenRouter.
Khi OpenRouter trả 429, `FallbackGateway` (`fallback.py`) gọi lại cùng lời gọi theo chuỗi: Groq (nếu có `GROQ_API_KEY`, model `GROQ_MODEL`) rồi OpenRouter khóa thứ hai (nếu có `OPENROUTER_API_KEY_2`, cùng model chính); lỗi khác không fallback.

## Phụ thuộc giữa module (một chiều)
`core` <- `ai`, `pipeline` <- `agent`, `api`. `agent` không import `api`. `api` gọi agent qua Celery task, không chạy agent trong request.

## Nguồn sự thật khác
`docs/RAG_FLOW.md`, `docs/RAG_UPGRADE_PLAN.md`, `docs/duties.md` (phân công 3 Dev: Dev1 ai, Dev2 pipeline/api/workers, Dev3 agent).

## Workspace (phiên/đề tài) — phạm vi truy xuất
`app/core/scope.allowed_paper_ids_for(db, user, workspace_id)`: `run_research` lấy `task.workspace_id`; `chat` lấy workspace của research task (hoặc của paper) được hỏi. Có workspace → chỉ paper của workspace; không → user thường chỉ thấy paper chưa gán workspace, admin thấy tất cả. Paper = 1 user + ≤1 workspace; `catalog.json`/figures vẫn theo `UPLOAD_DIR` toàn cục (chưa tách theo workspace).
