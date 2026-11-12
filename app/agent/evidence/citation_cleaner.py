"""Bộ chuẩn hóa và định dạng danh mục tài liệu tham khảo theo chuẩn học thuật (IEEE/ACM).

Chức năng:
1. Deduplicate: Hợp nhất các chunk thuộc cùng một bài báo về một trích dẫn duy nhất.
2. Canonical Formatter: Định dạng trích dẫn theo chuẩn 'Authors (Year). Title. Venue/DOI',
   tuyệt đối không dump raw search snippet (Page: 1, Section: ...).
3. Citation Pruner & Remapper: Lọc bỏ bài báo không được cite trong văn bản,
   đánh số lại thứ tự [1], [2], ... tăng dần và đồng bộ vào nội dung văn bản.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.agent.evidence.citation_validator import expand_citation_clusters
from app.agent.evidence.report_structure import _LOCATED_CITE_RE, _MERMAID_CITE_RE, _clean_data_fence
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def _read_catalog(path: Path) -> dict[str, dict[str, str]]:
    """Đọc một tệp catalog.json; rỗng nếu lỗi hoặc sai định dạng."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Không đọc được catalog %s", path)
        return {}
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def _local_catalog() -> dict[str, dict[str, str]]:
    """Metadata của PDF nội bộ (khóa = paper_id); rỗng nếu không có.

    Ưu tiên `<upload_dir>/catalog.json`. Nếu không có (vd. UPLOAD_DIR mặc định `data/papers`
    trong khi catalog thật ở `data/papers_brain/`), gộp mọi `catalog.json` trong các thư mục
    con cấp 1 của thư mục cha upload_dir (không đọc catalog.full.json).
    """
    upload_dir = Path(get_settings().upload_dir)
    path = upload_dir / "catalog.json"
    if path.is_file():
        return _read_catalog(path)
    parent = upload_dir.parent
    if not parent.is_dir():
        return {}
    merged: dict[str, dict[str, str]] = {}
    found: list[str] = []
    for candidate in sorted(parent.glob("*/catalog.json")):
        if candidate.parent == upload_dir or not candidate.is_file():
            continue
        for pid, meta in _read_catalog(candidate).items():
            merged.setdefault(pid, meta)
        found.append(str(candidate))
    if found:
        logger.warning(
            "Không có catalog tại %s; dùng catalog dự phòng: %s (%d paper)", path, ", ".join(found), len(merged)
        )
    return merged


_DB_META: dict[str, dict[str, str]] = {}  # paper_id -> metadata đọc từ PDF ({} = không có trong DB); cache trong tiến trình
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


@lru_cache(maxsize=1)
def _manifest_index() -> dict[str, dict[str, Any]]:
    """Tên tệp PDF -> mục trong `_manifest.json` (title, year, doi lấy từ OpenAlex lúc tải corpus), gộp mọi thư mục data/*."""
    upload_dir = Path(get_settings().upload_dir)
    index: dict[str, dict[str, Any]] = {}
    for path in [upload_dir / "_manifest.json", *sorted(upload_dir.parent.glob("*/_manifest.json"))]:
        if not path.is_file():
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("Không đọc được manifest %s", path)
            continue
        for e in entries if isinstance(entries, list) else []:
            if isinstance(e, dict) and e.get("file"):
                index.setdefault(str(e["file"]), e)
    return index


def _apply_manifest(meta: dict[str, str], *names: str) -> dict[str, str]:
    """Manifest (tiêu đề/năm/DOI chuẩn) đè lên metadata đoán từ PDF; tác giả vẫn lấy từ PDF."""
    entry = next((_manifest_index()[n] for n in names if n and n in _manifest_index()), None)
    if not entry:
        return meta
    out = dict(meta)
    if entry.get("title"):
        out["title"] = str(entry["title"])
    if entry.get("year"):
        out["year"] = str(entry["year"])
    if entry.get("doi"):
        out["doi"] = re.sub(r"^https?://(dx\.)?doi\.org/", "", str(entry["doi"]))
    return out


