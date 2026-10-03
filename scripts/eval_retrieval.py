"""Đo recall@k / MRR của pipeline retrieval (hybrid search + rerank) trên 1 tập câu hỏi đã gán nhãn.

Đây là eval harness tối thiểu cho RAG_UPGRADE_PLAN.md — mọi thay đổi retrieval sau này (đổi
reranker, semantic chunking, bật quantization...) nên chạy qua script này trước/sau để có số đo
thay vì đoán theo cảm tính.

Cách dùng:
    python scripts/eval_retrieval.py eval/retrieval_queries.sample.jsonl

Format file JSONL, mỗi dòng 1 câu hỏi đã biết trước chunk nào là relevant:
    {"question": "...", "paper_id": "uuid-hoac-null", "relevant_chunk_ids": ["id1", "id2"]}

Xem eval/README.md để biết cách tạo bộ câu hỏi thật từ corpus của bạn — repo không có sẵn nhãn
thật vì việc đó cần domain judgement trên papers thật, không thể tạo giả.
"""

import json
import sys
from pathlib import Path

from app.ai.retrieval.hybrid import search_hybrid
from app.ai.retrieval.reranker import rerank

HYBRID_TOP_K = 20  # match app/api/routes/chat.py:26
RERANK_TOP_K = 6  # match app/api/routes/chat.py:27


def _load_queries(path: Path) -> list[dict]:
    queries = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                queries.append(json.loads(line))
    return queries


def _recall_at_k(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    if not relevant_ids:
        return 0.0
    hit = len(set(retrieved_ids) & relevant_ids)
    return hit / len(relevant_ids)


def _reciprocal_rank(retrieved_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, chunk_id in enumerate(retrieved_ids, start=1):
        if chunk_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def evaluate(queries: list[dict]) -> None:
    hybrid_recalls: list[float] = []
    rerank_recalls: list[float] = []
    mrrs: list[float] = []

    for q in queries:
        question = q["question"]
        paper_id = q.get("paper_id")
        relevant_ids = set(q["relevant_chunk_ids"])

        hybrid_results = search_hybrid(question, top_k=HYBRID_TOP_K, paper_id=paper_id)
        hybrid_ids = [r.chunk.id for r in hybrid_results]
        hybrid_recalls.append(_recall_at_k(hybrid_ids, relevant_ids))

        reranked = rerank(question, hybrid_results, top_k=RERANK_TOP_K)
        rerank_ids = [r.chunk.id for r in reranked]
        rerank_recalls.append(_recall_at_k(rerank_ids, relevant_ids))
        mrrs.append(_reciprocal_rank(rerank_ids, relevant_ids))

        print(
            f"- {question!r}: recall@{HYBRID_TOP_K}(hybrid)={hybrid_recalls[-1]:.2f} "
            f"recall@{RERANK_TOP_K}(reranked)={rerank_recalls[-1]:.2f} RR={mrrs[-1]:.2f}"
        )

    n = len(queries)
    print("\n=== Aggregate ===")
    print(f"queries: {n}")
    print(f"mean recall@{HYBRID_TOP_K} (hybrid stage): {sum(hybrid_recalls) / n:.3f}")
    print(f"mean recall@{RERANK_TOP_K} (after rerank):  {sum(rerank_recalls) / n:.3f}")
    print(f"MRR (after rerank):                          {sum(mrrs) / n:.3f}")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Không tìm thấy file: {path}\n")
        print(__doc__)
        sys.exit(1)

    queries = _load_queries(path)
    if not queries:
        print(f"{path} không có câu hỏi nào.")
        sys.exit(1)

    evaluate(queries)


if __name__ == "__main__":
    main()
