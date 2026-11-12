"""Hậu xử lý báo cáo sau synthesize: kiểm chứng mermaid/table/chart, gỡ số liệu không có căn cứ,
dịch đoạn lẫn tiếng Việt và bổ sung biểu đồ từ Quantitative Evidence Ledger khi bài chưa có hình số liệu."""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict

from app.agent.evidence.figure_policy import refine_chart_spec
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


_MERMAID_TD_RE = re.compile(r"^(\s*(?:graph|flowchart)\s+)(?:TD|TB)\b", re.M)
_MERMAID_EDGE_RE = re.compile(r"([A-Za-z][\w-]*)(?:\s*(?:\[[^\]\n]*\]|\([^)\n]*\)|\{[^}\n]*\}))?\s*-[-.=]*>(?:\|[^|\n]*\|)?\s*([A-Za-z][\w-]*)")
MAX_TD_LEVEL_WIDTH = 6  # quá số nút cùng tầng này thì sơ đồ dọc thành một dải ngang chữ li ti


def orient_mermaid(code: str) -> str:
    """Cây TD/TB có tầng rộng (taxonomy 6 trục × vài lá = 30+ nút một hàng) → LR: các lá xếp dọc, chữ đọc được trong trang."""
    if not _MERMAID_TD_RE.search(code):
        return code
    children: dict[str, list[str]] = {}
    targets: set[str] = set()
    for a, b in _MERMAID_EDGE_RE.findall(code):
        children.setdefault(a, []).append(b)
        targets.add(b)
    roots = [n for n in children if n not in targets] or list(children)[:1]
    level, seen, widest = roots, set(roots), len(roots)
    while level:
        level = [c for n in level for c in children.get(n, []) if c not in seen]
        seen.update(level)
        widest = max(widest, len(level))
    if widest <= MAX_TD_LEVEL_WIDTH:
        return code
    compact = _compact_taxonomy(code, children, roots)
    if compact:
        logger.info("Gộp lá của cây taxonomy thành danh sách mỗi trục (tầng rộng nhất %d nút)", widest)
        return compact
    logger.info("Đổi sơ đồ mermaid TD → LR: tầng rộng nhất %d nút", widest)
    return _MERMAID_TD_RE.sub(r"\1LR", code, count=1)


_MERMAID_LABEL_RE = re.compile(r"([A-Za-z][\w-]*)\s*\[\s*\"([^\"\n]*)\"\s*\]")
MAX_COMPACT_LEAVES = 12  # cây gốc→trục→lá có nhiều lá hơn: mỗi ô lá tốn khung + khoảng cách → co cả hình thành chữ li ti


def _compact_taxonomy(code: str, children: dict[str, list[str]], roots: list[str]) -> str | None:
    """Cây đúng 3 tầng (gốc → trục → lá) nhiều lá → LR với MỘT ô danh sách lá mỗi trục (giữ nguyên nhãn và trích dẫn [n]).

    Không phải dạng đó (lá có con, nút nhiều cha, thiếu nhãn) → None, giữ sơ đồ của tác giả."""
    if len(roots) != 1:
        return None
    labels = dict(_MERMAID_LABEL_RE.findall(code))
    root = roots[0]
    axes = children.get(root, [])
    parents: dict[str, int] = {}
    for kids in children.values():
        for k in kids:
            parents[k] = parents.get(k, 0) + 1
    leaves = [leaf for a in axes for leaf in children.get(a, [])]
    if len(leaves) <= MAX_COMPACT_LEAVES or any(parents.get(n, 0) != 1 for n in axes + leaves):
        return None
    if any(children.get(leaf) for leaf in leaves) or any(n not in labels for n in [root, *axes, *leaves]):
        return None
    out = ["graph LR", f'    {root}["{labels[root]}"]']
    for i, a in enumerate(axes):
        out.append(f'    {root} --> {a}["{labels[a]}"]')
        items = [re.sub(r"\s*<br\s*/?>\s*", " ", labels[leaf]).strip() for leaf in children.get(a, [])]
        if items:
            out.append(f'    {a} --> L{i}["' + "<br/>".join(f"• {t}" for t in items) + '"]')
    return "\n".join(out)


