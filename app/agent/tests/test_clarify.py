from unittest.mock import MagicMock

from app.agent.clarify import clarify
from app.ai.llm_gateway.base import LLMResponse


def _fake_llm(text: str) -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(text=text, model="fake")
    return llm


def test_clarify_returns_needs_clarification_when_llm_asks():
    llm = _fake_llm('{"status": "needs_clarification", "questions": ["Phạm vi là gì?"]}')

    result = clarify("So sánh các phương pháp", llm=llm)

    assert result["status"] == "needs_clarification"
    assert result["questions"] == ["Phạm vi là gì?"]


def test_clarify_returns_ready_when_llm_has_enough_info():
    llm = _fake_llm('{"status": "ready", "refined_question": "So sánh BM25 và vector search"}')

    result = clarify("So sánh BM25 và vector search trong RAG", llm=llm)

    assert result["status"] == "ready"
    assert result["refined_question"] == "So sánh BM25 và vector search"


def test_clarify_does_not_ask_again_when_answers_already_provided():
    llm = _fake_llm('{"status": "needs_clarification", "questions": ["vẫn thiếu"]}')

    result = clarify("câu hỏi mơ hồ", clarification_answers={"phạm vi": "RAG"}, llm=llm)

    assert result["status"] == "ready"
    assert result["refined_question"] == "câu hỏi mơ hồ"


def test_clarify_falls_back_to_ready_when_llm_output_unparseable():
    llm = _fake_llm("không phải JSON")

    result = clarify("câu hỏi bất kỳ", llm=llm)

    assert result == {"status": "ready", "refined_question": "câu hỏi bất kỳ"}
