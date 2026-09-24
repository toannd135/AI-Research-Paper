"""Node tìm kiếm evidence trên toàn kho paper, dựa trên search_queries từ plan_node."""

from app.agent.state import ResearchState
from app.agent.tools.retrieve_evidence import retrieve_evidence


def search_node(state: ResearchState) -> ResearchState:
    queries = state.get("search_queries") or [state["question"]]
    evidence = retrieve_evidence(queries)
    return {**state, "evidence": evidence}
