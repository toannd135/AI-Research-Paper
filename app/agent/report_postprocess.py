"""Hậu xử lý báo cáo sau synthesize: kiểm chứng mermaid/table/chart, gỡ số liệu không có căn cứ,
dịch đoạn lẫn tiếng Việt và bổ sung biểu đồ từ Quantitative Evidence Ledger khi bài chưa có hình số liệu."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from app.agent.language import is_foreign_paragraph, language_name
from app.ai.llm_gateway.base import LLMGateway, Message

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(r"```(mermaid|table|chart)[ \t]*\n(.*?)```", re.DOTALL)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_CITE_RE = re.compile(r"\[\d+(?:[,\s–-]+\d+)*\]")
_MISSING = "–"
_AVG_COLUMN_RE = re.compile(r"average|avg|mean|trung bình", re.I)

_MERMAID_HEADERS = (
    "graph", "flowchart", "sequencediagram", "classdiagram", "statediagram", "erdiagram",
    "gantt", "pie", "journey", "mindmap", "timeline",
)

# --------------------------------------------------------------------------- mermaid
def validate_mermaid(code: str) -> list[str]:
    """Kiểm tra cấu trúc cơ bản của sơ đồ mermaid (không cần trình duyệt). Trả về danh sách lỗi."""
    errors: list[str] = []
    lines = [ln for ln in code.strip().split("\n") if ln.strip() and not ln.strip().startswith("%%")]
    if not lines:
        return ["Sơ đồ rỗng"]
    first = lines[0].strip().lower()
    if not any(first.startswith(h) for h in _MERMAID_HEADERS):
        errors.append(f"Dòng đầu không phải khai báo sơ đồ hợp lệ: '{lines[0].strip()[:40]}'")
    if first.startswith(("graph", "flowchart")):
        depth = 0
        for ln in lines[1:]:
            word = ln.strip().split(" ")[0]
            if word == "subgraph":
                depth += 1
            elif ln.strip() == "end":
                depth -= 1
        if depth != 0:
            errors.append("Số subgraph và end không khớp")
        if len(lines) < 2:
            errors.append("Sơ đồ không có node/cạnh nào")
    for i, ln in enumerate(lines, 1):
        if ln.count('"') % 2:
            errors.append(f"Dòng {i}: dấu nháy kép không cân")
        for o, c in (("[", "]"), ("(", ")"), ("{", "}")):
            if ln.count(o) != ln.count(c):
                errors.append(f"Dòng {i}: ngoặc '{o}{c}' không cân")
                break
        if "```" in ln:
            errors.append(f"Dòng {i}: lẫn dấu rào code")
    return errors[:6]


def _repair_mermaid(code: str, errors: list[str], gateway: LLMGateway, model_name: str | None) -> str | None:
    prompt = (
        "Fix the Mermaid diagram below so it parses with Mermaid v10. Keep the same meaning and the same node labels "
        "(English only). Wrap every node label in double quotes, avoid parentheses/brackets/semicolons/pipes inside labels, "
        "no `direction` lines, close every subgraph with `end`. Output ONLY the corrected diagram code, no fences, no commentary.\n\n"
        f"Detected problems: {'; '.join(errors)}\n\nDiagram:\n{code}"
    )
    try:
        out = gateway.generate(
            messages=[Message(role="system", content="You repair Mermaid diagram syntax."), Message(role="user", content=prompt)],
            model_name=model_name,
        ).text.strip()
    except Exception as e:
        logger.warning("Mermaid repair call failed: %s", e)
        return None
    return re.sub(r"^```(?:mermaid)?\s*|\s*```$", "", out).strip() or None


def fix_mermaid_block(code: str, gateway: LLMGateway | None, model_name: str | None, retries: int = 2) -> str | None:
    """Trả về sơ đồ hợp lệ (đã sửa nếu cần) hoặc None khi không cứu được."""
    from app.agent.format_sanitizer import sanitize_mermaid_block

    current = sanitize_mermaid_block(code)
    for attempt in range(retries + 1):
        errors = validate_mermaid(current)
        if not errors:
            return current
        if gateway is None or attempt == retries:
            break
        repaired = _repair_mermaid(current, errors, gateway, model_name)
        if not repaired:
            break
        current = sanitize_mermaid_block(repaired)
    return None


# --------------------------------------------------------------------------- table / chart
def _draft_numbers(draft: str) -> set[float]:
    return {float(n) for n in _NUM_RE.findall(_CITE_RE.sub(" ", draft))}


def _is_grounded(cell: str, known: set[float]) -> bool:
    nums = _NUM_RE.findall(_CITE_RE.sub(" ", cell))
    return all(float(n) in known for n in nums)


def scrub_table_spec(body: str, draft: str) -> str | None:
    """Thay ô số không xuất hiện trong draft bằng '–'. Trả về JSON mới, hoặc None nếu spec hỏng/không còn số liệu."""
    try:
        spec = json.loads(body)
        columns, rows = spec["columns"], spec["rows"]
    except (ValueError, KeyError, TypeError):
        return None
    if not isinstance(columns, list) or not isinstance(rows, list) or not rows:
        return None
    known = _draft_numbers(draft)
    n_cols = len(columns)
    clean_rows, numeric_cells = [], 0
    for row in rows:
        if not isinstance(row, list):
            return None
        row = [str(c) for c in (row + [""] * n_cols)[:n_cols]]
        for j, cell in enumerate(row):
            if j == 0 or _AVG_COLUMN_RE.search(str(columns[j])):
                continue
            if _NUM_RE.search(cell):
                if _is_grounded(cell, known):
                    numeric_cells += 1
                else:
                    row[j] = _MISSING
        clean_rows.append(row)
    if numeric_cells == 0:
        return None
    spec["rows"] = clean_rows
    return json.dumps(spec, ensure_ascii=False)


def scrub_chart_spec(body: str, draft: str) -> str | None:
    try:
        spec = json.loads(body)
        labels, series = spec["labels"], spec["series"]
    except (ValueError, KeyError, TypeError):
        return None
    known = _draft_numbers(draft)
    kept, real = [], 0
    for s in series:
        vals = s.get("values", [])
        if len(vals) != len(labels):
            continue
        vals = [v if isinstance(v, (int, float)) and float(v) in known else None for v in vals]
        real += sum(v is not None for v in vals)
        kept.append({**s, "values": vals})
    if not kept or real < 2:
        return None
    spec["series"] = kept
    return json.dumps(spec, ensure_ascii=False)


# --------------------------------------------------------------------------- ledger → fallback chart
def _ledger_rows(draft: str) -> list[dict[str, str]]:
    m = re.search(r"Quantitative Evidence Ledger(.*)", draft, re.I | re.DOTALL)
    if not m:
        return []
    rows = []
    for ln in m.group(1).split("\n"):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) < 5 or set(ln.strip()) <= set("|-: "):
            continue
        rows.append(dict(zip(("source", "method", "dataset", "metric", "value"), cells, strict=False)))
    return rows[1:] if rows and rows[0]["value"].lower().startswith("value") else rows


def build_ledger_chart(draft: str) -> str | None:
    """Dựng khối ```chart từ nhóm (metric, dataset) có nhiều phương pháp nhất trong ledger. Chỉ dùng số có thật."""
    groups: dict[tuple[str, str], list[tuple[str, float, str]]] = defaultdict(list)
    for r in _ledger_rows(draft):
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", _CITE_RE.sub("", r["value"]))
        if not m or not r["method"] or r["method"].lower().startswith("no quantitative"):
            continue
        groups[(r["metric"], r["dataset"])].append((r["method"], float(m.group(1)), r["source"]))
    best = max(groups.items(), key=lambda kv: len({x[0] for x in kv[1]}), default=None)
    if not best:
        return None
    (metric, dataset), items = best
    seen: dict[str, tuple[float, str]] = {}
    for method, val, src in items:
        seen.setdefault(method, (val, src))
    if len(seen) < 3:
        return None
    entries = sorted(seen.items(), key=lambda kv: -kv[1][0])[:8]
    cites = ", ".join(sorted({e[1][1] for e in entries if e[1][1]}))
    spec = {
        "type": "barh",
        "caption": f"Reported {metric} on {dataset} {cites}".strip(),
        "labels": [e[0][:40] for e in entries],
        "series": [{"name": metric, "values": [e[1][0] for e in entries]}],
    }
    return json.dumps(spec, ensure_ascii=False)


# --------------------------------------------------------------------------- language
def _skip_paragraph(p: str) -> bool:
    t = p.strip()
    return not t or t.startswith(("|", "#", "$$", "[", "**Keywords", "**Authors"))


def translate_foreign_paragraphs(text: str, target: str, gateway: LLMGateway | None, model_name: str | None) -> str:
    """Dịch các đoạn lẫn ngôn ngữ khác về ngôn ngữ đích (bỏ qua khối code/bảng/công thức, mục References)."""
    if gateway is None:
        return text
    body, sep, refs = text.partition("\n## References")
    parts = re.split(r"(```.*?```|\$\$.*?\$\$)", body, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2:
            continue
        for p in part.split("\n\n"):
            if _skip_paragraph(p) or not is_foreign_paragraph(p, target):
                continue
            try:
                out = gateway.generate(
                    messages=[
                        Message(
                            role="system",
                            content=(
                                f"Translate to {language_name(target)} in formal academic register. Keep markdown, citations [n], numbers, "
                                "LaTeX, code, proper names and method/model acronyms unchanged. Output only the translation."
                            ),
                        ),
                        Message(role="user", content=p),
                    ],
                    model_name=model_name,
                ).text.strip()
            except Exception as e:
                logger.warning("Translate call failed: %s", e)
                continue
            if out and not is_foreign_paragraph(out, target):
                part = part.replace(p, out)
        parts[i] = part
    return "".join(parts) + sep + refs


# --------------------------------------------------------------------------- entrypoint
def postprocess_report(
    report: str, draft: str, gateway: LLMGateway | None, model_name: str | None, language: str = "en"
) -> str:
    """Kiểm chứng/sửa mọi khối mermaid, table, chart; dịch đoạn lẫn Việt; chèn biểu đồ ledger nếu thiếu."""

    def _fix(m: re.Match) -> str:
        kind, body = m.group(1), m.group(2)
        if kind == "mermaid":
            fixed = fix_mermaid_block(body, gateway, model_name)
        elif kind == "table":
            fixed = scrub_table_spec(body, draft)
        else:
            fixed = scrub_chart_spec(body, draft)
        if fixed is None:
            logger.warning("Dropped invalid %s block from report", kind)
            return ""
        return f"```{kind}\n{fixed.strip()}\n```"

    report = _FENCE_RE.sub(_fix, report)
    report = translate_foreign_paragraphs(report, language, gateway, model_name)

    if "```chart" not in report:
        chart = build_ledger_chart(draft)
        marker = re.search(r"^## 5\.", report, re.MULTILINE)
        if chart and marker:
            block = f"```chart\n{chart}\n```\n\n"
            report = report[: marker.start()] + block + report[marker.start():]
    return re.sub(r"\n{3,}", "\n\n", report)
