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
- Hình (Chart Selection Policy + Figure Layout): `evidence/figure_policy.py` đổi biểu đồ cột hai điều kiện ghép cặp (validation/test, có/không, full/thiếu) → `dumbbell`, nhiều phương pháp × metric → `dot` (chỉ đổi cách vẽ, giữ số) và cảnh báo quality gate khi >2 biểu đồ cột, hai hình cùng dữ liệu hoặc hình chỉ lặp một bảng. Hình tất định từ record: heatmap Δ so với full-modality của chính nguồn (14 tập thiếu × phương pháp, ô NR, một setting) và evidence map (tiêu chí × nguồn, Yes/No/NR từ câu nguyên văn) thay bảng hồ sơ khi >12 nguồn; khối `"derived": true` không qua scrub. Ledger fallback: dot + heatmap, không vẽ lại ma trận bằng bar. `pipeline/export/figure_layout.py`: PDF hai cột đặt hình trong MỘT cột (vẽ 3.4 in); chỉ `wide` (CSS `column-span: all`, Typst `scope: "parent"`) khi nhãn không đọc được trong một cột hoặc spec ghi `"layout": "wide"`.
- synthesize: sau khi ghép bài chạy Quality Gate (`evidence/quality_gate.py`: reference, truy vết số, so sánh được, hình/bảng, nhất quán) → `validation_report`; chèn bảng Δ/ablation/scatter suy ra từ record (`evidence/quant_analysis.py`, khối `derived:true`). Export PDF/LaTeX trả 409 khi `passed=false` (trừ `?draft=true`).
  - RQ một nguồn: blueprint (mục 7) sinh RQ chuẩn → `evidence/rq_sync.py` tiêm vào chặng 1/2/5 và ép nguyên văn vào mọi mục "Research Questions" sau khi ghép; RQ lệch giữa các mục = lỗi chặn (`validation_report.research_questions`).
  - Sau `finalize_structure_report` (đánh số lại Table/Figure, tham chiếu mơ hồ gán theo ngữ cảnh): tham chiếu treo = lỗi chặn, gán theo vị trí = cảnh báo; gộp vào report bằng `quality_gate.merge_structure_issues`.
  - `consistency_check.check_review_claims`: tự nhận systematic review/PRISMA mà không phủ định = lỗi chặn. `display_check.check_figure_captions`: caption chung chung/trùng, ảnh thiếu nguồn [n]/giấy phép = cảnh báo. `reference_check.classify_publication`: thống kê preprint/đã xuất bản, cảnh báo thiếu metadata.
  - `quant_analysis`: ma trận missing-modality (`ResultRecord.modality`), Δ so với full CHỈ khi cùng nguồn báo full, biểu đồ theo tập modality; `efficiency_table` (Params/GFLOPs/InferenceTime theo phương pháp, ô thiếu = NR, caption nói rõ không so sánh trực tiếp giữa nguồn); `ResultRecord.spread`/`spread_type` (SD|SE|CI95) chỉ giữ khi số `± x` in nguyên văn trong chunk, hiện ở cột Spread của bảng Δ (bỏ cột khi không nguồn nào báo) và ở Notes của ledger; `evidence_limits` đưa giới hạn thật (số bản ghi có spread, ma trận thiếu) vào prompt Limitations. Thiếu số liệu thì ghi hạn chế, không chặn export.
  - Đợt đánh giá Q1/Q2 lần 2: biến thể ablation 'Missing X'/'w/o X' được hiểu là tập modality còn lại (vào ma trận missing-modality, không lặp ở bảng ablation); EVIDENCE LIMITS tách 3 mức (ablation từng modality / ma trận đủ 15 tập / ma trận liên nghiên cứu) và cấm trích dẫn cho câu nói về chính corpus; `study_profile_table` (hồ sơ bằng chứng mỗi nguồn, NR khi thiếu, ≥3 nguồn). `consistency_check._check_dice_scale`: cảnh báo cột Dice trộn tỷ lệ và %. `format_sanitizer`: bỏ dòng tác giả/đơn vị giữ chỗ và caption '**Figure N: …**' thừa trên khối hình; `citation_cleaner` gộp `[n]–[n]`. REVIEW FACTS nêu số paper corpus không được truy xuất.
  - Đợt 3: `quant_analysis.canon_modality`/`_variant_modalities` (đồng nghĩa T1ce/T1Gd/T1 post-contrast…, thiếu 1–3 modality, 'X only'/'available X'); `modality_coverage_matrix` (đủ 15 tập, NR, nhãn bối cảnh A/B…, thay bảng dài). `study_profile.py`: thuộc tính external validation/CV/patient-wise/giao thức thiếu modality/uncertainty/code từ CÂU NGUYÊN VĂN của chính paper (bỏ câu có 'et al.'/[n]), 'Yes/No (p. X)' hoặc NR; câu trích nằm ở `validation_report.study_profile`. `science_qa.py` (WARNING): claim phủ định trái bằng chứng, thuật ngữ lẫn, phạm vi năm vượt References, overclaim Abstract/Conclusion, một nguồn nhiều nhóm cùng trục taxonomy, NR không định nghĩa. `review_protocol.py`: giao thức do người dùng khai báo (`<upload_dir>/review_protocol.json`, mẫu `docs/review-protocol.md`) → REVIEW FACTS + sơ đồ PRISMA tất định; `check_review_claims` theo loại review đã khai báo. REVIEW FACTS liệt kê survey có trong kho; gate cảnh báo `novelty:` khi không cite survey nào.
- model: dựng Research Knowledge Model (gaps, questions, claims, experiments) — `model_node.py`.
- synthesize: viết paper; hậu xử lý `report_postprocess.py`, `format_sanitizer.py`; kiểm chứng `evidence/` (citation_validator, hallucination_detector, claim_validator, stats, claim_scan, report_structure).
  - `stats.py`: Welch t-test + Cohen's d trên số liệu từng lần chạy (`experiments`) của người dùng; không đủ ≥2 lần chạy thì chỉ cảnh báo, khác biệt không có ý nghĩa thì claim thành `unsupported`.
  - `claim_scan.py`: sau khi ghép bài, quét câu khẳng định cho claim `unsupported`/`hypothesis` và nhờ LLM hạ giọng; câu không sửa được ghi vào `research_model.validation.leaked_claims`.
- State: `app/agent/state.py` (`ResearchState`). Inject LLM giả khi test: `build_graph(llm=fake)`.

## Luồng 3: chat với paper
`POST /chat` -> hybrid retrieval -> context_builder (giới hạn `context_token_limit`) -> LLM gateway -> trả lời + citations, lưu `messages`.

## LLM gateway (`app/ai/llm_gateway`)
Adapter: anthropic, openai, gemini, groq, openrouter; `registry.py` chọn theo `agent_provider`/model; `retry.py` backoff + fallback model OpenRouter.

## Phụ thuộc giữa module (một chiều)
`core` <- `ai`, `pipeline` <- `agent`, `api`. `agent` không import `api`. `api` gọi agent qua Celery task, không chạy agent trong request.

## Nguồn sự thật khác
`docs/RAG_FLOW.md`, `docs/RAG_UPGRADE_PLAN.md`, `docs/duties.md` (phân công 3 Dev: Dev1 ai, Dev2 pipeline/api/workers, Dev3 agent).
