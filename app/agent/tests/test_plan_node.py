from unittest.mock import MagicMock

from app.agent.nodes.plan_node import plan_node
from app.ai.llm_gateway.base import LLMResponse


def _fake_llm(text: str) -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(text=text, model="fake")
    return llm


def test_plan_node_parses_queries_from_llm():
    llm = _fake_llm('{"queries": ["q1", "q2", "q3"]}')

    state = plan_node({"question": "So sánh A và B"}, llm=llm)

    assert state["search_queries"] == ["q1", "q2", "q3"]
    assert state["question"] == "So sánh A và B"


def test_plan_node_falls_back_to_question_when_unparseable():
    llm = _fake_llm("not json")

    state = plan_node({"question": "So sánh A và B"}, llm=llm)

    assert state["search_queries"] == ["So sánh A và B"]