def _db_metadata(ids: set[str]) -> dict[str, dict[str, str]]:
    """Metadata trích dẫn của các paper trong DB (đọc từ chính PDF đã upload) — cho paper không có trong catalog.json.

    Chỉ tra id dạng UUID (paper nội bộ); lỗi DB (vd. chạy test không có Postgres) → bỏ qua.
    """
    missing = {i for i in ids if i and _UUID_RE.match(i) and i not in _DB_META}
    if missing:
        try:
            from sqlalchemy import select

            from app.agent.evidence.pdf_metadata import pdf_citation_metadata
            from app.api.models.paper import Paper
            from app.core.database import SessionLocal

            with SessionLocal() as db:
                rows = db.execute(select(Paper.id, Paper.filename, Paper.file_path).where(Paper.id.in_(missing))).all()
            found = {
                str(pid): _apply_manifest(pdf_citation_metadata(fp, fn), fn, Path(fp or "").name) for pid, fn, fp in rows
            }
            for pid in missing:
                meta = found.get(pid) or {}
                _DB_META[pid] = meta if meta.get("title") else {}
        except Exception:
            logger.warning("Không lấy được metadata paper từ DB", exc_info=True)
    return {i: _DB_META[i] for i in ids if _DB_META.get(i)}


def corpus_catalog() -> dict[str, dict[str, str]]:
    """Catalog của kho đang chạy: catalog.json (đã duyệt tay) + metadata đọc từ PDF cho paper upload chưa có trong catalog.

    Task chạy trong một kho (có phạm vi paper) → chỉ gồm paper của kho đó, để số paper/khoảng năm/survey trong bài
    không lấy nhầm catalog của kho khác (vd. kho deepfake bị ghi '52 catalogued papers' của kho MRI).
    Không có phạm vi → giữ nguyên catalog.json như trước.
    """
    from app.core.scope import get_allowed_paper_ids

    files = _local_catalog()
    allowed = get_allowed_paper_ids()
    if allowed is None:
        return files
    allowed = {str(i) for i in allowed}
    scoped = {pid: meta for pid, meta in files.items() if pid in allowed}
    scoped.update(_db_metadata(allowed - set(scoped)))
    return scoped


def _normalize_title(title: str) -> str:
    """Chuẩn hóa tiêu đề để so khớp deduplication."""
    clean = re.sub(r"[^a-zA-Z0-9\s]", " ", title).lower()
    return " ".join(clean.split())


