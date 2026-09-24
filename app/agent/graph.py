"""LangGraph StateGraph định nghĩa flow research deterministically."""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agent.generators.base import AnswerGenerator
from app.agent.generators.mock import MockAnswerGenerator
from app.agent.nodes import (
    create_synthesize_node,
    fallback_node,
    retrieve_node,
    search_node,
)
from app.core.schemas import ResearchState


def should_synthesize(state: ResearchState) -> Literal["synthesize", "fallback"]:
    """Conditional edge: kiểm tra xem có thu thập được bằng chứng không."""
    evidence = state.get("evidence", [])
    if evidence and len(evidence) > 0:
        return "synthesize"
    return "fallback"


def build_research_graph(generator: AnswerGenerator | None = None):
    """Xây dựng và biên dịch đồ thị LangGraph v0 cho PaperAI Research Agent.

    Args:
        generator: Tùy chọn truyền AnswerGenerator. Mặc định là MockAnswerGenerator.

    Returns:
        CompiledStateGraph có thể invoke.
    """
    if generator is None:
        generator = MockAnswerGenerator()

    workflow = StateGraph(ResearchState)

    # Thêm các nodes
    workflow.add_node("search", search_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("synthesize", create_synthesize_node(generator))
    workflow.add_node("fallback", fallback_node)

    # Thiết lập các cạnh chuyển tiếp (Edges)
    workflow.add_edge(START, "search")
    workflow.add_edge("search", "retrieve")

    # Conditional edge sau khi retrieve
    workflow.add_conditional_edges(
        "retrieve",
        should_synthesize,
        {
            "synthesize": "synthesize",
            "fallback": "fallback",
        },
    )

    workflow.add_edge("synthesize", END)
    workflow.add_edge("fallback", END)

    return workflow.compile()


def run_research_agent(
    question: str,
    generator: AnswerGenerator | None = None,
) -> dict:
    """Entrypoint chạy Research Agent với câu hỏi nghiên cứu.

    Args:
        question: Câu hỏi từ người dùng.
        generator: Tùy chọn Generator. Nếu None sẽ dùng MockAnswerGenerator.

    Returns:
        Dictionary kết quả chứa question, papers, evidence, answer, citations, steps.
    """
    graph = build_research_graph(generator=generator)
    initial_state: ResearchState = {
        "question": question,
        "papers": [],
        "evidence": [],
        "answer": "",
        "citations": [],
        "steps": [],
    }
    return graph.invoke(initial_state)
