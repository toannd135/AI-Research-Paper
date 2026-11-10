"""Độ phủ kho nội bộ: số paper bài PHẢI cite và danh sách paper có evidence nhưng chưa được cite."""

from __future__ import annotations

import re
from math import ceil
from typing import Any

from app.core.config import get_settings

MIN_CITED_PAPERS = 25  # kho lớn hơn giới hạn phủ trọn: chỉ yêu cầu tối thiểu chừng này paper khác nhau
_LOCAL_EVIDENCE_TARGET = 40  # số chunk evidence muốn có ở chế độ chỉ-nội-bộ
_LOCAL_MAX_CHUNKS_CEILING = 12  # kho rất nhỏ vẫn không dồn quá nhiều chunk cho một paper


def local_chunks_per_paper(n_papers: int) -> int:
    """Giới hạn chunk mỗi paper ở chế độ chỉ-nội-bộ: kho càng nhỏ càng được lấy nhiều, để có đủ bằng chứng."""
    base = get_settings().local_max_chunks_per_paper
    if n_papers <= 0:
        return base
    return max(base, min(_LOCAL_MAX_CHUNKS_CEILING, ceil(_LOCAL_EVIDENCE_TARGET / n_papers)))


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