def fix_mermaid_block(code: str, gateway: LLMGateway | None, model_name: str | None, retries: int = 2) -> str | None:
    """Trả về sơ đồ hợp lệ (đã sửa nếu cần) hoặc None khi không cứu được."""
    from app.agent.format_sanitizer import sanitize_mermaid_block

    current = sanitize_mermaid_block(code)
    for attempt in range(retries + 1):
        errors = validate_mermaid(current)
        if not errors:
            return orient_mermaid(current)
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


def _apply_chart_policy(body: str | None) -> str | None:
    """Chart Selection Policy: đổi loại hình theo câu hỏi dữ liệu trả lời (chỉ đổi cách vẽ, giữ nguyên số)."""
    if body is None:
        return None
    try:
        spec = json.loads(body)
    except ValueError:
        return body
    if not isinstance(spec, dict):
        return body
    refined, reason = refine_chart_spec(spec)
    if reason is None:
        return body
    logger.info("Đổi biểu đồ '%s' từ %s sang %s: %s", str(spec.get("caption", ""))[:60], spec.get("type", "bar"), refined["type"], reason)
    return json.dumps(refined, ensure_ascii=False)


_EDITION_RE = re.compile(r"\b([A-Z][A-Za-z0-9-]{1,30})[\s-]+((?:19|20)\d{2})\b")
_SPLIT_WORDS = {
    "test": r"\b(?:hidden\s+)?test(?:ing)?\s+(?:set|split)\b|\bhidden\s+test\b|\btest\b",
    "validation": r"\bvalidation\b|\bval\b",
    "cv": r"\bcross[- ]validation\b|\b\d+[- ]fold\b|\bCV\b",
    "train": r"\btrain(?:ing)?\s+(?:set|split)\b",
}
_PERCENT_RE = re.compile(r"%|\bpercent(?:age)?\b|\bpct\b", re.I)
_RATIO_RE = re.compile(r"\bratio\b|\b0\s*[–-]\s*1\b|\brat\b", re.I)
# Các loại hình so sánh trực tiếp trên MỘT trục; dumbbell được phép ghép đúng 2 điều kiện (val vs test…), heatmap/xy theo cấu hình
_COMPARATIVE_TYPES = {"bar", "barh", "dot", "line", "stacked_bar", "stacked_barh", "scatter"}
MIN_SCATTER_POINTS = 4


def mixed_protocol_reason(spec: dict) -> str | None:
    """Lý do chart so sánh đặt kết quả của các protocol khác nhau trên cùng một trục (None = không phát hiện).

    Tất định, không theo lĩnh vực: ≥2 phiên bản của cùng tên dataset ('X 2020' và 'X 2021'), ≥2 loại split
    (test/validation/CV) hoặc lẫn % với tỉ lệ 0–1 trong caption/nhãn/tên series/trục.
    """
    kind = spec.get("type", "bar")
    if kind not in _COMPARATIVE_TYPES:
        return None
    parts = [spec.get("caption"), spec.get("title"), spec.get("x_label"), spec.get("y_label"), *(spec.get("labels") or [])]
    parts += [s.get("name") for s in spec.get("series") or [] if isinstance(s, dict)]
    text = " ".join(str(p) for p in parts if p)
    editions: dict[str, set[str]] = {}
    for name, year in _EDITION_RE.findall(text):
        editions.setdefault(name.lower(), set()).add(year)
    multi = {n: sorted(y) for n, y in editions.items() if len(y) > 1}
    if multi:
        name, years = next(iter(multi.items()))
        return f"trộn nhiều phiên bản dataset {name} {years} trong một panel"
    splits = sorted(k for k, pat in _SPLIT_WORDS.items() if re.search(pat, text, re.I))
    if len(splits) > 1:
        return f"trộn nhiều split {splits} trong một panel"
    if _PERCENT_RE.search(text) and _RATIO_RE.search(text):
        return "trộn đơn vị % và tỉ lệ 0–1 trong một panel"
    return None


