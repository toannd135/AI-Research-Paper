"""Render report Markdown → HTML dàn trang bài báo → PDF (Chromium headless qua Playwright).

- Bảng Markdown → bảng 3 đường kẻ (booktabs), đánh số "Table n".
- Khối ```chart {json}``` → biểu đồ matplotlib (SVG), đánh số "Figure n".
- Khối ```mermaid``` → sơ đồ do mermaid.js render trong Chromium, đánh số "Figure n".
- Công thức $$...$$ và \\(...\\) → KaTeX.
"""

import html
import io
import json
import re

import markdown

_FENCE_RE = re.compile(r"```(mermaid|chart|table)[ \t]*\n(.*?)```", re.DOTALL)
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)")
# $...$ (không dính tiền tệ như "$5 to $10": sau $ mở không có khoảng trắng, trước $ đóng không có khoảng trắng)
_DOLLAR_MATH_RE = re.compile(r"(?<![\\$\w])\$(?![\s$])([^$\n]+?)(?<![\s\\])\$(?![\w$])")
_PLACEHOLDER_RE = re.compile(r"(?:<p>)?\s*PAPERAIBLOCK(\d+)END\s*(?:</p>)?")

_PALETTE = ["#1f4e79", "#c55a11", "#548235", "#7f6000", "#7030a0", "#2e75b6"]
# Thanh xếp chồng kiểu "thắng / hoà / thua": xanh lá, xanh nhạt, đỏ nhạt
_STACK_PALETTE = ["#6fdc6f", "#cfe2f7", "#f38b8b", "#f6d28b", "#c7b3e6", "#b8b8b8"]


