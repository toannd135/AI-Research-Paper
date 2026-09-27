from unittest.mock import patch

from app.agent.graph import MAX_ITERATIONS, run_graph
from app.ai.llm_gateway.base import LLMResponse
from app.core.schemas import Chunk, ScoredChunk


class _FakeGateway:
    """Định tuyến response theo nội dung system prompt để giả lập từng node riêng biệt."""

    def __init__(self, hallucination_results: list[str]):
        self._hallucination_results = iter(hallucination_results)
        self.analyze_calls = 0
        self.hallucination_calls = 0

    def generate(self, messages, model_name=None):
        system = messages[0].content

        if "lập kế hoạch tìm kiếm" in system:
            return LLMResponse(text='{"queries": ["q1"]}', model="fake")

        if "fact-checker" in system:
            self.hallucination_calls += 1
            result = next(self._hallucination_results)
            return LLMResponse(text=result, model="fake")

        if "tổng hợp draft nghiên cứu" in system:
            return LLMResponse(text="# Báo cáo\n...\n[1]", model="fake")

        # analyze_node
        self.analyze_calls += 1
        return LLMResponse(text="Nội dung phân tích [1].", model="fake")


def _scored(id_: str) -> ScoredChunk:
    return ScoredChunk(chunk=Chunk(id=id_, paper_id="p1", text="evidence text", chunk_index=0), score=0.9)


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_graph_retries_on_critique_failure_then_passes(mock_hybrid, mock_rerank):
    mock_hybrid.return_value = []
    mock_rerank.return_value = [_scored("a")]

    gateway = _FakeGateway(hallucination_results=[
        '{"unsupported_sentences": ["câu bịa"]}',
        '{"unsupported_sentences": []}',
    ])

    state = run_graph("Câu hỏi test", llm=gateway)

    assert gateway.analyze_calls == 2
    assert gateway.hallucination_calls == 2
    assert state["iterations"] == 2
    assert state["report"].startswith("# Báo cáo")


@patch("app.agent.tools.search_papers.rerank")
@patch("app.agent.tools.search_papers.search_hybrid")
def test_graph_stops_at_max_iterations_even_if_still_failing(mock_hybrid, mock_rerank):
    mock_hybrid.return_value = []
    mock_rerank.return_value = [_scored("a")]

    gateway = _FakeGateway(hallucination_results=[
        '{"unsupported_sentences": ["vẫn bịa"]}' for _ in range(MAX_ITERATIONS + 1)
    ])

    state = run_graph("Câu hỏi test", llm=gateway)

    assert state["iterations"] == MAX_ITERATIONS
    assert "report" in state
