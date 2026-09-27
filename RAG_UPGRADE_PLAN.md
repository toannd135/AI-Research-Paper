# PaperAI RAG Upgrade Plan — Scaling to 10k+ Papers

Audit only — no application code was changed to produce this document. Every finding below cites the file:line verified in this repo on 2026-09-27.

## 1. Audit Findings

### Ingestion
- `app/pipeline/parser/pdf_parser.py:14` `parse_pdf()` — pymupdf, page-by-page, synchronous, single paper per call. No OCR fallback for scanned/image-only PDFs — any such paper silently yields empty/garbled text.
- `app/pipeline/chunking/semantic_chunker.py:16` `chunk_pages()` — packs consecutive paragraphs until `DEFAULT_CHUNK_SIZE=800` chars (line 10), `DEFAULT_OVERLAP=150` (line 11). This is **length-based chunking**, not semantic chunking: the break point is "buffer + next paragraph > 800 chars," never a meaning boundary. `section_detector.py` heading positions are used only to **label** a chunk's section (`assign_section`, section_detector.py:60) after the fact — a chunk can still span across a section boundary (e.g. end of "Related Work" + start of "Method" in one chunk), mislabeling retrieval metadata and mixing unrelated content in one embedding.
- `app/ai/embedding/service.py:12` `_load_model()` — `SentenceTransformer(BAAI/bge-m3, device="cpu")`, comment explicitly says CPU-only to avoid VRAM contention. `embed_batch()` (line 18) is the ingestion throughput ceiling: CPU dense-embedding a 10k-paper backlog will be slow with no batching/concurrency knobs visible here.
- `app/ai/embedding/cache.py:5` — cache is a **plain process-local Python dict**, keyed by `sha256(model+text)` (line 9), no eviction, no persistence, no cross-process sharing. Celery's default prefork pool runs multiple OS worker processes — each gets its own copy of this dict and its own copy of the loaded model (`_load_model` is `@lru_cache` per-process, service.py:11), so cache hits don't share across workers and memory scales with `worker_count × unique_chunks_seen`.
- `app/pipeline/vector_store/qdrant_client.py:19` `ensure_collection()` — creates the collection with only `distance=COSINE` (line 25): no `on_disk`, no quantization, no HNSW `m`/`ef_construct` tuning, and no payload index on `paper_id` (`create_payload_index` is never called anywhere in this file). Every `paper_id`-filtered query (search.py:74, bm25_search.py:24) filters unindexed payload — fine at hundreds of papers, degrades as the collection grows.

### Retrieval
- `app/ai/retrieval/bm25_search.py:19` `_load_corpus()` — **scrolls every chunk matching the filter out of Qdrant and rebuilds a fresh `BM25Okapi` index in memory on every single call** (line 63). `paper_id` is optional; `search_hybrid()` (hybrid.py:20-24) passes it through unchanged, so if a query isn't scoped to one paper, this scrolls and re-tokenizes the **entire collection** per chat request. This is the single biggest blocker to 10k-paper scale — it's O(total corpus size) per query, not O(top_k).
- `app/ai/retrieval/hybrid.py:20` `search_hybrid()` — fixed `hybrid_alpha`/`hybrid_beta` weights from config (config.py:29-30), min-max normalized per-query (hybrid.py:9-17). No fallback if one side returns zero results skews normalization but isn't incorrect, just brittle.
- `app/ai/retrieval/reranker.py:12` `_load_model()` — `CrossEncoder(BAAI/bge-reranker-v2-m3, device="cpu")`. Note: `FlagEmbedding` is already a declared dependency (`requirements.txt:23`) but reranker.py uses `sentence-transformers`' `CrossEncoder` instead of `FlagEmbedding`'s own `FlagReranker`, which supports `use_fp16=True` for faster CPU/GPU inference of the **same model weights** — this dependency currently appears unused for its most relevant purpose.
- `app/ai/context_builder.py:8` `_approx_tokens()` — token count is `len(text)//4`, a heuristic, not a real tokenizer. `context_token_limit=8000` (config.py:31) is enforced against this estimate, not against what Gemini actually counts as tokens — risk of silently over- or under-filling context.

### Verification
- `tests/test_e2e.py` contains only a module docstring, no test functions. There is currently **zero automated coverage** of ingestion or retrieval, and no retrieval-quality evaluation (no recall@k/MRR/NDCG harness) anywhere in the repo.

## 2. Scale Estimate for 10,000 Papers