def scrub_chart_spec(body: str, draft: str) -> str | None:
    """Giữ biểu đồ nếu có ít nhất 2 giá trị có thật trong draft; giá trị không có căn cứ bị bỏ (null/loại điểm).

    Hỗ trợ mọi type mà renderer vẽ được: bar/barh/line/stacked_barh (labels + values), xyline/scatter (x, y),
    histogram/boxplot/cdf (samples), heatmap (matrix). Trục x của xyline/scatter (epoch, tham số…) không cần căn cứ.
    """
    try:
        spec = json.loads(body)
    except ValueError:
        return None
    if not isinstance(spec, dict):
        return None
    known = _draft_numbers(draft)

    def grounded(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) in known

    kind = spec.get("type", "bar")
    real = 0
    if kind == "evidence_map":  # ô Yes/No chỉ tin khi dựng từ câu nguyên văn (derived), không tin LLM
        return None
    if kind == "panels":  # kiểm từng ô con như một chart độc lập; ô không đủ căn cứ bị bỏ
        panels = spec.get("panels")
        if not isinstance(panels, list):
            return None
        kept_panels = [json.loads(b) for p in panels if isinstance(p, dict) and (b := scrub_chart_spec(json.dumps(p), draft))]
        if not kept_panels:
            return None
        return json.dumps({**spec, "panels": kept_panels}, ensure_ascii=False)
    if kind == "heatmap":
        matrix = spec.get("matrix")
        if not isinstance(matrix, list) or not all(isinstance(r, list) for r in matrix):
            return None
        spec["matrix"] = [[v if grounded(v) else None for v in row] for row in matrix]
        real = sum(v is not None for row in spec["matrix"] for v in row)
    else:
        series = spec.get("series")
        if not isinstance(series, list):
            return None
        kept = []
        for s in series:
            if not isinstance(s, dict):
                continue
            if kind in ("xyline", "scatter"):
                pts = [(x, y) for x, y in zip(s.get("x", []), s.get("y", []), strict=False) if grounded(y)]
                if pts:
                    kept.append({**s, "x": [x for x, _ in pts], "y": [y for _, y in pts]})
                    kept[-1].pop("errors", None)  # error bar không còn khớp sau khi bỏ điểm
                    real += len(pts)
            elif kind in ("histogram", "boxplot", "cdf"):
                samples = [v for v in s.get("samples", []) if grounded(v)]
                if samples:
                    kept.append({**s, "samples": samples})
                    real += len(samples)
            else:
                labels = spec.get("labels")
                vals = s.get("values", [])
                if not isinstance(labels, list) or len(vals) != len(labels):
                    continue
                vals = [v if grounded(v) else None for v in vals]
                real += sum(v is not None for v in vals)
                kept.append({**s, "values": vals})
        if not kept:
            return None
        spec["series"] = kept
    if real < 2:
        return None
    if kind == "scatter" and real < MIN_SCATTER_POINTS:  # vài điểm không thể hiện được quan hệ/đường biên đánh đổi
        logger.warning("Bỏ scatter '%s': chỉ %d điểm có căn cứ (< %d)", str(spec.get("caption", ""))[:60], real, MIN_SCATTER_POINTS)
        return None
    return json.dumps(spec, ensure_ascii=False)


_REF_YEAR_RE = re.compile(r"^\[(\d+)\].*?[,\s]((?:19|20)\d{2})[a-z]?\.?\s*$")
_LABEL_CITE_RE = re.compile(r"\[(\d+)\]")
MIN_TIMELINE_EVENTS = 4


def reference_years(references: list[str]) -> dict[int, int]:
    """'[3] A et al., "T," *Venue*, 2024.' → {3: 2024}; mục không có năm ở cuối thì bỏ (không đoán)."""
    out: dict[int, int] = {}
    for ref in references:
        m = _REF_YEAR_RE.match(ref.strip())
        if m:
            out[int(m.group(1))] = int(m.group(2))
    return out


def scrub_timeline_spec(body: str, years: dict[int, int] | None) -> str | None:
    """Giữ mốc có đúng MỘT trích dẫn [n] và năm trùng năm của reference [n]; LLM không được tự đặt năm."""
    try:
        spec = json.loads(body)
    except ValueError:
        return None
    if not isinstance(spec, dict) or not years:
        return None
    kept = []
    for e in spec.get("events") or []:
        if not isinstance(e, dict):
            continue
        cites = _LABEL_CITE_RE.findall(str(e.get("label") or ""))
        try:
            ok = len(cites) == 1 and years.get(int(cites[0])) == int(e.get("year"))
        except (TypeError, ValueError):
            ok = False
        if ok:
            kept.append(e)
        else:
            logger.warning("Bỏ mốc timeline không khớp năm của reference: %s", e)
    if len(kept) < MIN_TIMELINE_EVENTS or len({e["year"] for e in kept}) < 2:
        return None
    return json.dumps({**spec, "events": kept}, ensure_ascii=False)


