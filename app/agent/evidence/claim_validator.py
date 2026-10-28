"""Kiểm chứng claim ↔ evidence và tính liên kết của chuỗi lập luận (gap → question → claim) bằng luật, không dùng LLM."""

from __future__ import annotations

from typing import Any

from app.agent.evidence.stats import ALPHA, compare_runs
from app.agent.research_model import CONTRIBUTION_TYPES

_COMPARATIVE = ("performance", "efficiency")


def _valid_refs(refs: list[int], citation_count: int) -> list[int]:
    return [n for n in refs if 1 <= n <= citation_count]


def _norm(value: str | None) -> str:
    return (value or "").strip().lower()


def _matching_runs(claim: dict[str, Any], experiments: list[dict[str, Any]]) -> tuple[list[float], list[float]]:
    """Giá trị các lần chạy của hệ thống đề xuất và của baseline mà claim nêu, cùng metric (và dataset nếu claim ghi)."""
    same = [
        e for e in experiments
        if _norm(e["metric"]) == _norm(claim.get("metric")) and (not claim.get("dataset") or _norm(e["dataset"]) == _norm(claim["dataset"]))
    ]
    proposed = [v for e in same if e["role"] == "proposed" for v in e["values"]]
    baselines = [e for e in same if e["role"] == "baseline"]
    named = [e for e in baselines if _norm(claim.get("baseline")) and _norm(claim["baseline"]) in _norm(e["system"])]
    chosen = named or (baselines if len({e["system"] for e in baselines}) == 1 else [])
    return proposed, [v for e in chosen for v in e["values"]]


def _significance(claim: dict[str, Any], experiments: list[dict[str, Any]]) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """(issues, warnings, stat) của so sánh thống kê; chỉ áp dụng cho claim so sánh dựa trên kết quả của người dùng."""
    if claim.get("kind") not in _COMPARATIVE or claim.get("source") != "user_results" or not claim.get("metric"):
        return [], [], None
    proposed, baseline = _matching_runs(claim, experiments)
    stat = compare_runs(proposed, baseline, claim["metric"])
    if stat is None:
        return [], ["only a single run per system: statistical significance cannot be assessed (report mean ± std over several seeds)"], None
    if not stat["favors_proposed"]:
        return [f"the measured runs do not favor the proposed method (mean {stat['mean_proposed']:.4g} vs {stat['mean_baseline']:.4g})"], [], stat
    if not stat["significant"]:
        return [f"the difference is not statistically significant (Welch t-test p={stat['p_value']:.3g} ≥ {ALPHA})"], [], stat
    return [], [], stat


def validate_claim(claim: dict[str, Any], citation_count: int, experiments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Gắn `status` (supported | hypothesis | unsupported) và `issues` (điều còn thiếu) cho 1 claim."""
    issues: list[str] = []
    refs = _valid_refs(claim.get("evidence_refs", []), citation_count)
    if claim.get("evidence_refs") and len(refs) != len(claim["evidence_refs"]):
        issues.append("cites a reference number that does not exist")
    has_evidence = bool(refs) or claim.get("source") == "user_results"
    kind = claim.get("kind")

    if kind in _COMPARATIVE:
        for field, label in (("baseline", "baseline"), ("metric", "metric"), ("dataset", "dataset")):
            if not claim.get(field):
                issues.append(f"no {label} specified for a comparative claim")
        if not has_evidence:
            issues.append("no measured result (cited source or user-provided experiment) backs this claim")
    elif kind == "novelty":
        if not refs:
            issues.append("novelty is not established by any cited related work")
    elif not has_evidence:
        issues.append("no supporting evidence")

    stat_issues, warnings, stat = _significance(claim, experiments or [])
    issues += stat_issues

    if not issues:
        status = "supported"
    elif claim.get("source") == "proposed" and not claim.get("evidence_refs"):
        status = "hypothesis"  # kết quả dự kiến, chưa được đo: chỉ được viết dạng giả thuyết
    else:
        status = "unsupported"
    result = {**claim, "status": status, "issues": issues, "warnings": warnings}
    if stat:
        result["stat"] = stat
    return result


def _check_requirements(model: dict[str, Any], claims: list[dict[str, Any]]) -> list[str]:
    needs = _needs(model.get("contribution_type"))
    comparative = [c for c in claims if c["kind"] in _COMPARATIVE]
    issues: list[str] = []
    if "baseline" in needs and not any(c.get("baseline") for c in comparative):
        issues.append("no comparative claim names a baseline, so superiority over prior work cannot be shown")
    if "two_baselines" in needs and len({c["baseline"] for c in comparative if c.get("baseline")}) < 2:
        issues.append("a comparative study needs at least two compared baselines/models")
    if "efficiency_metric" in needs and not any(c["kind"] == "efficiency" and c.get("metric") for c in claims):
        issues.append("a system paper needs an efficiency claim with a metric (latency, throughput, scalability)")
    if comparative and len({c["dataset"] for c in comparative if c.get("dataset")}) > 1 and "two_baselines" in needs:
        issues.append("compared results use different datasets; the comparison may not be fair")
    return issues


def _needs(contribution_type: str | None) -> list[str]:
    return CONTRIBUTION_TYPES.get(contribution_type or "", {}).get("needs", [])


def validate_model(model: dict[str, Any], citation_count: int) -> dict[str, Any]:
    """Kiểm từng claim và chuỗi lập luận; trả model kèm `validation` {ok, issues, unsupported_claims}."""
    experiments = model.get("experiments", [])
    claims = [validate_claim(c, citation_count, experiments) for c in model.get("claims", [])]
    gaps = [
        {**g, "evidence_refs": _valid_refs(g.get("evidence_refs", []), citation_count)} for g in model.get("research_gaps", [])
    ]
    issues: list[str] = []
    if model.get("contribution_type") != "survey":
        if not gaps:
            issues.append("no research gap identified")
        elif any(not g["evidence_refs"] for g in gaps):
            issues.append("a research gap is not linked to any cited related work")
        if not model.get("research_questions"):
            issues.append("no research question or hypothesis stated")
        if not claims:
            issues.append("no claim extracted: contribution cannot be checked against evidence")
        issues += _check_requirements(model, claims)
    unsupported = [c["id"] for c in claims if c["status"] == "unsupported"]
    return {
        **model,
        "research_gaps": gaps,
        "claims": claims,
        "validation": {"ok": not issues and not unsupported, "issues": issues, "unsupported_claims": unsupported},
    }
