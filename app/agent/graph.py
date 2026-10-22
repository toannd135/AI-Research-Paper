"""LangGraph StateGraph định nghĩa flow research: plan -> search -> analyze -> critique -> (loop | synthesize)."""

from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agent.nodes.analyze_node import analyze_node
from app.agent.nodes.critique_node import critique_node
from app.agent.nodes.fallback import FALLBACK_MESSAGE
from app.agent.nodes.plan_node import plan_node
from app.agent.nodes.search_node import search_node
from app.agent.nodes.synthesize_node import synthesize_node
from app.agent.profiles import normalize_audience, normalize_field
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway
from app.core.schemas import PaperRef

MAX_ITERATIONS = 2


def _route_after_critique(state: ResearchState) -> str:
    if state.get("critique_feedback") and state.get("iterations", 0) < MAX_ITERATIONS:
        return "analyze"
    return "synthesize"


def build_graph(llm: LLMGateway | None = None):
    """Build + compile graph. `llm` cho phép inject fake gateway khi test."""
    graph = StateGraph(ResearchState)
    graph.add_node("plan", lambda state: plan_node(state, llm=llm))
    graph.add_node("search", search_node)
    graph.add_node("analyze", lambda state: analyze_node(state, llm=llm))
    graph.add_node("critique", lambda state: critique_node(state, llm=llm))
    graph.add_node("synthesize", lambda state: synthesize_node(state, llm=llm))

    graph.set_entry_point("plan")
    graph.add_edge("plan", "search")
    graph.add_edge("search", "analyze")
    graph.add_edge("analyze", "critique")
    graph.add_conditional_edges(
        "critique", _route_after_critique, {"analyze": "analyze", "synthesize": "synthesize"}
    )
    graph.add_edge("synthesize", END)

    return graph.compile()


# Bài báo chuẩn quốc tế: luôn viết bằng tiếng Anh, bất kể câu hỏi của người dùng dùng ngôn ngữ nào.
MANUSCRIPT_LANGUAGE = "en"


def run_graph(
    question: str,
    llm: LLMGateway | None = None,
    language: str | None = None,
    audience: str | None = None,
    field: str | None = None,
) -> ResearchState:
    """Entrypoint chạy Research Agent graph theo workflow đầy đủ."""
    app = build_graph(llm=llm)
    initial_state: ResearchState = {
        "question": question,
        "iterations": 0,
        "language": language or MANUSCRIPT_LANGUAGE,
        "audience": normalize_audience(audience),
    }
    if normalize_field(field):
        initial_state["field"] = normalize_field(field)
    return app.invoke(initial_state)


def build_research_graph(llm: LLMGateway | None = None):
    """Alias cũ của build_graph (giữ cho evaluation + test)."""
    return build_graph(llm=llm)


def run_research_agent(question: str, llm: LLMGateway | None = None) -> dict:
    """Chạy graph và bổ sung các trường tổng hợp (answer/papers/steps) mà evaluator sử dụng."""
    state = run_graph(question=question, llm=llm)
    if not state.get("evidence"):
        state["answer"] = FALLBACK_MESSAGE
        state["citations"] = []
        state["papers"] = []
        state["steps"] = ["search", "retrieve", "fallback"]
    else:
        if "report" in state and "answer" not in state:
            state["answer"] = state["report"]
        seen_pids = set()
        papers = []
        for sc in state.get("evidence", []):
            pid = sc.chunk.paper_id
            if pid not in seen_pids:
                seen_pids.add(pid)
                papers.append(PaperRef(paper_id=pid, title=pid))
        state["papers"] = papers
        state["steps"] = ["search", "retrieve", "synthesize"]
    return state
