from unittest.mock import MagicMock

from app.agent.evidence.claim_validator import validate_claim, validate_model
from app.agent.nodes.model_node import model_node
from app.agent.nodes.plan_node import plan_node
from app.agent.research_model import build_research_model, model_brief
from app.ai.llm_gateway.base import LLMGatewayError, LLMResponse


def _llm(text: str) -> MagicMock:
    llm = MagicMock()
    llm.generate.return_value = LLMResponse(text=text, model="fake")
    return llm


def _claim(**kw):
    base = {"id": "C1", "text": "ours is better", "kind": "performance", "source": "literature",
            "baseline": "BERT", "metric": "F1", "dataset": "GLUE", "evidence_refs": [1]}
    return {**base, **kw}


def test_comparative_claim_with_baseline_metric_dataset_and_evidence_is_supported():
    assert validate_claim(_claim(), citation_count=3)["status"] == "supported"


def test_accuracy_only_claim_without_baseline_is_unsupported():
    result = validate_claim(_claim(baseline=None, source="user_results", evidence_refs=[]), citation_count=3)
    assert result["status"] == "unsupported"
    assert any("baseline" in i for i in result["issues"])


def test_proposed_claim_without_measurement_is_only_a_hypothesis():
    result = validate_claim(_claim(source="proposed", evidence_refs=[]), citation_count=3)
    assert result["status"] == "hypothesis"


def test_nonexistent_reference_is_flagged():
    result = validate_claim(_claim(evidence_refs=[9]), citation_count=3)
    assert result["status"] == "unsupported"
    assert any("does not exist" in i for i in result["issues"])


def test_novelty_claim_needs_cited_related_work():
    assert validate_claim(_claim(kind="novelty", evidence_refs=[]), 3)["status"] == "unsupported"
    assert validate_claim(_claim(kind="novelty", evidence_refs=[2]), 3)["status"] == "supported"


def test_validate_model_reports_broken_argument_chain():
    model = build_research_model({"contribution_type": "new_method", "question": "q"}, {"claims": [{"text": "x", "kind": "novelty"}]})
    validation = validate_model(model, 2)["validation"]
    assert not validation["ok"]
    assert "no research gap identified" in validation["issues"]
    assert "no research question or hypothesis stated" in validation["issues"]


def test_comparison_needs_two_baselines_and_system_needs_efficiency_metric():
    one = build_research_model(
        {"contribution_type": "comparison"}, {"research_gaps": [{"text": "g", "evidence_refs": [1]}], "research_questions": ["q"],
                                              "claims": [_claim()]})
    assert any("two compared" in i for i in validate_model(one, 2)["validation"]["issues"])
    system = build_research_model(
        {"contribution_type": "system"}, {"research_gaps": [{"text": "g", "evidence_refs": [1]}], "research_questions": ["q"],
                                          "claims": [_claim()]})
    assert any("efficiency claim" in i for i in validate_model(system, 2)["validation"]["issues"])


def test_survey_does_not_require_claims():
    model = validate_model(build_research_model({"contribution_type": "survey"}), 2)
    assert model["validation"]["ok"]


def test_model_brief_lists_status_and_policy():
    model = validate_model(build_research_model({"contribution_type": "new_method"}, {"claims": [_claim(baseline=None)]}), 2)
    brief = model_brief(model)
    assert "UNSUPPORTED" in brief and "CLAIM POLICY" in brief and "missing:" in brief


def test_model_node_extracts_and_validates_claims():
    llm = _llm('{"research_gaps": [{"text": "g", "evidence_refs": [1]}], "research_questions": ["q"], "claims": [' +
               '{"text": "faster", "kind": "efficiency", "source": "user_results", "baseline": "B", "metric": "p95 latency", "dataset": "D1"}]}')
    state = model_node({"question": "q", "contribution_type": "improvement", "research_mode": "novel_research",
                        "citations": [MagicMock()], "user_results": "p95 12ms vs 30ms"}, llm=llm)
    model = state["research_model"]
    assert model["claims"][0]["status"] == "supported"
    assert model["has_user_results"] and model["validation"]["ok"]


def test_model_node_survives_unparseable_llm_output_and_gateway_error():
    state = model_node({"question": "q", "research_mode": "novel_research", "citations": []}, llm=_llm("not json"))
    assert state["research_model"]["claims"] == []
    failing = MagicMock()
    failing.generate.side_effect = LLMGatewayError("down")
    assert model_node({"question": "q", "research_mode": "novel_research", "citations": []}, llm=failing)["research_model"]["claims"] == []


def test_model_node_skips_llm_for_survey_without_user_results():
    llm = _llm("{}")
    model_node({"question": "q", "research_mode": "survey", "citations": []}, llm=llm)
    llm.generate.assert_not_called()


def test_plan_node_classifies_contribution_and_user_choice_wins():
    reply = '{"contribution_type": "system", "methodology": "system_building", "paper_type": "system_paper", "topic": "DDoS in K8s", "queries": ["q"]}'
    state = plan_node({"question": "Xây dựng hệ thống phát hiện DDoS"}, llm=_llm(reply))
    assert (state["contribution_type"], state["research_mode"], state["paper_type"], state["topic"]) == ("system", "novel_research", "system_paper", "DDoS in K8s")
    forced = plan_node({"question": "q", "contribution_type": "survey"}, llm=_llm(reply))
    assert forced["contribution_type"] == "survey" and forced["research_mode"] == "survey"


def test_plan_node_derives_contribution_from_mode_when_missing():
    state = plan_node({"question": "Tổng quan RAG"}, llm=_llm('{"mode": "survey", "queries": ["q"]}'))
    assert state["contribution_type"] == "survey" and state["methodology"] == "survey_review"