def reject_mixed_protocol(body: str | None) -> str | None:
    """Chạy SAU Chart Selection Policy (cặp val/test đã thành dumbbell): bỏ chart/ô con trộn protocol trên một trục."""
    if body is None:
        return None
    try:
        spec = json.loads(body)
    except ValueError:
        return body
    if not isinstance(spec, dict):
        return body
    if spec.get("type") == "panels":
        panels = [p for p in spec.get("panels") or [] if isinstance(p, dict) and not mixed_protocol_reason(p)]
        return json.dumps({**spec, "panels": panels}, ensure_ascii=False) if panels else None
    reason = mixed_protocol_reason(spec)
    if reason:
        logger.warning("Bỏ chart '%s': %s", str(spec.get("caption", ""))[:80], reason)
        return None
    return body


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


def _ledger_groups(draft: str) -> dict[tuple[str, str], dict[str, tuple[float, str]]]:
    """(metric, dataset) -> {method: (giá trị, nguồn)}; chỉ giá trị số thật, lấy giá trị đầu tiên của mỗi phương pháp."""
    groups: dict[tuple[str, str], dict[str, tuple[float, str]]] = defaultdict(dict)
    for r in _ledger_rows(draft):
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*%?\s*", _CITE_RE.sub("", r["value"]))
        if not m or not r["method"] or r["method"].lower().startswith("no quantitative"):
            continue
        groups[(r["metric"], r["dataset"])].setdefault(r["method"], (float(m.group(1)), r["source"]))
    return groups


def _complete_matrix(groups: dict) -> tuple[str, str, list[str], list[str], list[list[float]], str] | None:
    """Tìm (họ metric, dataset) có ≥2 metric cùng họ (vd Dice WT/TC/ET) và ≥3 phương pháp có đủ mọi metric."""
    best = None
    by_key: dict[tuple[str, str], list[str]] = defaultdict(list)
    for metric, dataset in groups:
        by_key[((metric.split() or [""])[0].lower(), dataset)].append(metric)
    for (family, dataset), metrics in by_key.items():
        if len(metrics) < 2:
            continue
        methods = [m for m in groups[(metrics[0], dataset)] if all(m in groups[(x, dataset)] for x in metrics)]
        if len(methods) >= 3 and (best is None or len(methods) * len(metrics) > len(best[3]) * len(best[2])):
            matrix = [[groups[(x, dataset)][m][0] for x in metrics] for m in methods]
            cites = ", ".join(sorted({groups[(x, dataset)][m][1] for x in metrics for m in methods if groups[(x, dataset)][m][1]}))
            best = (family, dataset, metrics, methods, matrix, cites)
    return best


def build_ledger_charts(draft: str, limit: int = 1) -> list[str]:
    """Dựng tối đa `limit` khối ```chart ưu tiên KHÁC LOẠI: dot (xếp hạng một metric), heatmap (phương pháp × vùng/metric).

    Mỗi bộ số chỉ vẽ một lần (không vẽ lại ma trận bằng biểu đồ cột) — Chart Selection Policy.

    Chỉ dùng số có thật trong ledger, mỗi biểu đồ cùng dataset và cùng họ metric."""
    groups = _ledger_groups(draft)
    ranked = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    out: list[str] = []
    matrix = _complete_matrix(groups)
    if ranked and len(ranked[0][1]) >= 3:
        (metric, dataset), items = ranked[0]
        entries = sorted(items.items(), key=lambda kv: -kv[1][0])[:8]
        cites = ", ".join(sorted({e[1][1] for e in entries if e[1][1]}))
        out.append(json.dumps({
            "type": "dot", "caption": f"Reported {metric} on {dataset} {cites}".strip(),
            "labels": [e[0][:40] for e in entries], "series": [{"name": metric, "values": [e[1][0] for e in entries]}],
        }, ensure_ascii=False))
    if matrix:
        family, dataset, metrics, methods, values, cites = matrix
        labels = [m[:40] for m in methods]
        out.append(json.dumps({
            "type": "heatmap", "caption": f"Heatmap of reported {family} on {dataset} (methods x metrics) {cites}".strip(),
            "x_labels": metrics, "y_labels": labels, "matrix": values, "c_label": family,
        }, ensure_ascii=False))
    for (metric, dataset), items in ranked[1:]:  # bù cùng loại dot nếu vẫn thiếu
        if len(out) >= limit:
            break
        if len(items) >= 3:
            entries = sorted(items.items(), key=lambda kv: -kv[1][0])[:8]
            cites = ", ".join(sorted({e[1][1] for e in entries if e[1][1]}))
            out.append(json.dumps({
                "type": "dot", "caption": f"Reported {metric} on {dataset} {cites}".strip(),
                "labels": [e[0][:40] for e in entries], "series": [{"name": metric, "values": [e[1][0] for e in entries]}],
            }, ensure_ascii=False))
    return out[:limit]


