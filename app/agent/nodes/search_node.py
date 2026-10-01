"""Node tìm kiếm evidence trên toàn kho paper (nội bộ Qdrant + mở rộng OpenAlex trên Internet)."""

from app.agent.state import ResearchState
from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.agent.tools.search_external_papers import retrieve_external_evidence


def search_node(state: ResearchState) -> ResearchState:
    queries = state.get("search_queries") or [state["question"]]

    # 1. Tìm kiếm evidence trên CSDL nội bộ (Qdrant)
    internal_evidence = retrieve_evidence(queries)

    # 2. Truy xuất tài liệu học thuật liên quan từ Internet (OpenAlex)
    external_evidence = retrieve_external_evidence(queries, count_per_query=5, max_total=10)

    # 3. Hợp nhất bằng chứng: loại bỏ trùng lặp, không bị phụ thuộc duy nhất vào CSDL nội bộ
    seen_ids = set()
    combined = []

    for sc in internal_evidence:
        if sc.chunk.id not in seen_ids:
            seen_ids.add(sc.chunk.id)
            combined.append(sc)

    for sc in external_evidence:
        if sc.chunk.id not in seen_ids:
            seen_ids.add(sc.chunk.id)
            combined.append(sc)

    combined.sort(key=lambda s: s.score, reverse=True)
    return {**state, "evidence": combined}
