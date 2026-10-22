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

_FENCE_RE = re.compile(r"```(mermaid|table|chart|image)[ \t]*\n(.*?)```", re.DOTALL)
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


_CLAIM_NUM_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:%|×|x\b)|\b\d+\.\d+\b|\b[A-Za-z]\s*=\s*\d+")
_YEAR_RE = re.compile(r"^(?:19|20)\d{2}$")
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _sentence_is_ungrounded(sentence: str, known: set[float]) -> bool:
    """Câu có trích dẫn [n] và số liệu kiểu %, ×, thập phân, 'T=50' mà số đó không xuất hiện trong draft/evidence."""
    if not _CITE_RE.search(sentence):
        return False
    body = _CITE_RE.sub(" ", sentence)
    for m in _CLAIM_NUM_RE.finditer(body):
        for n in _NUM_RE.findall(m.group(0)):
            if not _YEAR_RE.match(n) and float(n) not in known:
                return True
    return False


def drop_ungrounded_claims(text: str, draft: str, evidence_text: str = "") -> tuple[str, list[str]]:
    """Gỡ câu văn xuôi gán số liệu cho nguồn [n] nhưng số đó không có trong draft/evidence (nghi bịa/gán sai nguồn).

    Bỏ qua tiêu đề, bảng, danh sách ký hiệu, khối code. Trả về (văn bản, các câu đã gỡ).
    """
    known = _draft_numbers(draft) | _draft_numbers(evidence_text)
    dropped: list[str] = []
    out: list[str] = []
    in_fence = False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence or not line.strip() or line.lstrip().startswith(("#", "|", "$", "**Table", "**Figure")):
            out.append(line)
            continue
        kept = []
        for sent in _SENT_SPLIT_RE.split(line):
            if _sentence_is_ungrounded(sent, known):
                dropped.append(sent.strip())
            else:
                kept.append(sent)
        out.append(" ".join(kept))
    return "\n".join(out), dropped


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
    groups = spec.get("header_groups")
    if groups is not None and not _groups_match_columns(groups, n_cols):
        # LLM hay cộng sai span: bỏ nhóm tiêu đề, bảng vẫn dùng được (renderer sẽ không phải từ chối cả bài).
        logger.warning("Bỏ header_groups không khớp %d cột của bảng %r", n_cols, str(spec.get("caption", ""))[:60])
        spec.pop("header_groups")
    return json.dumps(spec, ensure_ascii=False)


def _groups_match_columns(groups, n_cols: int) -> bool:
    try:
        return sum(int(g["span"]) for g in groups) == n_cols
    except (KeyError, TypeError, ValueError):
        return False


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
def scrub_image_spec(body: str, figures: list[dict] | None) -> str | None:
    """Chỉ giữ ảnh có ref nằm trong danh sách hình thật; gắn đường dẫn và nguồn từ metadata (không tin JSON của LLM)."""
    try:
        spec = json.loads(body)
    except ValueError:
        return None
    by_id = {f["id"]: f for f in figures or []}
    ref = str(spec.get("ref", "")).strip() if isinstance(spec, dict) else ""
    fig = by_id.get(ref)
    if fig is None:
        logger.warning("Bỏ khối image ref=%r: không có trong AVAILABLE FIGURES %s", ref, sorted(by_id))
        return None
    source = f"{fig.get('source_title') or fig['paper_id']}, p. {fig['page']}"
    caption = str(spec.get("caption") or "").strip() or fig["caption"]
    return json.dumps({"ref": fig["id"], "caption": caption, "path": fig["path"], "source": source}, ensure_ascii=False)


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


def _llm_translate(text: str, target: str, gateway: LLMGateway, model_name: str | None, what: str = "text") -> str | None:
    try:
        return gateway.generate(
            messages=[
                Message(
                    role="system",
                    content=(
                        f"Translate the {what} to {language_name(target)} in formal academic register. Keep markdown, citations [n], numbers, "
                        "LaTeX, code, proper names and method/model acronyms unchanged. Output only the translation."
                    ),
                ),
                Message(role="user", content=text),
            ],
            model_name=model_name,
        ).text.strip()
    except Exception as e:
        logger.warning("Translate call failed: %s", e)
        return None


