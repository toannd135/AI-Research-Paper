from unittest.mock import MagicMock

from app.agent.evidence.hallucination_detector import find_unsupported_sentences
from app.ai.llm_gateway.base import LLMResponse


def _fake_llm(text: str) -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(text=text, model="fake")
    return llm


def test_returns_flagged_sentences():
    llm = _fake_llm('{"unsupported_sentences": ["Câu bịa số liệu."]}')

    result = find_unsupported_sentences("draft", "evidence", llm=llm)

    assert result == ["Câu bịa số liệu."]


def test_returns_empty_list_when_fully_supported():
    llm = _fake_llm('{"unsupported_sentences": []}')

    assert find_unsupported_sentences("draft", "evidence", llm=llm) == []


def test_returns_empty_list_when_llm_output_unparseable():
    llm = _fake_llm("not json")

    assert find_unsupported_sentences("draft", "evidence", llm=llm) == []