Stated assumptions (verify against your actual corpus before trusting the numbers):
- Average paper length: 12 pages (typical for a research paper/preprint).
- Chunk yield: ~4 chunks/page at `chunk_size=800` (a typical page has ~3,000-4,000 chars of body text after `pdf_parser.parse_pdf`).

| Metric | Estimate | Basis |
|---|---|---|
| Total chunks/vectors | ~480,000 (range 350k–1M if pages/chunks-per-page vary) | 10,000 × 12 × 4 |
| Embedding dimension | 1024 (BAAI/bge-m3 dense output — documented by the model, not verified by running it in this repo) [uncertain — confirm with `model.get_sentence_embedding_dimension()`] | — |
| Qdrant raw vector bytes | ~2 GB (480k × 1024 × 4 bytes, float32) | before HNSW graph + payload overhead, which typically adds 30-50% more |
| Qdrant total in-RAM footprint (default config) | roughly 3-5 GB, growing linearly with corpus | no quantization/on_disk configured today (qdrant_client.py:19-26) |
| Embedding cache (process-local dict) | tens of GB **per worker process** at full corpus (Python list-of-floats has heavy per-object overhead, roughly 25-30x the raw 4KB/vector) | cache.py:5, multiplied by Celery prefork worker count |
| BM25 rebuild cost per unscoped query | scroll + tokenize ~480k chunk texts, O(N) `BM25Okapi` build, **on every chat request** | bm25_search.py:19-63 |

The BM25 rebuild and the unbounded per-process embedding cache are the two findings that most directly say "this will not hold at 10k papers" — everything else degrades gracefully, these two degrade catastrophically (unbounded memory growth, and per-query cost proportional to total corpus size).

## 3. Reranker Comparison

| Candidate | Type | Quality (qualitative) | Latency | Cost/Infra | Multilingual |
|---|---|---|---|---|---|
| **BAAI/bge-reranker-v2-m3 (current)** | Cross-encoder, self-hosted | Strong, well-regarded for multilingual retrieval | Moderate on CPU for top-20 rerank | Free, already integrated | Yes |
| **Same model via FlagEmbedding `FlagReranker(use_fp16=True)`** | Same weights, faster runtime | Same quality as current | Lower latency than sentence-transformers CrossEncoder path on CPU/GPU | Free, dependency already present (`requirements.txt:23`), currently unused | Yes |
| **BAAI/bge-reranker-v2-gemma or bge-reranker-large** | Larger cross-encoder, same family | Likely higher quality, unverified for this corpus | Higher latency than v2-m3 | Free, self-hosted, same loading pattern | Yes |
| **Cohere Rerank (hosted API)** | Cross-encoder as a service | Strong, general-purpose | Network round-trip per query | Per-query cost + requires API key not currently in `config.py` + paper text leaves your infra | Yes, but verify on your domain |
| **ColBERTv2 / late-interaction** | Token-level max-sim, different architecture | Competitive quality; scales better because document-side representations are precomputable offline | Query-time cost shifts away from a full cross-encoder pass | Self-hosted but needs a new token-vector index — largest engineering lift here | Model-dependent |
| **cross-encoder/ms-marco-MiniLM-L-6-v2** | Small cross-encoder | Lower quality, English-only | Fastest | Free, trivial to swap in | No — a poor fit if the corpus includes non-English papers [uncertain — confirm corpus language mix] |

**Recommendation:** keep the current `bge-reranker-v2-m3` model (already integrated, multilingual, proven), but switch its execution path to `FlagEmbedding`'s `FlagReranker` with `use_fp16=True` — same weights, no new dependency, no quality change to validate, just a latency win. Treat any actual model swap (larger BGE variant, Cohere, ColBERT) as a **P2, evaluation-gated** decision — do not swap the reranker model based on a leaderboard; build the eval harness (Finding above) first and measure on your own queries.

## 4. Semantic Chunking Proposal

Current gap: `chunk_pages()` breaks purely on character count, and section headings are only used to *label* a chunk after the fact, not to *bound* it.

Proposed method (reuses infrastructure already in place, no new dependency):
1. **Hard-break at detected section boundaries.** `detect_sections()` (section_detector.py:48) already finds heading positions — force a chunk boundary there instead of only using it for labeling in `assign_section`. This alone fixes the cross-section chunk-mixing finding above.
2. **Embedding-similarity breakpoints within a section.** Split each section into paragraphs (already done, semantic_chunker.py:28), embed each paragraph with the existing `embed_batch()` (service.py:18), and walk consecutive paragraphs computing cosine similarity between their embeddings. Start a new chunk when similarity drops below a threshold (tune empirically, e.g. starting around 0.5-0.6) instead of only when the character budget is exceeded. Keep `chunk_size` as an upper bound safety cap (very long low-similarity-break sections should still hard-split) and keep the existing overlap behavior.
3. **Keep the same `Chunk` schema and `chunk_index`/`page`/`section` fields** — this is a drop-in replacement for `chunk_pages()`, not a new pipeline.