def _is_foreign_text(text: str, target: str) -> bool:
    """is_foreign_paragraph sau khi bỏ công thức: biến như d_i, di… làm bộ nhận diện nhầm sang tiếng Indonesia."""
    return is_foreign_paragraph(re.sub(r"\$[^$\n]*\$", " ", text), target)


def _is_foreign_short(text: str, target: str) -> bool:
    """Tiêu đề / ô bảng / nhãn ngắn: ngưỡng từ thấp hơn đoạn văn."""
    plain = re.sub(r"\$[^$]*\$|[#*|`]", " ", text)
    return is_foreign_paragraph(plain, target, min_words=2)


def _shape(obj):
    """Cấu trúc JSON bỏ chuỗi: khoá, độ dài list, số — để kiểm tra bản dịch không làm đổi dữ liệu."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_shape(v) for v in obj]
    return "s" if isinstance(obj, str) else obj


def _strip_fence(text: str) -> str:
    return re.sub(r"^```[a-z]*\n|\n?```$", "", text.strip())


def _translate_table(block: str, target: str, gateway: LLMGateway, model_name: str | None) -> str:
    out = _llm_translate(block, target, gateway, model_name, "Markdown table (keep every '|' and the separator row exactly)")
    if out:
        out = _strip_fence(out)
        a, b = block.strip().split("\n"), out.split("\n")
        if len(a) == len(b) and all(x.count("|") == y.count("|") for x, y in zip(a, b)):
            return out
    return block


def _translate_heading(line: str, target: str, gateway: LLMGateway, model_name: str | None) -> str:
    hashes, _, title = line.partition(" ")
    out = _llm_translate(title, target, gateway, model_name, "section heading (output the heading text only)")
    out = (out or "").strip().strip("#").strip()
    return f"{hashes} {out}" if out and "\n" not in out and not _is_foreign_short(out, target) else line


def _translate_json_block(kind: str, body: str, target: str, gateway: LLMGateway, model_name: str | None) -> str:
    """Dịch các giá trị chuỗi (caption, nhãn, tên cột…) của khối table/chart; từ chối nếu cấu trúc/số đổi."""
    try:
        spec = json.loads(body)
    except ValueError:
        return body
    out = _llm_translate(body, target, gateway, model_name, "JSON (translate only human-readable string values; keep keys, numbers and structure identical)")
    try:
        new = json.loads(_strip_fence(out or ""))
    except ValueError:
        return body
    return json.dumps(new, ensure_ascii=False) if _shape(new) == _shape(spec) else body


def _translate_mermaid(body: str, target: str, gateway: LLMGateway, model_name: str | None) -> str:
    out = _llm_translate(body, target, gateway, model_name, "Mermaid diagram (translate only the quoted node labels; keep ids, arrows and syntax identical)")
    if out:
        out = _strip_fence(out)
        if not validate_mermaid(out) and out.count("-->") == body.count("-->") and len(out.split("\n")) == len(body.strip().split("\n")):
            return out
    return body


def _translate_lines(part: str, target: str, gateway: LLMGateway, model_name: str | None) -> str:
    """Tiêu đề '#…' và khối bảng '|…' (bị bỏ qua ở bước đoạn văn) — dịch riêng, kiểm tra cấu trúc."""
    lines, out, i = part.split("\n"), [], 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            block = "\n".join(lines[i:j])
            out.append(_translate_table(block, target, gateway, model_name) if _is_foreign_short(block, target) else block)
            i = j
            continue
        if re.match(r"^#{1,6}\s", line) and _is_foreign_short(line, target):
            line = _translate_heading(line, target, gateway, model_name)
        out.append(line)
        i += 1
    return "\n".join(out)


def translate_foreign_paragraphs(text: str, target: str, gateway: LLMGateway | None, model_name: str | None) -> str:
    """Dịch mọi chỗ lẫn ngôn ngữ về ngôn ngữ đích: đoạn văn, tiêu đề, bảng Markdown, khối table/chart JSON, nhãn mermaid.

    Bỏ qua khối code, công thức $$ và mục References; mọi bản dịch cấu trúc đều được kiểm tra rồi mới thay.
    """
    if gateway is None:
        return text
    body, sep, refs = text.partition("\n## References")
    parts = re.split(r"(```.*?```|\$\$.*?\$\$)", body, flags=re.DOTALL)
    for i, part in enumerate(parts):
        if i % 2:
            fence = re.match(r"```(table|chart|mermaid)[ \t]*\n(.*?)\n?```$", part, re.DOTALL)
            if fence and _is_foreign_short(fence.group(2), target):
                kind, inner = fence.groups()
                new = (_translate_mermaid if kind == "mermaid" else lambda b, *a: _translate_json_block(kind, b, *a))(inner, target, gateway, model_name)
                parts[i] = f"```{kind}\n{new.strip()}\n```"
            continue
        for chunk in part.split("\n\n"):
            lines = chunk.split("\n")
            k = 0
            while k < len(lines) and lines[k].lstrip().startswith("#"):  # tiêu đề dính liền đoạn văn: dịch riêng ở _translate_lines
                k += 1
            p = "\n".join(lines[k:])
            if _skip_paragraph(p) or not (_is_foreign_text(p, target) or _is_foreign_short(p, target)):
                continue
            out = _llm_translate(p, target, gateway, model_name, "text")
            if out and not _is_foreign_text(out, target) and not _is_foreign_short(out, target):
                part = part.replace(p, out)
        parts[i] = _translate_lines(part, target, gateway, model_name)
    return "".join(parts) + sep + refs


# --------------------------------------------------------------------------- entrypoint
def postprocess_report(
    report: str,
    draft: str,
    gateway: LLMGateway | None,
    model_name: str | None,
    language: str = "en",
    figures: list[dict] | None = None,
    evidence_text: str = "",
) -> str:
    """Kiểm chứng/sửa mọi khối mermaid, table, chart, image; dịch đoạn lẫn Việt; chèn biểu đồ ledger nếu thiếu."""
    used_figures: set[str] = set()

    def _fix(m: re.Match) -> str:
        kind, body = m.group(1), m.group(2)
        if kind == "mermaid":
            fixed = fix_mermaid_block(body, gateway, model_name)
        elif kind == "table":
            fixed = scrub_table_spec(body, draft)
        elif kind == "image":
            fixed = scrub_image_spec(body, figures)
            if fixed is not None:
                ref = json.loads(fixed)["ref"]
                if ref in used_figures:
                    logger.warning("Bỏ khối image trùng ref=%s", ref)
                    fixed = None
                used_figures.add(ref)
        else:
            fixed = scrub_chart_spec(body, draft)
        if fixed is None:
            logger.warning("Dropped invalid %s block from report", kind)
            return ""
        return f"```{kind}\n{fixed.strip()}\n```"

    report = _FENCE_RE.sub(_fix, report)
    report = translate_foreign_paragraphs(report, language, gateway, model_name)
    report, dropped = drop_ungrounded_claims(report, draft, evidence_text)
    for sent in dropped:
        logger.warning("Gỡ câu có số liệu không có trong evidence: %s", sent[:160])

    if "```chart" not in report:
        chart = build_ledger_chart(draft)
        marker = re.search(r"^## 5\.", report, re.MULTILINE)
        if chart and marker:
            block = f"```chart\n{chart}\n```\n\n"
            report = report[: marker.start()] + block + report[marker.start():]
    return re.sub(r"\n{3,}", "\n\n", report)
