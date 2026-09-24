"""LangGraph StateGraph định nghĩa flow research: plan -> search -> analyze -> critique -> (loop | synthesize)."""

from langgraph.graph import END, StateGraph

from app.agent.nodes.analyze_node import analyze_node
from app.agent.nodes.critique_node import critique_node
from app.agent.nodes.plan_node import plan_node
from app.agent.nodes.search_node import search_node
from app.agent.nodes.synthesize_node import synthesize_node
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway

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


def run_graph(question: str, llm: LLMGateway | None = None) -> ResearchState:
    app = build_graph(llm=llm)
    initial_state: ResearchState = {"question": question, "iterations": 0}
    return app.invoke(initial_state)