def _extract_citation_metadata(paper_id: str, snippet: str = "") -> dict[str, str]:
    """Trích xuất authors, title, year, venue từ chuỗi paper_id hoặc snippet."""
    # Paper nội bộ có metadata trong catalog: dùng nguyên, không đoán từ snippet
    pid = paper_id.strip()
    local = _local_catalog().get(pid) or _db_metadata({pid}).get(pid)
    if local:
        authors = [a.strip() for a in local.get("authors", "").split(",") if a.strip()]
        return {
            "title": local.get("title", paper_id)[:180],
            "authors": f"{authors[0]} et al." if len(authors) > 2 else " and ".join(authors) or "Anonymous",
            "year": local.get("year", "") or "n.d.",
            "venue": local.get("venue", "") or "Full text in the review corpus",
            "doi": local.get("doi", ""),
        }

    # Mẫu 1: "Title: X Authors: Y (Year) Venue/DOI: Z"
    combined = f"{paper_id} {snippet}"

    title = paper_id.strip()
    authors = ""
    year = ""
    venue = ""

    title_match = re.search(r"Title:\s*([^\n\r]+?)(?=\s+Authors:|\s+DOI:|\s+Venue:|$)", combined, re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip().strip('"').strip("'")

    auth_match = re.search(r"Authors:\s*([^\n\r]+?)(?=\s+\(\d{4}\)|\s+DOI:|\s+Venue:|\s+Title:|$)", combined, re.IGNORECASE)
    if auth_match:
        authors = auth_match.group(1).strip()

    year_match = re.search(r"\b(20[12]\d)\b", combined)
    if year_match:
        year = year_match.group(1)

    venue_match = re.search(r"(?:Venue/Publisher|Venue|Published in):\s*([^\n\r]+?)(?=\s+DOI:|$)", combined, re.IGNORECASE)
    if venue_match:
        venue = venue_match.group(1).strip()

    doi_match = re.search(r"DOI:\s*([^\s,]+)", combined, re.IGNORECASE)
    doi = doi_match.group(1).strip() if doi_match else ""

    # Dọn dẹp tiêu đề nếu còn dính metadata
    for prefix in ["Title:", "Title :", "title:"]:
        if title.startswith(prefix):
            title = title[len(prefix):].strip()

    # Dọn dẹp authors
    if authors:
        authors = authors.rstrip(",;")
        if not authors.endswith("et al.") and not authors.endswith("et al") and "," in authors:
            parts = [p.strip() for p in authors.split(",") if p.strip()]
            if len(parts) > 2:
                authors = f"{parts[0]} et al."
            else:
                authors = " and ".join(parts)
        if authors.endswith("et al"):
            authors += "."
    else:
        # Thử đoán tác giả từ title
        lead_words = title.split()[:2]
        authors = " ".join(lead_words) + " et al." if len(lead_words) >= 2 else "Anonymous et al."

    if not year:
        year = "2024"

    return {
        "title": title[:180],
        "authors": authors,
        "year": year,
        "venue": venue or "arXiv preprint",
        "doi": doi,
    }


_CITE_CLUSTER_RE = re.compile(r"\[\d+\](?:(?:,\s*)?\[\d+\])+")
_BLOCK_RE = re.compile(r"(```(?:table)[ \t]*\n)(.*?)(```)", re.DOTALL)
_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)


_SELF_RANGE_RE = re.compile(r"\[(\d+)\]\s*[–—-]\s*\[\1\]")  # '[1]–[1]' sau khi đánh số lại


def _collapse_cluster(m: re.Match) -> str:
    numbers = list(dict.fromkeys(re.findall(r"\d+", m.group(0))))
    return ", ".join(f"[{n}]" for n in numbers)


def _merge_cluster(m: re.Match) -> str:
    return "[" + ", ".join(dict.fromkeys(re.findall(r"\d+", m.group(0)))) + "]"


def _collapse_text(text: str) -> str:
    return _CITE_CLUSTER_RE.sub(_collapse_cluster, _SELF_RANGE_RE.sub(r"[\1]", text))


def _collapse_in_json(value: Any) -> Any:
    if isinstance(value, str):
        return _collapse_text(value)
    if isinstance(value, list):
        return [_collapse_in_json(v) for v in value]
    if isinstance(value, dict):
        return {k: _collapse_in_json(v) for k, v in value.items()}
    return value


def collapse_duplicate_citations(text: str) -> str:
    """Gộp trích dẫn liền kề trùng nhau sau khi đánh số lại ('[1], [1]' -> '[1]', '[1]–[1]' -> '[1]'); giữ thứ tự xuất hiện đầu tiên.

    Sửa văn bản thường, chuỗi JSON trong ```table/```chart và nhãn ```mermaid; mảng số và khối code khác giữ nguyên.
    """

    def _table(m: re.Match) -> str:
        try:
            spec = json.loads(m.group(2))
        except ValueError:
            return m.group(0)
        return f"{m.group(1)}{json.dumps(_collapse_in_json(spec), ensure_ascii=False)}\n{m.group(3)}"

    out: list[str] = []
    pos = 0
    for fence in _FENCE_RE.finditer(text):
        out.append(_collapse_text(text[pos : fence.start()]))
        block = fence.group(0)
        if block.startswith("```table"):
            out.append(_BLOCK_RE.sub(_table, block))
        elif block.startswith("```mermaid"):
            # nhãn mermaid: '[2], [38], [2]' -> '[2, 38]' cho gọn trong nút
            out.append(re.sub(r"(?<![\w\]])\[\d+\](?:,\s*\[\d+\])*", _merge_cluster, block))
        else:
            out.append(_map_fence_citations(block, _collapse_text))
        pos = fence.end()
    out.append(_collapse_text(text[pos:]))
    return "".join(out)


