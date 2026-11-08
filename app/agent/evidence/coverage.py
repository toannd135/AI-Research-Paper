"""Độ phủ kho nội bộ: số paper bài PHẢI cite và danh sách paper có evidence nhưng chưa được cite."""

from __future__ import annotations

import re
from typing import Any

from app.core.config import get_settings

MIN_CITED_PAPERS = 25  # kho lớn hơn giới hạn phủ trọn: chỉ yêu cầu tối thiểu chừng này paper khác nhau


def full_coverage_applies(n_available: int) -> bool:
    limit = get_settings().full_corpus_coverage_limit
    return 0 < n_available <= limit


def coverage_target(n_available: int) -> int:
    """Kho nhỏ (≤ full_corpus_coverage_limit): cite hết; kho lớn: tối thiểu MIN_CITED_PAPERS."""
    return n_available if full_coverage_applies(n_available) else min(MIN_CITED_PAPERS, n_available)


def uncited_papers(citations: list[Any], text: str) -> list[str]:
    """paper_id có trong Available Citations nhưng không có [n] nào trong văn bản."""
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    first: dict[str, int] = {}
    for i, c in enumerate(citations, start=1):
        first.setdefault(getattr(c, "paper_id", None) or "", i)
    owners = {pid: [j for j, c in enumerate(citations, start=1) if (getattr(c, "paper_id", None) or "") == pid] for pid in first}
    return sorted(pid for pid, idx in owners.items() if pid and not cited.intersection(idx))
