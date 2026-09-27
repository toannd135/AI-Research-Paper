# Retrieval Evaluation Set

`scripts/eval_retrieval.py` measures recall@k and MRR of the hybrid search + rerank pipeline
against a labeled query set. This is the eval harness `RAG_UPGRADE_PLAN.md` calls out as a P0
prerequisite — every later retrieval change (reranker swap, semantic chunking, quantization)
should be measured against it instead of trusted on intuition.

## Format

One JSON object per line in a `.jsonl` file:

```
{"question": "<a real question about one of your ingested papers>", "paper_id": "<paper UUID, or null to search across the whole corpus>", "relevant_chunk_ids": ["<chunk id>", "..."]}
```

## Building a real eval set

1. Ingest a handful of papers you know well.
2. For each, write 3-5 questions you know the answer to.
3. Find the `chunk.id` of the chunk(s) that actually contain the answer (query Qdrant directly,
   or read the citations returned by `/chat` once) and record those as `relevant_chunk_ids`.
4. Aim for at least 20-30 labeled questions before trusting the aggregate numbers — a handful of
   queries is noisy.

`retrieval_queries.sample.jsonl` is a template with placeholder values, **not real eval data** —
replace it with your own before drawing conclusions:

```
python scripts/eval_retrieval.py eval/retrieval_queries.sample.jsonl
```
