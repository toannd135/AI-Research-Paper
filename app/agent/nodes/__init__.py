"""Các node trong đồ thị LangGraph của PaperAI Agent: plan -> search -> analyze -> critique -> synthesize."""

from app.agent.nodes.analyze_node import analyze_node
from app.agent.nodes.critique_node import critique_node
from app.agent.nodes.fallback import FALLBACK_MESSAGE
from app.agent.nodes.plan_node import plan_node
from app.agent.nodes.search_node import search_node
from app.agent.nodes.synthesize_node import synthesize_node

__all__ = [
    "FALLBACK_MESSAGE",
    "analyze_node",
    "critique_node",
    "plan_node",
    "search_node",
    "synthesize_node",
]
