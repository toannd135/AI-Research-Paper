"""Taxonomy nghiên cứu (contribution / methodology / paper type) và Research Knowledge Model.

Một dự án nghiên cứu được mô hình hóa thành dữ liệu có cấu trúc (gaps, questions, claims, experiments)
thay vì chỉ là văn bản, để mỗi claim có thể được kiểm chứng với evidence (xem evidence/claim_validator.py).
"""

from __future__ import annotations

from typing import Any

CONTRIBUTION_TYPES: dict[str, dict[str, Any]] = {
    "new_method": {
        "label": "New method / model",
        "methodology": "experimental",
        "paper_type": "original_research",
        "mode": "novel_research",
        "needs": ["baseline"],
        "guidance": (
            "CONTRIBUTION TYPE = NEW METHOD. The paper must justify the novelty: explain the architecture and what is new versus the closest "
            "prior work, define the baselines, the metrics, the datasets and an ablation study. Every superiority claim needs a baseline, a "
            "metric and a dataset."
        ),
    },
    "improvement": {
        "label": "Improvement of an existing method",
        "methodology": "experimental",
        "paper_type": "original_research",
        "mode": "novel_research",
        "needs": ["baseline"],
        "guidance": (
            "CONTRIBUTION TYPE = IMPROVEMENT OF AN EXISTING METHOD. Describe exactly what technical change is made to the base method, the "
            "measured gain, the computational cost and the trade-off (e.g. accuracy vs latency). Compare against the unmodified base method "
            "under identical conditions."
        ),
    },
    "comparison": {
        "label": "Comparative study",
        "methodology": "experimental",
        "paper_type": "original_research",
        "mode": "novel_research",
        "needs": ["two_baselines"],
        "guidance": (
            "CONTRIBUTION TYPE = COMPARATIVE STUDY. Focus on fairness of the comparison: the same datasets, splits, tuning budget and metrics "
            "for every compared model; state the evaluation protocol explicitly and analyse the results (including variance) instead of "
            "proposing a new model."
        ),
    },
    "system": {
        "label": "System / implementation",
        "methodology": "system_building",
        "paper_type": "system_paper",
        "mode": "novel_research",
        "needs": ["efficiency_metric"],
        "guidance": (
            "CONTRIBUTION TYPE = SYSTEM. Focus on system architecture, deployment, workload, throughput, latency, scalability and operational "
            "overhead; describe the test environment (hardware, workload generator) so that measurements are reproducible."
        ),
    },
    "survey": {
        "label": "Survey / review",
        "methodology": "survey_review",
        "paper_type": "review",
        "mode": "survey",
        "needs": [],
        "guidance": "",
    },
}

METHODOLOGIES = ("experimental", "theoretical", "survey_review", "system_building", "case_study")
PAPER_TYPES = ("original_research", "review", "system_paper")

# Loại claim: so sánh hiệu năng/hiệu quả cần baseline+metric+dataset; novelty cần tài liệu liên quan chứng minh khoảng trống.
CLAIM_KINDS = ("performance", "efficiency", "novelty", "generalization", "other")
CLAIM_SOURCES = ("literature", "user_results", "proposed")


def normalize_contribution(value: str | None) -> str | None:
    return value if isinstance(value, str) and value in CONTRIBUTION_TYPES else None


def contribution_from_mode(mode: str | None) -> str:
    return "survey" if mode == "survey" else "new_method"


def contribution_profile(state: dict) -> dict[str, Any]:
    return CONTRIBUTION_TYPES[normalize_contribution(state.get("contribution_type")) or contribution_from_mode(state.get("research_mode"))]


def normalize_choice(value: Any, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def contribution_guidance(state: dict) -> str:
    return contribution_profile(state)["guidance"]


def _clean_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [v.strip() for v in value if isinstance(v, str) and v.strip()]


def _ref_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, int) and not isinstance(v, bool) and v > 0]


def normalize_claim(raw: Any, index: int) -> dict[str, Any] | None:
    """Chuẩn hóa 1 claim do LLM trả về; trả None nếu không có nội dung."""
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
        return None
    return {
        "id": f"C{index}",
        "text": raw["text"].strip(),
        "kind": normalize_choice(raw.get("kind"), CLAIM_KINDS, "other"),
        "source": normalize_choice(raw.get("source"), CLAIM_SOURCES, "proposed"),
        "baseline": raw["baseline"].strip() if isinstance(raw.get("baseline"), str) and raw["baseline"].strip() else None,
        "metric": raw["metric"].strip() if isinstance(raw.get("metric"), str) and raw["metric"].strip() else None,
        "dataset": raw["dataset"].strip() if isinstance(raw.get("dataset"), str) and raw["dataset"].strip() else None,
        "evidence_refs": _ref_list(raw.get("evidence_refs")),
    }