**Migration for already-ingested papers:** `qdrant_client.py:51` `delete_paper(paper_id)` already exists. Backfill = for each existing paper: `delete_paper` → `parse_pdf` → new `chunk_pages` → `embed_batch` → `upsert_chunks`, run as a batch script, throttled given CPU embedding cost, and only after the eval harness confirms the new chunker improves retrieval quality on a held-out query set. Do not backfill all 10k papers before that validation step.

## 5. Additional Techniques

| Technique | Problem it solves | Effort | Risk |
|---|---|---|---|
| Move embedding cache to Redis | Process-local dict (cache.py:5) isn't shared across Celery workers or persisted; Redis is already a running service in this stack (docker-compose.yml:21, already used for Celery broker) | Low | Low — same interface, swap backing store |
| Qdrant payload index on `paper_id` (`create_payload_index`) | Filtered queries (search.py:74, bm25_search.py:24) degrade as collection grows without one | Low | Low |
| Qdrant scalar or binary quantization + `on_disk` vectors | RAM footprint grows linearly with corpus (Section 2); quantization cuts RAM 4x (scalar) to ~32x (binary) with a recall trade-off to measure | Medium | Medium — must validate recall impact with the eval harness before enabling in production |
| Replace `bm25_search.py`'s scroll-and-rebuild with Qdrant's native sparse-vector support | Removes the catastrophic per-query full-corpus rebuild entirely by moving keyword search into the same vector engine | Medium-High | Medium — is a structural retrieval change, needs the eval harness to confirm parity with current BM25 |
| Real tokenizer in `context_builder.py:8` instead of `len(text)//4` | Token budget (`context_token_limit`) is currently enforced against a heuristic, not what Gemini actually counts | Low | Low |
| Celery worker concurrency tuning for bulk ingestion | `docker-compose.yml:42` doesn't set `--concurrency`; default pool sizing is untested against a 10k-paper backfill | Low | Low — config-only change, verify against CPU core count |
| Retrieval evaluation harness (recall@k / MRR against a small labeled query set) | `tests/test_e2e.py` is currently empty — every recommendation above (reranker choice, chunking, quantization) needs a way to be validated instead of trusted on intuition | Medium | None — pure upside, should be P0 |
| GPU inference for embedding/reranker | CPU is the explicit, documented choice today (service.py:13, reranker.py:13) to avoid VRAM contention — only revisit if the deployment target has dedicated GPU headroom | Environment-dependent | Medium — re-introduces the VRAM contention concern the current code deliberately avoided |

## 6. Phased Roadmap

**P0 — must-do before real 10k-paper load (unblocks correctness/perf, low-to-medium effort):**
- [x] Fix `bm25_search.py`'s unscoped full-corpus rebuild — added `app/ai/retrieval/bm25_index_cache.py`, an in-process cache per scope (paper_id / whole corpus), invalidated from `qdrant_client.upsert_chunks`/`delete_paper`, TTL 300s as a safety net. Not the final architecture (still in-process, not shared across workers) — the real structural fix is still the P2 native sparse-vector item below; this buys time and removes the "rebuild on every single request" cost in the meantime.
- [x] Move embedding cache to Redis — `app/ai/embedding/cache.py` now backed by `settings.redis_url` (reuses the already-running Redis service), same `get/set/clear` interface.
- [x] Add Qdrant payload index on `paper_id` — `qdrant_client.ensure_collection()` now calls `create_payload_index` idempotently.
- [x] Build a minimal retrieval evaluation harness — `scripts/eval_retrieval.py` computes recall@k (hybrid stage and post-rerank) and MRR from a labeled JSONL query set; see `eval/README.md`. **No real labeled queries exist yet** — `eval/retrieval_queries.sample.jsonl` is a placeholder template. This must be populated with real questions from your corpus before P1/P2 decisions can be trusted.

Verification: 9 new unit tests added (`tests/test_bm25_index_cache.py`, `tests/test_embedding_cache.py`) plus the existing 60-test suite, all passing. Unit tests cover cache logic only (no live Redis/Qdrant in this environment) — `scripts/eval_retrieval.py` itself needs a running stack + real labeled data to produce meaningful numbers.

