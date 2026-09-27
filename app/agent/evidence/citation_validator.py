"""Kiểm tra citation [n] trong draft khớp với danh sách citations thật."""

import re

from app.core.schemas import Citation

_MARKER_RE = re.compile(r"\[(\d+)\]")


def find_invalid_citations(draft: str, citations: list[Citation]) -> list[int]:
    """Trả về danh sách số [n] xuất hiện trong draft nhưng KHÔNG có citation tương ứng."""
    valid_indices = set(range(1, len(citations) + 1))
    used = {int(m) for m in _MARKER_RE.findall(draft)}
    return sorted(used - valid_indices)
