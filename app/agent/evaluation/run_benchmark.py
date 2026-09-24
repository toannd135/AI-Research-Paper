"""Chạy benchmark trên bộ questions.json.

Format kỳ vọng của mỗi entry trong questions.json:
{
  "question": "...",
  "relevant_chunk_ids": ["...", "..."]   # optional, dùng để tính recall@K
}

questions.json hiện để trống ([]) vì chưa có paper thật đã ingest để làm gold data —
điền entry vào đây sau khi đã upload paper thật và biết trước chunk nào liên quan.
"""

import json
from pathlib import Path

from app.agent.evaluation.metrics import citation_faithfulness, recall_at_k
from app.agent.graph import run_graph

QUESTIONS_PATH = Path(__file__).parent / "questions.json"


def run_benchmark() -> list[dict]:
    questions = json.loads(QUESTIONS_PATH.read_text())
    if not questions:
        print("Không có câu hỏi để eval (questions.json rỗng).")
        return []

    results = []
    for entry in questions:
        state = run_graph(entry["question"])
        retrieved_ids = [s.chunk.id for s in state.get("evidence", [])]
        relevant_ids = entry.get("relevant_chunk_ids", [])

        result = {
            "question": entry["question"],
            "recall_at_k": recall_at_k(retrieved_ids, relevant_ids) if relevant_ids else None,
            "citation_faithfulness": citation_faithfulness(
                state.get("report", ""), state.get("citations", [])
            ),
        }
        results.append(result)
        print(result)

    return results


if __name__ == "__main__":
    run_benchmark()
