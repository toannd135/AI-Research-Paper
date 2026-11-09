"""Kiểm tra citation [n] trong draft khớp với danh sách citations thật và không bị gán ép sai nguồn."""

import re

from app.core.schemas import Citation

_MARKER_RE = re.compile(r"\[(\d+)\]")
# Cụm trích dẫn trong một cặp ngoặc: '[7, 73]', '[3–5]', '[2; 9-11]' (≥2 mục hoặc một khoảng).
_ITEM = r"\d+(?:\s*[–—-]\s*\d+)?"
_CLUSTER_RE = re.compile(rf"\[(\d+\s*[–—-]\s*\d+|{_ITEM}(?:\s*[,;]\s*{_ITEM})+)\]")
_MAX_RANGE = 30  # khoảng dài hơn thế này không phải trích dẫn (vd. '[1-100]' là thang đo) -> giữ nguyên


def _expand_cluster(m: re.Match) -> str:
    numbers: list[int] = []
    for item in re.split(r"\s*[,;]\s*", m.group(1)):
        lo_hi = re.split(r"\s*[–—-]\s*", item)
        lo, hi = int(lo_hi[0]), int(lo_hi[-1])
        if hi < lo or hi - lo > _MAX_RANGE:
            return m.group(0)
        numbers.extend(range(lo, hi + 1))
    return ", ".join(f"[{n}]" for n in dict.fromkeys(numbers))


def expand_citation_clusters(text: str) -> str:
    """'[7, 73]' -> '[7], [73]', '[3–5]' -> '[3], [4], [5]' để mọi bước đánh số lại/kiểm tra chỉ cần xử lý marker đơn."""
    return _CLUSTER_RE.sub(_expand_cluster, text)

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
    used = {int(m) for m in _MARKER_RE.findall(expand_citation_clusters(draft))}
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

            # Nếu tên phương pháp/tác giả hoàn toàn không xuất hiện trong bài báo được cite
            # So khớp theo ranh giới từ: 'unetr' không được coi là có mặt trong 'nnunetrevisited'
            spaced_name = " ".join(re.findall(r"[a-z0-9]+", clean_lower))
            spaced_corpus = " " + " ".join(re.findall(r"[a-z0-9]+", cit_corpus)) + " "
            corpus_tokens = set(spaced_corpus.split())
            present = f" {spaced_name} " in spaced_corpus or normalized_name in corpus_tokens
            if not present:
                key = (clean_name, idx)
                if key not in seen:
                    seen.add(key)
                    paper_title = cit.paper_id[:50]
                    misattributions.append(
                        f"'{raw_entity} [{idx}]' bị gán sai nguồn: Bài báo [{idx}] ('{paper_title}...') không chứa thông tin về '{clean_name}'"
                    )

    return misattributions