**P1 — quality improvements (medium effort):**
- Semantic chunking (section-boundary hard-breaks + embedding-similarity breakpoints) + validated backfill
- Real tokenizer in `context_builder.py`
- Switch reranker execution to `FlagEmbedding`'s `FlagReranker(use_fp16=True)` (same model, faster)

**P2 — scale/cost optimization (higher effort or environment-dependent, evaluation-gated):**
- Qdrant quantization + on-disk storage
- Native sparse-vector hybrid search to retire the custom BM25 path
- GPU inference, if the deployment target supports it
- Reranker model swap (larger BGE / Cohere / ColBERT) — only if the eval harness shows the current model underperforming on your own queries

**Scope decision (2026-09-27): staying at 10k papers**, not pursuing a 100k-paper phase for now. Effort instead redirected to the query flow and the deep-research reasoning agent below.

## 7. Query Flow & Reasoning Optimizations (done)

The agent stack is more complete than `RAG_FLOW.md` describes: `app/agent/graph.py` runs a LangGraph pipeline (`clarify` → `plan` → `search` → `analyze` → `critique` → loop up to `MAX_ITERATIONS=2` → `synthesize`), with regex-based citation validation (`app/agent/evidence/citation_validator.py`) and an LLM-judge hallucination check (`app/agent/evidence/hallucination_detector.py`). A single research request can therefore make **5-7 sequential Gemini calls**. `app/agent/evaluation/` already has its own recall@k/faithfulness harness, with `questions.json` empty — same "needs your real labeled data" gap as `eval/`.

Findings and fixes, grounded in the code read for this pass:

- **`app/agent/tools/retrieve_evidence.py`** — `plan_node` generates 3-5 sub-queries, and the old code called `search_papers()` (hybrid search + rerank, each a corpus-wide search per `search_papers.py:1`) **sequentially** for every sub-query — a direct latency multiplier. Now runs them in a `ThreadPoolExecutor` (`max_workers=min(len(queries), 5)`); dedup/sort logic unchanged. Covered by existing `test_retrieve_evidence_dedups_across_queries_keeping_highest_score` (still passes — the test's mock ordering assumption doesn't depend on which thread calls first, since it only checks the merged result set).
- **`app/ai/llm_gateway/gemini_adapter.py`** — a single transient Gemini error anywhere in a 5-7-call chain previously failed the entire `run_research` task (Celery has no retry configured in `tasks.py`), wasting all prior plan/search/analyze work. `GeminiAdapter.generate()` now retries up to 2 times with exponential backoff (1s, 2s) on `APIError`, other exceptions, and empty responses, via a new internal `_call_once()` (kept the original immediate-raise shape so the retry loop only catches the specific `LLMGatewayError`, not a blind `Exception`). New tests: `test_retries_transient_error_then_succeeds`, `test_gives_up_after_max_retries`.
- **`app/agent/nodes/critique_node.py`** — previously called the hallucination-detector LLM check unconditionally, even when citation validation (cheap, local regex) already found invalid citations and the draft is going to be rewritten regardless. Now skips that LLM call in the invalid-citation branch, saving one Gemini round-trip on the common "citation format mistake" loop-back path. New test: `test_critique_node.py` (both the skip case and the normal case).
- **Considered, not implemented:** a singleton `genai.Client` (to avoid re-constructing a client per node call) — dropped because the existing Gemini adapter tests reuse the literal api-key `"fake-key"` with a fresh per-test mock, so a module-level cache would leak a stale mocked client across tests; the actual construction cost of `genai.Client()` is not believed to be a meaningful latency source compared to the network call itself, so this wasn't worth the added complexity/risk.
- **Considered, not implemented:** converting `chat.py`'s `def chat(...)` to `async def` with an async Gemini client, and per-step model tiering (cheaper model for `plan`/`critique`, higher-tier for `synthesize`). Both are real options but: the sync FastAPI route already runs off the event loop in a threadpool (fine at current expected concurrency, revisit only if request volume becomes the bottleneck), and model tiering needs the (still-empty) eval harness to prove it doesn't hurt report quality before swapping models per-step — consistent with the eval-gating principle used throughout this plan.

Verification: full test suite (64 tests, up from 60) passes, including the modified `test_graph.py` scenarios (unaffected — no existing test exercises the invalid-citation branch), `ruff check` clean on all touched files (aside from the pre-existing `EXE002` file-permission artifact present repo-wide, unrelated to this change).