def build_ledger_chart(draft: str) -> str | None:
    """Chart tốt nhất từ ledger (nhóm có nhiều phương pháp nhất), hoặc None."""
    charts = build_ledger_charts(draft, 1)
    return charts[0] if charts else None


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
        if len(a) == len(b) and all(x.count("|") == y.count("|") for x, y in zip(a, b, strict=True)):
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
                new = (_translate_mermaid if kind == "mermaid" else lambda b, *a, kind=kind: _translate_json_block(kind, b, *a))(inner, target, gateway, model_name)
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
    min_charts: int = 1,
    ref_years: dict[int, int] | None = None,
) -> str:
    """Kiểm chứng/sửa mọi khối mermaid, table, chart, image; dịch đoạn lẫn Việt; chèn biểu đồ ledger nếu thiếu.

    `ref_years` ({n: năm} của References đã đánh số lại) để kiểm năm của khối timeline; None → bỏ timeline do LLM viết."""
    used_figures: set[str] = set()

    def _fix(m: re.Match) -> str:
        kind, body = m.group(1), m.group(2)
        if kind == "mermaid":
            fixed = fix_mermaid_block(body, gateway, model_name)
        elif kind == "table":
            fixed = body if '"derived": true' in body else scrub_table_spec(body, draft)  # số suy ra không có trong PDF
        elif kind == "image":
            fixed = scrub_image_spec(body, figures)
            if fixed is not None:
                ref = json.loads(fixed)["ref"]
                if ref in used_figures:
                    logger.warning("Bỏ khối image trùng ref=%s", ref)
                    fixed = None
                used_figures.add(ref)
        elif re.search(r'"type"\s*:\s*"timeline"', body):
            fixed = scrub_timeline_spec(body, ref_years)
        else:
            fixed = body if '"derived": true' in body else scrub_chart_spec(body, draft)  # số suy ra từ record đã kiểm chứng
            fixed = _apply_chart_policy(fixed)
            if '"derived": true' not in body:
                fixed = reject_mixed_protocol(fixed)
        if fixed is None:
            logger.warning("Dropped invalid %s block from report", kind)
            return ""
        return f"```{kind}\n{fixed.strip()}\n```"

    report = _FENCE_RE.sub(_fix, report)
    report = translate_foreign_paragraphs(report, language, gateway, model_name)
    report, dropped = drop_ungrounded_claims(report, draft, evidence_text)
    for sent in dropped:
        logger.warning("Gỡ câu có số liệu không có trong evidence: %s", sent[:160])

    types = []
    for m in re.finditer(r"```chart\n(.*?)```", report, re.DOTALL):
        try:
            types.append(str(json.loads(m.group(1)).get("type", "bar")))
        except (ValueError, AttributeError):
            continue
    if len(set(types)) < min_charts:
        marker = re.search(r"^## 5\.", report, re.MULTILINE)
        extra = []
        for c in build_ledger_charts(draft, 10):
            t = json.loads(c)["type"]
            if t not in types and len(set(types)) < min_charts:
                types.append(t)
                extra.append(c)
        if extra and marker:
            block = "".join(f"```chart\n{c}\n```\n\n" for c in extra)
            report = report[: marker.start()] + block + report[marker.start():]
        if len(set(types)) < min_charts:
            logger.warning("Chỉ có %d/%d LOẠI biểu đồ khác nhau: ledger không đủ dữ liệu cùng setting (không bịa số)", len(set(types)), min_charts)
    return re.sub(r"\n{3,}", "\n\n", report)
