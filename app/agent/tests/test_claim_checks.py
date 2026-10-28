from unittest.mock import MagicMock

from app.agent.evidence.claim_scan import find_leaked_claims, soften_leaked_claims
from app.agent.evidence.claim_validator import validate_claim
from app.agent.evidence.stats import compare_runs, lower_is_better
from app.agent.research_model import build_research_model, normalize_experiment
from app.ai.llm_gateway.base import LLMGatewayError, LLMResponse


def _exp(system, role, values, metric="F1", dataset="D1"):
    return {"id": "E", "system": system, "role": role, "metric": metric, "dataset": dataset, "values": values}


def _claim(**kw):
    base = {"id": "C1", "text": "Our model outperforms LSTM on F1", "kind": "performance", "source": "user_results",
            "baseline": "LSTM", "metric": "F1", "dataset": "D1", "evidence_refs": []}
    return {**base, **kw}


def test_compare_runs_needs_two_runs_each_and_handles_direction():
    assert compare_runs([0.9], [0.8, 0.81]) is None
    good = compare_runs([0.95, 0.94, 0.96], [0.90, 0.91, 0.89], "F1")
    assert good["significant"] and good["favors_proposed"]
    latency = compare_runs([12.0, 12.5, 11.8], [30.0, 31.0, 29.0], "p95 latency")
    assert latency["significant"] and lower_is_better("p95 latency")
    worse = compare_runs([0.80, 0.81, 0.79], [0.90, 0.91, 0.89], "F1")
    assert not worse["favors_proposed"] and not worse["significant"]


def test_identical_runs_have_no_variance_but_are_handled():
    assert compare_runs([0.9, 0.9], [0.8, 0.8])["significant"]
    assert not compare_runs([0.9, 0.9], [0.9, 0.9])["significant"]


def test_significant_difference_keeps_claim_supported_and_records_stat():
    exps = [_exp("ours", "proposed", [0.95, 0.94, 0.96]), _exp("LSTM", "baseline", [0.90, 0.91, 0.89])]
    result = validate_claim(_claim(), 0, exps)
    assert result["status"] == "supported" and result["stat"]["p_value"] < 0.05


def test_non_significant_difference_makes_claim_unsupported():
    exps = [_exp("ours", "proposed", [0.91, 0.89, 0.93]), _exp("LSTM", "baseline", [0.90, 0.92, 0.88])]
    result = validate_claim(_claim(), 0, exps)
    assert result["status"] == "unsupported"
    assert any("not statistically significant" in i for i in result["issues"])


def test_single_run_only_warns():
    exps = [_exp("ours", "proposed", [0.95]), _exp("LSTM", "baseline", [0.90])]
    result = validate_claim(_claim(), 0, exps)
    assert result["status"] == "supported" and result["warnings"]


def test_literature_claims_are_not_tested_statistically():
    result = validate_claim(_claim(source="literature", evidence_refs=[1]), 2, [])
    assert result["status"] == "supported" and result["warnings"] == []


def test_normalize_experiment_drops_invalid_and_build_model_keeps_valid():
    assert normalize_experiment({"system": "x", "values": []}, 1) is None
    assert normalize_experiment({"values": [1]}, 1) is None
    model = build_research_model({}, {"experiments": [{"system": "ours", "role": "proposed", "metric": "F1", "values": [0.9, "bad", 0.95]}]})
    assert model["experiments"][0]["values"] == [0.9, 0.95]


WEAK = [{"id": "C1", "status": "unsupported", "text": "The proposed model reduces inference latency", "baseline": "Model B",
         "metric": "p95 latency", "dataset": "D01"}]


def test_find_leaked_claims_flags_assertive_sentence_only():
    report = (
        "## 4. Results\n\n"
        "The proposed model reduces inference latency on D01 compared with Model B. "
        "We hypothesize that the proposed model reduces inference latency in future deployments.\n\n"
        "| a | The proposed model reduces inference latency |\n"
        "The proposed pipeline supports Kubernetes operators.\n"
    )
    leaks = find_leaked_claims(report, WEAK)
    assert [lk["claim_id"] for lk in leaks] == ["C1"]
    assert leaks[0]["sentence"].startswith("The proposed model reduces")


def test_supported_claims_are_never_flagged():
    assert find_leaked_claims("The proposed model reduces inference latency.", [{**WEAK[0], "status": "supported"}]) == []


def _gateway(text: str) -> MagicMock:
    gw = MagicMock()
    gw.generate.return_value = LLMResponse(text=text, model="fake")
    return gw


def test_soften_replaces_sentence_and_reports_unresolved():
    report = "Intro. The proposed model reduces inference latency on D01 compared with Model B. End."
    leaks = find_leaked_claims(report, WEAK)
    gw = _gateway('{"rewrites": [{"original": "' + leaks[0]["sentence"] + '", "rewritten": "We expect the proposed model to lower latency on D01; this remains to be verified."}]}')
    new, unresolved = soften_leaked_claims(report, leaks, gw, None)
    assert "remains to be verified" in new and "reduces inference latency" not in new and unresolved == []


def test_soften_keeps_sentence_when_rewrite_still_assertive_or_llm_fails():
    report = "The proposed model reduces inference latency on D01 compared with Model B."
    leaks = find_leaked_claims(report, WEAK)
    still = _gateway('{"rewrites": [{"original": "' + leaks[0]["sentence"] + '", "rewritten": "The model significantly outperforms."}]}')
    new, unresolved = soften_leaked_claims(report, leaks, still, None)
    assert new == report and unresolved == leaks
    failing = MagicMock()
    failing.generate.side_effect = LLMGatewayError("down")
    assert soften_leaked_claims(report, leaks, failing, None) == (report, leaks)