def normalize_gap(raw: Any, index: int) -> dict[str, Any] | None:
    if isinstance(raw, str):
        raw = {"text": raw}
    if not isinstance(raw, dict) or not isinstance(raw.get("text"), str) or not raw["text"].strip():
        return None
    return {"id": f"G{index}", "text": raw["text"].strip(), "evidence_refs": _ref_list(raw.get("evidence_refs"))}


def normalize_experiment(raw: Any, index: int) -> dict[str, Any] | None:
    """Một chuỗi kết quả đo (mỗi giá trị là một lần chạy/seed/fold) của một hệ thống trên một metric+dataset."""
    if not isinstance(raw, dict) or not isinstance(raw.get("system"), str) or not raw["system"].strip():
        return None
    values = [float(v) for v in raw.get("values") or [] if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not values:
        return None
    return {
        "id": f"E{index}",
        "system": raw["system"].strip(),
        "role": "proposed" if raw.get("role") == "proposed" else "baseline",
        "metric": raw["metric"].strip() if isinstance(raw.get("metric"), str) and raw["metric"].strip() else None,
        "dataset": raw["dataset"].strip() if isinstance(raw.get("dataset"), str) and raw["dataset"].strip() else None,
        "values": values,
    }


def build_research_model(state: dict, parsed: Any = None) -> dict[str, Any]:
    """Dựng Research Knowledge Model từ taxonomy trong state và kết quả trích xuất của LLM (nếu có)."""
    profile = contribution_profile(state)
    parsed = parsed if isinstance(parsed, dict) else {}
    gaps = [g for i, raw in enumerate(parsed.get("research_gaps") or [], 1) if (g := normalize_gap(raw, i))]
    claims = [c for i, raw in enumerate(parsed.get("claims") or [], 1) if (c := normalize_claim(raw, i))]
    return {
        "domain": state.get("field"),
        "topic": state.get("topic") or state.get("question"),
        "contribution_type": normalize_contribution(state.get("contribution_type")) or contribution_from_mode(state.get("research_mode")),
        "methodology": normalize_choice(state.get("methodology"), METHODOLOGIES, profile["methodology"]),
        "paper_type": normalize_choice(state.get("paper_type"), PAPER_TYPES, profile["paper_type"]),
        "target_venue": state.get("target_venue") or None,
        "research_questions": _clean_str_list(parsed.get("research_questions")),
        "research_gaps": gaps,
        "claims": claims,
        "experiments": [e for i, raw in enumerate(parsed.get("experiments") or [], 1) if (e := normalize_experiment(raw, i))],
        "has_user_results": bool(state.get("user_results")),
    }


def model_brief(model: dict[str, Any] | None) -> str:
    """Đoạn chỉ dẫn đưa vào prompt viết bài: claim nào được khẳng định, claim nào chỉ là giả thuyết."""
    if not model:
        return ""
    lines = ["RESEARCH KNOWLEDGE MODEL (authoritative; obey the claim policy below):"]
    for g in model.get("research_gaps", []):
        refs = " ".join(f"[{n}]" for n in g["evidence_refs"]) or "(no citation)"
        lines.append(f"- Gap {g['id']}: {g['text']} {refs}")
    for q in model.get("research_questions", []):
        lines.append(f"- Research question: {q}")
    for c in model.get("claims", []):
        detail = ", ".join(f"{k}={c[k]}" for k in ("baseline", "metric", "dataset") if c.get(k)) or "no baseline/metric/dataset"
        refs = " ".join(f"[{n}]" for n in c["evidence_refs"])
        lines.append(f"- Claim {c['id']} [{c.get('status', 'unchecked').upper()}]: {c['text']} ({detail}) {refs}".rstrip())
        for issue in c.get("issues", []):
            lines.append(f"    * missing: {issue}")
        for warning in c.get("warnings", []):
            lines.append(f"    * caution: {warning}")
    for issue in model.get("validation", {}).get("issues", []):
        lines.append(f"- Argument gap: {issue}")
    lines.append(
        "CLAIM POLICY: state a claim as an established result ONLY if its status is SUPPORTED. For HYPOTHESIS claims write 'we hypothesize / "
        "we expect' and describe the planned evaluation; for UNSUPPORTED claims do NOT write that the method is better/faster/novel — present "
        "them as a limitation or future work and name what evidence is missing. Never invent numbers to turn a claim into a supported one."
    )
    return "\n".join(lines)