def _num(v) -> float | None:
    """Ép giá trị về số; null / "" / "–" / chữ → None (không vẽ)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace("%", "").replace(",", "").strip())
    except ValueError:
        return None


def _render_chart_svg(spec: dict) -> str:
    """Vẽ biểu đồ theo spec JSON.

    {type: bar | barh | line | stacked_barh | stacked_bar, labels, series: [{name, values}], x_label, y_label}
    - values thiếu số liệu ghi null; nhãn nào không có giá trị ở mọi series thì bị bỏ.
    """
    import textwrap

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw_labels = [str(x) for x in spec["labels"]]
    series = [
        {"name": s.get("name"), "values": [_num(v) for v in s["values"]]}
        for s in spec["series"]
        if len(s.get("values", [])) == len(raw_labels)
    ]
    keep_idx = [i for i in range(len(raw_labels)) if any(s["values"][i] is not None for s in series)]
    if not keep_idx or not series:
        raise ValueError("chart spec thiếu labels/series hợp lệ")
    kind = spec.get("type", "bar")
    horizontal = kind in ("barh", "stacked_barh")
    stacked = kind.startswith("stacked")
    labels = [textwrap.fill(raw_labels[i], 26 if horizontal else 16) for i in keep_idx]
    for s in series:
        s["values"] = [s["values"][i] for i in keep_idx]
    n, m = len(series), len(labels)

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "path"})
    if horizontal:
        per_bar = 0.55 if stacked else 0.32 * n + 0.2
        fig, ax = plt.subplots(figsize=(6.6, max(2.2, per_bar * m + 1.0)))
    else:
        fig, ax = plt.subplots(figsize=(6.6, 3.4))
    pos = list(range(m))

    if kind == "line":
        for i, s in enumerate(series):
            ys = [float("nan") if v is None else v for v in s["values"]]
            ax.plot(labels, ys, marker="o", linewidth=1.6, color=_PALETTE[i % len(_PALETTE)], label=s["name"])
            for x, y in zip(labels, ys):
                if y == y:
                    ax.annotate(f"{y:g}", (x, y), textcoords="offset points", xytext=(0, 5), ha="center", fontsize=7)
    elif stacked:
        left = [0.0] * m
        for i, s in enumerate(series):
            vals = [v or 0.0 for v in s["values"]]
            color = _STACK_PALETTE[i % len(_STACK_PALETTE)]
            draw = ax.barh if horizontal else ax.bar
            kw = {"left": left, "height": 0.6} if horizontal else {"bottom": left, "width": 0.6}
            bars = draw(pos, vals, color=color, label=s["name"], edgecolor="white", linewidth=0.6, **kw)
            ax.bar_label(bars, labels=[f"{v:g}" if v else "" for v in vals], label_type="center", fontsize=8)
            left = [a + b for a, b in zip(left, vals)]
        ax.margins(x=0.0 if horizontal else 0.05, y=0.05 if horizontal else 0.0)
    else:
        width = 0.8 / n
        for i, s in enumerate(series):
            offset = [p - 0.4 + width * (i + 0.5) for p in pos]
            vals = [float("nan") if v is None else v for v in s["values"]]
            color = _PALETTE[i % len(_PALETTE)]
            if horizontal:
                bars = ax.barh(offset, vals, height=width * 0.9, color=color, label=s["name"])
            else:
                bars = ax.bar(offset, vals, width=width * 0.9, color=color, label=s["name"])
            ax.bar_label(bars, labels=["" if v != v else f"{v:g}" for v in vals], fontsize=7, padding=3)
        # chừa chỗ cho nhãn số ở cả hai đầu (kể cả giá trị âm) để không đè lên tên trục
        values = [v for s in series for v in s["values"] if v is not None]
        lo, hi = min(0.0, *values), max(0.0, *values)
        pad = (hi - lo) * 0.14 or 1.0
        (ax.set_xlim if horizontal else ax.set_ylim)(lo - (pad if lo < 0 else 0), hi + pad)
        if lo < 0:
            (ax.axvline if horizontal else ax.axhline)(0, color="#333", linewidth=0.8)

    if horizontal:
        ax.set_yticks(pos, labels)
        ax.invert_yaxis()
    elif kind != "line":
        long = max(map(len, raw_labels)) > 12
        ax.set_xticks(pos, labels, rotation=0, ha="center")
        if long and m > 5:
            ax.tick_params(axis="x", labelsize=7.5)

    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"])
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"])
    ax.spines[["top", "right"]].set_visible(False)
    if stacked and horizontal:
        ax.spines[["bottom"]].set_visible(False)
        ax.set_xticks([])
    else:
        ax.grid(axis="x" if horizontal else "y", linestyle=":", alpha=0.6)
        ax.set_axisbelow(True)
    if n > 1:
        # chú giải đặt phía trên khung, không đè lên dữ liệu
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=min(n, 4), frameon=True, fontsize=8, edgecolor="#bbb")
    fig.tight_layout()

    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index("<svg") :]


def _cell_html(text) -> str:
    """Escape ô bảng, cho phép **đậm** và *nghiêng* kiểu Markdown."""
    t = html.escape(str(text))
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    return re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", t)


def _render_table_html(spec: dict) -> str:
    """Dựng bảng học thuật từ spec JSON.

    {caption, header_groups?: [{label, span}], columns: [...], rows: [[...]], bold_rows?: [index]}
    - header_groups: dòng tiêu đề nhóm phía trên (label rỗng = cột cố định), tổng span = số cột.
    - Ô cột đầu để "" nghĩa là gộp (rowspan) với ô phía trên; hàng bắt đầu nhóm mới có đường kẻ ngang mảnh.
    - Ô có thể chứa **đậm**; bold_rows in đậm cả hàng.
    - highlight_best: "max" | "min" cho mọi cột số, hoặc {"Tên cột": "max" | "min"} → tô nền xanh ô tốt nhất mỗi cột.
    """
    columns = [str(c) for c in spec["columns"]]
    rows = [[("" if c is None else c) for c in r] for r in spec["rows"]]
    n = len(columns)
    rows = [r for r in rows if len(r) == n]
    if not rows:
        raise ValueError("table spec không có hàng hợp lệ")
    bold_rows = set(spec.get("bold_rows", []))

    vsep: set[int] = set()  # chỉ số cột có đường kẻ dọc bên trái
    head = ""
    groups = spec.get("header_groups")
    if groups and sum(int(g["span"]) for g in groups) == n:
        idx, labeled = 0, 0
        cells = []
        for g in groups:
            span = int(g["span"])
            if g.get("label"):
                labeled += 1
                if labeled > 1:
                    vsep.add(idx)
                cells.append(f'<th colspan="{span}" class="grp{" vs" if idx in vsep else ""}"><span>{_cell_html(g["label"])}</span></th>')
            else:
                cells.append(f'<th colspan="{span}"></th>')
            idx += span
        head += f"<tr>{''.join(cells)}</tr>"
    head += "<tr>" + "".join(f'<th class="{"vs" if i in vsep else ""}">{_cell_html(c)}</th>' for i, c in enumerate(columns)) + "</tr>"

    best: dict[int, set[int]] = {}  # cột → các hàng có giá trị tốt nhất
    rule = spec.get("highlight_best")
    if rule:
        for i in range(1, n):
            direction = rule if isinstance(rule, str) else rule.get(columns[i]) if isinstance(rule, dict) else None
            if direction not in ("max", "min"):
                continue
            vals = {r: _num(str(row[i]).replace("*", "")) for r, row in enumerate(rows)}
            vals = {r: v for r, v in vals.items() if v is not None}
            if len(vals) >= 2:
                target = (max if direction == "max" else min)(vals.values())
                best[i] = {r for r, v in vals.items() if v == target}

    body = []
    for r, row in enumerate(rows):
        tds = []
        if str(row[0]).strip():
            span = 1
            while r + span < len(rows) and not str(rows[r + span][0]).strip():
                span += 1
            # ô gộp nhiều hàng = tên nhóm (căn giữa, small-caps); ô đơn = tên phương pháp bình thường
            lead_cls = "lead" if span > 1 else ("bd" if r in bold_rows else "")
            tds.append(f'<td rowspan="{span}" class="{lead_cls}">{_cell_html(row[0])}</td>')
        cls_row = "start" if str(row[0]).strip() and r > 0 else ""
        for i in range(1, n):
            cls = ("vs " if i in vsep else "") + ("num" if re.fullmatch(r"[\d.,%±+\-– ]+", str(row[i]).replace("*", "").strip()) else "")
            raw = str(row[i]).strip()
            whole_bold = r in bold_rows or (raw.startswith("**") and raw.endswith("**") and raw.count("**") == 2)
            text = _cell_html(raw[2:-2] if raw.startswith("**") and raw.endswith("**") and raw.count("**") == 2 else raw)
            cls += (" bd" if whole_bold else "") + (" best" if r in best.get(i, ()) else "")
            tds.append(f'<td class="{cls.strip()}">{text}</td>')
        body.append(f'<tr class="{cls_row}">{"".join(tds)}</tr>')
    return f'<table class="spec"><thead>{head}</thead><tbody>{"".join(body)}</tbody></table>'


def _extract_blocks(md: str) -> tuple[str, list[str]]:
    """Thay khối mermaid/chart/công thức bằng placeholder để Markdown không làm hỏng nội dung."""
    blocks: list[str] = []

    def keep(fragment: str, block: bool = True) -> str:
        blocks.append(fragment)
        idx = len(blocks) - 1
        return f"\n\nPAPERAIBLOCK{idx}END\n\n" if block else f"PAPERAIINLINE{idx}END"

    def fence(match: re.Match) -> str:
        kind, body = match.group(1), match.group(2).strip()
        if kind == "mermaid":
            return keep(f'<figure class="fig" data-kind="figure"><pre class="mermaid">{html.escape(body)}</pre>__CAPTION__</figure>')
        if kind == "table":
            try:
                spec = json.loads(body)
                table = _render_table_html(spec)
            except Exception:
                return ""
            caption = html.escape(spec.get("caption") or "")
            return keep(table.replace('<table class="spec"', f'<table class="spec" data-caption="{caption}"', 1))
        try:
            spec = json.loads(body)
            svg = _render_chart_svg(spec)
        except Exception:
            return ""  # spec hỏng thì bỏ biểu đồ, không làm hỏng cả bài
        caption = html.escape(spec.get("caption") or spec.get("title") or "")
        return keep(f'<figure class="fig chart" data-kind="figure" data-caption="{caption}">{svg}__CAPTION__</figure>')

    md = _FENCE_RE.sub(fence, md)
    md = _DISPLAY_MATH_RE.sub(lambda m: keep(f'<div class="math">\\[{html.escape(m.group(1).strip())}\\]</div>'), md)
    md = _INLINE_MATH_RE.sub(lambda m: keep(f"\\({html.escape(m.group(1))}\\)", block=False), md)
    md = _DOLLAR_MATH_RE.sub(lambda m: keep(f"\\({html.escape(m.group(1))}\\)", block=False), md)
    return md, blocks


def _number_figures_and_tables(body: str) -> str:
    """Đánh số Table/Figure theo thứ tự xuất hiện; caption mặc định = tiêu đề mục gần nhất."""
    counters = {"table": 0, "figure": 0}
    last_heading = ""
    out: list[str] = []
    # LLM hay tự viết "**Table 1: ...**" ngay trên bảng → dùng làm caption thay vì lặp lại.
    body = re.sub(
        r"<p>(?:<(?:strong|em)>)*Table\s*\d+\s*[:.]\s*(.*?)(?:</(?:strong|em)>)*</p>\s*<table>",
        lambda m: f'<table data-caption="{html.escape(html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip()))}">',
        body,
        flags=re.DOTALL,
    )
    token_re = re.compile(r"<h[2-4][^>]*>(.*?)</h[2-4]>|<table[^>]*>|<figure[^>]*>", re.DOTALL)
    pos = 0
    for m in token_re.finditer(body):
        out.append(body[pos : m.start()])
        tag = m.group(0)
        if m.group(1) is not None:
            last_heading = re.sub(r"<[^>]+>|^[\d.]+\s*", "", m.group(1)).strip()
            out.append(tag)
        elif tag.startswith("<table"):
            counters["table"] += 1
            cap = re.search(r'data-caption="([^"]*)"', tag)
            text = (cap.group(1) if cap else "") or last_heading
            out.append(f'<div class="tbl"><div class="caption"><b>Table {counters["table"]}.</b> {text}</div>{tag}')
        else:
            counters["figure"] += 1
            cap = re.search(r'data-caption="([^"]*)"', tag)
            text = (cap.group(1) if cap and cap.group(1) else "") or last_heading
            out.append(tag)
            # caption đặt ở cuối figure (thay __CAPTION__ ngay sau)
            end = body.index("__CAPTION__", m.end())
            out.append(body[m.end() : end])
            out.append(f'<figcaption><b>Figure {counters["figure"]}.</b> {text}</figcaption>')
            pos = end + len("__CAPTION__")
            continue
        pos = m.end()
    out.append(body[pos:])
    return re.sub(r"</table>(?!</div>)", "</table></div>", "".join(out))


def _layout_front_matter(body: str) -> str:
    """Tách tiêu đề, dòng tác giả, abstract thành khối đầu bài kiểu tạp chí."""
    body = re.sub(r"<h1>(.*?)</h1>", r'<h1 class="title">\1</h1>', body, count=1, flags=re.DOTALL)
    body = re.sub(
        r"<p><strong>Authors:</strong>(.*?)\|\s*<strong>Affiliations:</strong>(.*?)</p>",
        r'<div class="authors">\1</div><div class="affil">\2</div>',
        body,
        count=1,
        flags=re.DOTALL,
    )
    body = re.sub(
        r"<h2>Abstract</h2>(.*?)(?=<h2)",
        r'<section class="abstract"><h2>Abstract</h2>\1</section>',
        body,
        count=1,
        flags=re.DOTALL,
    )
    return re.sub(r"<h2>References</h2>(.*)$", r'<section class="refs"><h2>References</h2>\1</section>', body, flags=re.DOTALL)


def report_to_html(report_md: str) -> str:
    md, blocks = _extract_blocks(report_md)
    parser = markdown.Markdown(extensions=["tables", "fenced_code", "sane_lists"])
    # LLM hay thụt lề đoạn văn sau công thức → Markdown hiểu nhầm là khối code. Code thật dùng ``` nên tắt indented code.
    parser.parser.blockprocessors.deregister("code")
    body = parser.convert(md)
    body = _PLACEHOLDER_RE.sub(lambda m: blocks[int(m.group(1))], body)
    body = re.sub(r"PAPERAIINLINE(\d+)END", lambda m: blocks[int(m.group(1))], body)
    body = _layout_front_matter(_number_figures_and_tables(body))
    return _TEMPLATE.replace("{{BODY}}", body)


def report_to_pdf(report_md: str) -> bytes:
    from playwright.sync_api import sync_playwright

    page_html = report_to_html(report_md)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(page_html, wait_until="networkidle", timeout=60_000)
            page.evaluate(
                """async () => {
                    if (window.mermaid) {
                        mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'loose',
                                             flowchart: { htmlLabels: true, useMaxWidth: true } });
                        await mermaid.run({ suppressErrors: true });
                    }
                    if (window.renderMathInElement) {
                        renderMathInElement(document.body, { delimiters: [
                            { left: '\\\\[', right: '\\\\]', display: true },
                            { left: '\\\\(', right: '\\\\)', display: false } ], throwOnError: false });
                    }
                    await document.fonts.ready;
                }"""
            )
            return page.pdf(
                format="A4",
                margin={"top": "20mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
                print_background=True,
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=(
                    '<div style="width:100%;text-align:center;font-size:8px;color:#666;font-family:serif">'
                    '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'
                ),
            )
        finally:
            browser.close()


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif:ital,wght@0,400;0,700;1,400&family=Noto+Sans:wght@400;600;700&display=swap">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  @page { size: A4; }
  body { font-family: 'Noto Serif', 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.5; color: #111; margin: 0; }
  h1.title { font-size: 19pt; line-height: 1.25; text-align: center; margin: 0 0 10pt; }
  .authors { text-align: center; font-size: 11pt; font-weight: 700; }
  .affil { text-align: center; font-size: 9.5pt; font-style: italic; color: #333; margin-bottom: 14pt; }
  .abstract { border-top: 1.2pt solid #111; border-bottom: 1.2pt solid #111; padding: 6pt 0 8pt; margin-bottom: 14pt; font-size: 9.5pt; }
  .abstract h2 { font-size: 10.5pt; text-transform: uppercase; letter-spacing: .06em; margin: 2pt 0 4pt; border: 0; }
  h2 { font-size: 13pt; margin: 16pt 0 6pt; break-after: avoid; }
  h3 { font-size: 11pt; margin: 12pt 0 4pt; break-after: avoid; }
  h4 { font-size: 10.5pt; font-style: italic; margin: 10pt 0 4pt; break-after: avoid; }
  p, li { text-align: justify; hyphens: auto; }
  p { margin: 0 0 6pt; }
  ul, ol { margin: 0 0 6pt; padding-left: 18pt; }
  .tbl { margin: 10pt 0 12pt; break-inside: avoid; }
  .caption, figcaption { font-family: 'Noto Sans', sans-serif; font-size: 8.5pt; text-align: center; margin: 4pt 0; }
  table { width: 100%; border-collapse: collapse; font-family: 'Noto Sans', sans-serif; font-size: 7.5pt; line-height: 1.35;
          border-top: 1.2pt solid #111; border-bottom: 1.2pt solid #111; }
  thead th { border-bottom: .6pt solid #111; text-align: left; padding: 4pt 4pt; vertical-align: bottom; }
  td { padding: 3pt 4pt; vertical-align: top; text-align: left; }
  tbody tr:nth-child(even) td { background: #f5f5f5; }
  figure.fig { margin: 12pt 0; text-align: center; break-inside: avoid; }
  figure.fig svg { max-width: 100%; height: auto; max-height: 190mm; }
  figure.chart svg { width: 78%; }
  pre.mermaid { background: none; border: 0; font-family: 'Noto Sans', sans-serif; }
  pre:not(.mermaid) { font-size: 8pt; background: #f6f6f6; border-left: 2pt solid #999; padding: 6pt 8pt; white-space: pre-wrap; break-inside: avoid; }
  code { font-size: 8.5pt; }
  table.spec { font-size: 8.5pt; }
  table.spec thead th { text-align: center; }
  table.spec th.grp span { display: block; border-bottom: .6pt solid #111; padding: 0 2pt 2pt; }
  table.spec th.grp { border-bottom: 0; padding-bottom: 0; }
  table.spec td.bd { font-weight: 700; }
  table.spec td.best { background: #dcefd6 !important; font-weight: 700; }
  table.spec td.num { text-align: right; padding-right: 10pt; }
  table.spec td.lead { vertical-align: middle; text-align: center; font-variant: small-caps; }
  table.spec th.vs, table.spec td.vs { border-left: .6pt solid #111; }
  table.spec tr.start td { border-top: .6pt solid #111; }
  table.spec tbody tr:nth-child(even) td { background: none; }
  .math { margin: 8pt 0; text-align: center; }
  .refs { font-size: 8.5pt; }
  .refs p { text-align: left; padding-left: 18pt; text-indent: -18pt; margin-bottom: 3pt; }
</style></head>
<body>{{BODY}}</body></html>
"""
