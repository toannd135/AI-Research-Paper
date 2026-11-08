"""Giao thức tổng quan do NGƯỜI DÙNG khai báo (`<upload_dir>/review_protocol.json`) — nguồn duy nhất cho mục Review Methodology.

Hệ thống không bao giờ tự tạo CSDL, chuỗi tìm kiếm, số sàng lọc hay người đánh giá. Khi người dùng thực hiện tìm kiếm/sàng lọc thật
và ghi lại vào tệp này, module kiểm tra tính đầy đủ và số học (identified − duplicates = screened → full text → included),
rồi đưa NGUYÊN VĂN vào REVIEW FACTS và dựng sơ đồ PRISMA tất định từ đúng các con số đó. Tệp thiếu/sai → dùng mô tả
"retrieval coverage" trung thực như cũ. Mẫu tệp: `docs/review-protocol.md`.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

FILENAME = "review_protocol.json"
REVIEW_TYPES = {"narrative", "scoping", "systematic"}
GUIDELINES = {"systematic": {"PRISMA 2020", "none"}, "scoping": {"PRISMA-ScR", "none"}, "narrative": {"none"}}
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def load_protocol(upload_dir: str | None = None) -> dict[str, Any] | None:
    path = Path(upload_dir or get_settings().upload_dir) / FILENAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.exception("Không đọc được giao thức review %s", path)
        return None
    return data if isinstance(data, dict) else None


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def validate_protocol(p: dict[str, Any], corpus_size: int | None = None) -> list[str]:
    """Danh sách lỗi; rỗng = dùng được. Không sửa số người dùng khai báo."""
    problems: list[str] = []
    rtype = p.get("review_type")
    if rtype not in REVIEW_TYPES:
        return [f"review_type phải là một trong {sorted(REVIEW_TYPES)}"]
    guideline = p.get("guideline", "none")
    if guideline not in GUIDELINES[rtype]:
        problems.append(f"guideline '{guideline}' không hợp với review_type '{rtype}' (cho phép: {sorted(GUIDELINES[rtype])})")
    dbs = p.get("databases") or []
    if rtype != "narrative" and not dbs:
        problems.append("thiếu databases (tên, search_string, date, hits)")
    for i, db in enumerate(dbs, start=1):
        if not isinstance(db, dict) or not db.get("name") or not db.get("search_string"):
            problems.append(f"databases[{i}] thiếu name/search_string")
        elif not _DATE_RE.match(str(db.get("date", ""))):
            problems.append(f"databases[{i}] ({db.get('name')}) thiếu ngày tìm kiếm YYYY-MM-DD")
        elif _int(db.get("hits")) is None:
            problems.append(f"databases[{i}] ({db.get('name')}) thiếu số kết quả (hits)")
    if rtype != "narrative":
        for key in ("inclusion_criteria", "exclusion_criteria"):
            if not p.get(key):
                problems.append(f"thiếu {key}")
    c = p.get("counts") or {}
    if rtype != "narrative" or c:
        problems += _check_counts(c, dbs, corpus_size)
    rev = p.get("reviewers") or {}
    n_screen = _int(rev.get("screening"))
    if rtype != "narrative" and n_screen is None:
        problems.append("reviewers.screening (số người sàng lọc) chưa khai báo")
    if (n_screen or 0) >= 2 and not rev.get("disagreement_resolution"):
        problems.append("có ≥2 người sàng lọc nhưng thiếu reviewers.disagreement_resolution")
    return problems


def _check_counts(c: dict[str, Any], dbs: list[Any], corpus_size: int | None) -> list[str]:
    keys = ("identified", "duplicates_removed", "screened", "excluded_screening", "full_text_assessed", "included")
    vals = {k: _int(c.get(k)) for k in keys}
    missing = [k for k, v in vals.items() if v is None]
    if missing:
        return [f"counts thiếu/không hợp lệ: {', '.join(missing)}"]
    excl_ft = c.get("excluded_full_text") or {}
    if not isinstance(excl_ft, dict) or any(_int(v) is None for v in excl_ft.values()):
        return ["counts.excluded_full_text phải là {lý do: số}"]
    out = []
    hits = sum(_int(db.get("hits")) or 0 for db in dbs if isinstance(db, dict)) + (_int(c.get("other_sources")) or 0)
    if dbs and hits != vals["identified"]:
        out.append(f"identified={vals['identified']} khác tổng hits các CSDL + other_sources = {hits}")
    if vals["identified"] - vals["duplicates_removed"] != vals["screened"]:
        out.append(f"identified − duplicates_removed = {vals['identified'] - vals['duplicates_removed']} ≠ screened={vals['screened']}")
    if vals["screened"] - vals["excluded_screening"] != vals["full_text_assessed"]:
        out.append(f"screened − excluded_screening = {vals['screened'] - vals['excluded_screening']} ≠ full_text_assessed={vals['full_text_assessed']}")
    if vals["full_text_assessed"] - sum(excl_ft.values()) != vals["included"]:
        out.append(f"full_text_assessed − Σexcluded_full_text = {vals['full_text_assessed'] - sum(excl_ft.values())} ≠ included={vals['included']}")
    if corpus_size and vals["included"] != corpus_size:
        out.append(f"included={vals['included']} nhưng kho PDF có {corpus_size} paper — kho phải chứa đúng các nghiên cứu được đưa vào")
    return out


def protocol_facts(p: dict[str, Any]) -> str:
    """Khối REVIEW FACTS từ giao thức đã hợp lệ — chỉ nêu đúng những gì người dùng khai báo."""
    lines = [
        "USER-DECLARED REVIEW PROTOCOL (carried out by the authors; describe exactly this, add nothing, keep every number):",
        f"- Review type: {p['review_type']}; reporting guideline: {p.get('guideline', 'none')}.",
    ]
    for db in p.get("databases") or []:
        lines.append(f"- Database {db['name']} searched on {db['date']} with: {db['search_string']} → {db['hits']} records.")
    if p.get("date_range"):
        lines.append(f"- Publication date range: {p['date_range']}.")
    for key, label in (("inclusion_criteria", "Inclusion"), ("exclusion_criteria", "Exclusion")):
        if p.get(key):
            lines.append(f"- {label} criteria: " + "; ".join(map(str, p[key])) + ".")
    c = p.get("counts") or {}
    if c:
        excl = "; ".join(f"{k}: {v}" for k, v in (c.get("excluded_full_text") or {}).items())
        lines.append(
            f"- Flow: {c['identified']} identified, {c['duplicates_removed']} duplicates removed, {c['screened']} titles/abstracts screened, "
            f"{c['excluded_screening']} excluded at screening, {c['full_text_assessed']} full texts assessed ({excl or 'no exclusions'}), {c['included']} included."
        )
    rev = p.get("reviewers") or {}
    if rev:
        lines.append(
            f"- Reviewers: {rev.get('screening', 'not stated')} for screening, {rev.get('extraction', 'not stated')} for data extraction"
            + (f"; disagreements resolved by {rev['disagreement_resolution']}" if rev.get("disagreement_resolution") else "")
            + ". Never state a different number of reviewers."
        )
    if p.get("quality_assessment"):
        lines.append(f"- Quality / risk-of-bias assessment: {p['quality_assessment']}.")
    if p.get("extraction_verification"):
        lines.append(f"- Verification of automatically extracted data: {p['extraction_verification']}.")
    if c:
        lines.append("- A flow diagram built from these numbers is inserted automatically in Section 2.2; refer to it, do not draw another.")
    return "\n".join(lines) + "\n"


def prisma_block(p: dict[str, Any]) -> str | None:
    """Sơ đồ luồng (mermaid) từ đúng số người dùng khai báo; None nếu không có counts."""
    c = p.get("counts") or {}
    if not c:
        return None
    excl = "<br/>".join(f"{k}: {v}" for k, v in (c.get("excluded_full_text") or {}).items()) or "none"
    db_names = ", ".join(str(db.get("name")) for db in p.get("databases") or [] if isinstance(db, dict))
    return (
        "```mermaid\nflowchart TD\n"
        f'  A["Records identified (n = {c["identified"]})<br/>{db_names}"] --> B["After duplicates removed (n = {c["screened"]})"]\n'
        f'  B --> C["Titles/abstracts screened (n = {c["screened"]})"]\n'
        f'  C --> D["Excluded at screening (n = {c["excluded_screening"]})"]\n'
        f'  C --> E["Full texts assessed (n = {c["full_text_assessed"]})"]\n'
        f'  E --> F["Full texts excluded<br/>{excl}"]\n'
        f'  E --> G["Studies included (n = {c["included"]})"]\n'
        "```"
    )


def inject_prisma(report: str, block: str | None) -> str:
    """Chèn sơ đồ trước mục 2.3 (hoặc trước mục 3) — không tạo mục mới; đã có sơ đồ thì giữ nguyên."""
    if not block or "Records identified (n =" in report:
        return report
    marker = re.search(r"^###\s*2\.3\b", report, re.M) or re.search(r"^##\s*3\.", report, re.M)
    if not marker:
        return report
    return report[: marker.start()] + block + "\n\n" + report[marker.start() :]
