"""Phân tầng bằng chứng theo dataset đích: trực tiếp / dataset khác / chỉ tham khảo kiến trúc.

Reviewer phàn nàn bài trộn số liệu FeTA/FLARE vào kết luận về BraTS và trích paper không có số liệu như thể là bằng
chứng. Module này không gọi LLM: xác định "họ dataset" đích (tên dataset nêu trong câu hỏi, nếu không có thì họ có nhiều
paper nhất trong sổ cái), rồi xếp mỗi paper được trích vào một tầng để prompt và bảng hồ sơ nêu rõ.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from app.agent.evidence.quant_check import ResultRecord

DIRECT = "direct"
OTHER_DATASET = "other_dataset"
REFERENCE_ONLY = "reference_only"

_NOISE_RE = re.compile(r"\b(?:19|20)\d{2}\b|\b(?:challenge|dataset|benchmark|data|set|v\d+)\b|[^a-z0-9 ]", re.I)


def dataset_family(name: str | None) -> str | None:
    """'BraTS 2021' / 'BraTS-2020 challenge' → 'brats'; bỏ năm, chữ 'challenge/dataset', dấu câu."""
    if not name:
        return None
    fam = re.sub(r"\s+", "", _NOISE_RE.sub(" ", name.lower()))
    fam = re.sub(r"\d+$", "", fam)  # 'brats2021' sau khi bỏ khoảng trắng
    return fam or None


def target_family(records: Iterable[ResultRecord], question: str = "") -> tuple[str | None, str | None]:
    """(họ dataset đích, tên hiển thị). Ưu tiên họ được nêu trong câu hỏi; không có thì họ có nhiều paper nhất."""
    papers: dict[str, set[str]] = {}
    display: dict[str, str] = {}
    for r in records:
        fam = dataset_family(r.dataset)
        if fam:
            papers.setdefault(fam, set()).add(r.paper_id)
            display.setdefault(fam, r.dataset.strip())
    if not papers:
        return None, None
    q = re.sub(r"[^a-z0-9]", "", (question or "").lower())
    named = [f for f in papers if len(f) >= 3 and f in q]
    if named:
        fam = max(named, key=lambda f: len(papers[f]))
    else:
        ranked = Counter({f: len(p) for f, p in papers.items()}).most_common(2)
        if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
            return None, None  # hòa: không đoán dataset đích
        fam = ranked[0][0]
    return fam, display[fam]


def classify_evidence(records: list[ResultRecord], cited_paper_ids: Iterable[str], question: str = "") -> dict:
    """{"target": tên hiển thị|None, "tiers": {paper_id: tầng}, "datasets": {paper_id: [dataset khác]}}."""
    fam, shown = target_family(records, question)
    by_paper: dict[str, set[str]] = {}
    for r in records:
        if r.dataset:
            by_paper.setdefault(r.paper_id, set()).add(r.dataset.strip())
    tiers: dict[str, str] = {}
    datasets: dict[str, list[str]] = {}
    for pid in dict.fromkeys(cited_paper_ids):
        names = by_paper.get(pid, set())
        if not names:
            tiers[pid] = REFERENCE_ONLY
        elif fam is None or any(dataset_family(n) == fam for n in names):
            tiers[pid] = DIRECT
        else:
            tiers[pid] = OTHER_DATASET
            datasets[pid] = sorted(names)
    return {"target": shown if fam else None, "tiers": tiers, "datasets": datasets}


def _refs(pids: list[str], paper_to_n: dict[str, int]) -> str:
    return ", ".join(f"[{n}]" for n in sorted(paper_to_n[p] for p in pids if p in paper_to_n)) or "none"


def tiers_fact(classified: dict, paper_to_n: dict[str, int]) -> str:
    """Khối đưa vào prompt: paper nào là bằng chứng trực tiếp, dataset khác, hay chỉ tham khảo kiến trúc."""
    target = classified.get("target")
    tiers: dict[str, str] = classified.get("tiers") or {}
    if not target or not tiers:
        return ""
    direct = [p for p, t in tiers.items() if t == DIRECT]
    other = [p for p, t in tiers.items() if t == OTHER_DATASET]
    ref_only = [p for p, t in tiers.items() if t == REFERENCE_ONLY]
    other_detail = "; ".join(
        f"[{paper_to_n[p]}] {', '.join(classified['datasets'].get(p, []))}" for p in sorted(other, key=lambda x: paper_to_n.get(x, 0)) if p in paper_to_n
    )
    return (
        f"EVIDENCE TIERS (target benchmark: {target}; computed from the extracted records):\n"
        f"- Direct evidence (results reported on {target}): {_refs(direct, paper_to_n)}.\n"
        f"- Indirect evidence from OTHER datasets: {other_detail or 'none'}. Always name the dataset when citing these values, keep them out of "
        f"{target} tables, rankings and conclusions, and describe them only as transfer/supporting evidence.\n"
        f"- Architectural reference only (no extracted quantitative result): {_refs(ref_only, paper_to_n)}. Cite them for design ideas only, "
        "never as performance evidence.\n"
        "Keep these three kinds of evidence visibly separate in the text (e.g. separate paragraphs or table groups).\n"
    )
