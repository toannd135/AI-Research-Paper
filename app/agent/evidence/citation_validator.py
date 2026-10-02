"""Kiểm tra citation [n] trong draft khớp với danh sách citations thật và không bị gán ép sai nguồn."""

import re

from app.core.schemas import Citation

_MARKER_RE = re.compile(r"\[(\d+)\]")

# Regex tìm kiếm tên phương pháp / tác giả đi kèm ngay trước trích dẫn [n]
# Ví dụ: "IRCoT [4]", "Self-RAG [12]", "CoVe [6]", "Pan et al. [6]"
_CLAIM_CITATION_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9\-_]+(?:\s+et\s+al\.)?)\s*\[(\d+)\]"
)

# Các từ thông dụng không phải là tên riêng bài báo
_STOP_WORDS = {
    "table", "figure", "section", "step", "ref", "reference", "baseline",
    "method", "study", "work", "model", "survey", "in", "and", "or", "to",
    "see", "from", "by", "with", "algorithm", "hop", "paper", "approach",
    "paradigm", "variant", "equation", "formula", "case", "example"
}


def find_invalid_citations(draft: str, citations: list[Citation]) -> list[int]:
    """Trả về danh sách số [n] xuất hiện trong draft nhưng KHÔNG có citation tương ứng."""
    valid_indices = set(range(1, len(citations) + 1))
    used = {int(m) for m in _MARKER_RE.findall(draft)}
    return sorted(used - valid_indices)


def find_citation_misattributions(draft: str, citations: list[Citation]) -> list[str]:
    """Phát hiện các trường hợp gán ép sai nguồn (Citation Misattribution / Force-Mapping).

    Ví dụ: Viết 'IRCoT [4]' nhưng bài báo [4] thực tế là 'HippoRAG' mà không hề liên quan đến IRCoT.
    """
    if not citations or not draft:
        return []

    misattributions: list[str] = []
    seen = set()

    for match in _CLAIM_CITATION_RE.finditer(draft):
        raw_entity = match.group(1).strip()
        idx_str = match.group(2)
        idx = int(idx_str)

        # Loại trừ các từ thông dụng (Table [1], Section [2], v.v.)
        clean_name = raw_entity.replace(" et al.", "").strip()
        if clean_name.lower() in _STOP_WORDS:
            continue

        # Bỏ qua nếu độ dài quá ngắn
        if len(clean_name) < 3:
            continue

        if 1 <= idx <= len(citations):
            cit = citations[idx - 1]
            cit_corpus = f"{cit.paper_id} {cit.text_snippet or ''} {cit.section or ''}".lower()

            # Chuẩn hóa để so khớp (ví dụ: 'self-rag' -> 'self rag' hoặc 'self-rag')
            clean_lower = clean_name.lower()
            normalized_name = re.sub(r"[^a-z0-9]", "", clean_lower)
            normalized_corpus = re.sub(r"[^a-z0-9]", "", cit_corpus)

            # Nếu tên phương pháp/tác giả hoàn toàn không xuất hiện trong bài báo được cite
            if clean_lower not in cit_corpus and normalized_name not in normalized_corpus:
                key = (clean_name, idx)
                if key not in seen:
                    seen.add(key)
                    paper_title = cit.paper_id[:50]
                    misattributions.append(
                        f"'{raw_entity} [{idx}]' bị gán sai nguồn: Bài báo [{idx}] ('{paper_title}...') không chứa thông tin về '{clean_name}'"
                    )

    return misattributions