def _map_json_strings(value: Any, fn) -> Any:
    if isinstance(value, str):
        return fn(value) if "[" in value else value
    if isinstance(value, list):
        return [_map_json_strings(v, fn) for v in value]
    if isinstance(value, dict):
        return {k: _map_json_strings(v, fn) for k, v in value.items()}
    return value


def _map_fence_citations(block: str, fn) -> str:
    """Áp `fn` lên trích dẫn trong khối hình: ```table/```chart chỉ sửa chuỗi JSON (mảng số giữ nguyên), ```mermaid chỉ sửa cụm [n,...]
    trong nhãn. Khối code khác giữ nguyên."""
    if block.startswith(("```table", "```chart")):
        return _clean_data_fence(block, lambda spec: _map_json_strings(spec, fn))
    if block.startswith("```mermaid"):
        return _MERMAID_CITE_RE.sub(lambda m: fn(m.group(0)), block)
    return block


def _apply_to_citation_text(text: str, fn) -> str:
    """Áp `fn` lên mọi chỗ có thể chứa trích dẫn: văn bản thường, chuỗi JSON của ```table/```chart, nhãn ```mermaid."""
    out: list[str] = []
    pos = 0
    for fence in _FENCE_RE.finditer(text):
        out.append(fn(text[pos : fence.start()]))
        out.append(_map_fence_citations(fence.group(0), fn))
        pos = fence.end()
    out.append(fn(text[pos:]))
    return "".join(out)


def _expand_outside_code(text: str) -> str:
    """Tách cụm trích dẫn trong văn bản thường, chuỗi JSON của ```table/```chart và nhãn ```mermaid; khối code khác giữ nguyên."""
    return _apply_to_citation_text(text, expand_citation_clusters)


def clean_and_deduplicate_citations(
    citations: list[Any],
    text: str,
) -> tuple[str, list[str]]:
    """Hợp nhất các citation trùng lặp, format IEEE chuẩn, và đồng bộ lại số [n] trong văn bản.

    Returns:
        (updated_text, clean_reference_lines)
    """
    updated_text, references, _ = clean_and_deduplicate_citations_ex(citations, text)
    return updated_text, references


def clean_and_deduplicate_citations_ex(
    citations: list[Any],
    text: str,
) -> tuple[str, list[str], list[Any]]:
    """Như `clean_and_deduplicate_citations`, thêm danh sách citation theo số [n] MỚI.

    `numbered[k-1]` là citation đại diện của reference [k] trong văn bản đã đánh số lại, để kiểm chứng
    bản cuối (số [n] mới không còn trùng chỉ số trong `citations` gốc).
    """
    if not citations:
        return text, [], []

    # 0. Tách cụm '[7, 73]'/'[3–5]' thành marker đơn để bước đánh số lại không bỏ sót (cụm sẽ được gộp lại ở bước 4).
    text = _expand_outside_code(text)

    # 1. Deduplicate các citations dựa trên tiêu đề chuẩn hóa
    canonical_list: list[dict[str, str]] = []
    norm_to_canon_idx: dict[str, int] = {}
    orig_idx_to_canon_idx: dict[int, int] = {}

    for orig_idx, c in enumerate(citations, start=1):
        pid = getattr(c, "paper_id", "") or (c.get("paper_id") if isinstance(c, dict) else "")
        snippet = getattr(c, "text_snippet", "") or (c.get("text_snippet") if isinstance(c, dict) else "")
        meta = _extract_citation_metadata(pid, str(snippet))
        norm_t = _normalize_title(meta["title"])

        if norm_t in norm_to_canon_idx:
            canon_idx = norm_to_canon_idx[norm_t]
        else:
            canon_idx = len(canonical_list) + 1
            norm_to_canon_idx[norm_t] = canon_idx
            canonical_list.append(meta)

        orig_idx_to_canon_idx[orig_idx] = canon_idx

    # 2. Tìm tất cả các chỉ số citation được thực sự sử dụng trong văn bản
    # chỉ đếm chỗ có thể là trích dẫn (không đếm mảng số trong JSON chart/table)
    cite_view: list[str] = []
    _apply_to_citation_text(text, lambda s: cite_view.append(s) or s)
    cite_text = "\n".join(cite_view)
    used_orig_indices = [int(m) for m in re.findall(r"\[(\d+)\]", cite_text)]
    used_orig_indices += [int(n) for m in _LOCATED_CITE_RE.finditer(cite_text) for n in re.findall(r"\d+", m.group(1))]
    used_canon_indices = sorted({orig_idx_to_canon_idx[i] for i in used_orig_indices if i in orig_idx_to_canon_idx})

    # Nếu văn bản chưa cite gì (hoặc draft offline), giữ lại tất cả canonical
    if not used_canon_indices:
        used_canon_indices = list(range(1, len(canonical_list) + 1))

    # 3. Tạo bảng ánh xạ mới: canon_idx -> new_sequential_idx (1, 2, 3...)
    canon_to_new: dict[int, int] = {old_c: new_i for new_i, old_c in enumerate(used_canon_indices, start=1)}
    orig_to_new: dict[int, int] = {}
    for orig_i, canon_i in orig_idx_to_canon_idx.items():
        if canon_i in canon_to_new:
            orig_to_new[orig_i] = canon_to_new[canon_i]

    # 4. Thay thế các nhãn [n] trong văn bản
    def _repl_citation(match: re.Match) -> str:
        idx = int(match.group(1))
        new_idx = orig_to_new.get(idx)
        return f"[{new_idx}]" if new_idx is not None else match.group(0)

    def _repl_located(match: re.Match) -> str:
        # '[5, Table 2]' dùng cùng ánh xạ với '[5]'; số không có trong ánh xạ giữ nguyên (strip_dangling_citations xử lý sau)
        nums = [str(orig_to_new.get(int(n), n)) for n in re.findall(r"\d+", match.group(1))]
        return "[" + ", ".join(dict.fromkeys(nums)) + ", " + match.group(2) + "]"

    updated_text = _apply_to_citation_text(
        text, lambda s: _LOCATED_CITE_RE.sub(_repl_located, re.sub(r"\[(\d+)\]", _repl_citation, s))
    )
    updated_text = collapse_duplicate_citations(updated_text)

    # 5. Sinh danh sách tham khảo theo định dạng chuẩn IEEE
    first_orig: dict[int, Any] = {}
    for orig_i, canon_i in orig_idx_to_canon_idx.items():
        first_orig.setdefault(canon_i, citations[orig_i - 1])
    numbered = [first_orig[old_c] for old_c in used_canon_indices]
    formatted_references = []
    for old_c in used_canon_indices:
        new_i = canon_to_new[old_c]
        meta = canonical_list[old_c - 1]
        authors = meta["authors"]
        title = meta["title"]
        year = meta["year"]
        venue = meta["venue"]
        doi_part = f", DOI: {meta['doi']}" if meta["doi"] else ""

        ref_entry = f"[{new_i}] {authors}, \"{title},\" *{venue}*, {year}{doi_part}."
        formatted_references.append(ref_entry)

    return updated_text, formatted_references, numbered
