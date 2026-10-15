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

_FENCE_RE = re.compile(r"```(mermaid|chart)[ \t]*\n(.*?)```", re.DOTALL)
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"\\\((.+?)\\\)")
_PLACEHOLDER_RE = re.compile(r"(?:<p>)?\s*PAPERAIBLOCK(\d+)END\s*(?:</p>)?")

_PALETTE = ["#1f4e79", "#c55a11", "#548235", "#7f6000", "#7030a0", "#2e75b6"]


def _render_chart_svg(spec: dict) -> str:
    """Vẽ biểu đồ theo spec JSON: {type: bar|barh|line, labels, series: [{name, values}], x_label, y_label}."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = [str(x) for x in spec["labels"]]
    series = [s for s in spec["series"] if len(s.get("values", [])) == len(labels)]
    if not labels or not series:
        raise ValueError("chart spec thiếu labels/series hợp lệ")
    kind = spec.get("type", "bar")

    plt.rcParams.update({"font.family": "DejaVu Serif", "font.size": 9, "svg.fonttype": "path"})
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    n = len(series)
    if kind == "line":
        for i, s in enumerate(series):
            ax.plot(labels, s["values"], marker="o", linewidth=1.6, color=_PALETTE[i % len(_PALETTE)], label=s.get("name"))
    else:
        width = 0.8 / n
        positions = range(len(labels))
        for i, s in enumerate(series):
            offset = [p - 0.4 + width * (i + 0.5) for p in positions]
            color = _PALETTE[i % len(_PALETTE)]
            if kind == "barh":
                bars = ax.barh(offset, s["values"], height=width, color=color, label=s.get("name"))
            else:
                bars = ax.bar(offset, s["values"], width=width, color=color, label=s.get("name"))
            ax.bar_label(bars, fmt="%g", fontsize=7, padding=2)
        if kind == "barh":
            ax.set_yticks(list(positions), labels)
            ax.invert_yaxis()
        else:
            ax.set_xticks(list(positions), labels, rotation=20 if max(map(len, labels)) > 10 else 0, ha="right" if max(map(len, labels)) > 10 else "center")

    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"])
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"])
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="x" if kind == "barh" else "y", linestyle=":", alpha=0.6)
    if n > 1 or series[0].get("name"):
        ax.legend(frameon=False, fontsize=8)
    fig.tight_layout()

    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    svg = buf.getvalue()
    return svg[svg.index("<svg") :]


def _extract_blocks(md: str) -> tuple[str, list[str]]:
    """Thay khối mermaid/chart/công thức bằng placeholder để Markdown không làm hỏng nội dung."""
    blocks: list[str] = []

    def keep(fragment: str, block: bool = True) -> str:
        blocks.append(fragment)
        token = f"PAPERAIBLOCK{len(blocks) - 1}END"
        return f"\n\n{token}\n\n" if block else token

    def fence(match: re.Match) -> str:
        kind, body = match.group(1), match.group(2).strip()
        if kind == "mermaid":
            return keep(f'<figure class="fig" data-kind="figure"><pre class="mermaid">{html.escape(body)}</pre>__CAPTION__</figure>')
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
            out.append(f'<div class="tbl"><div class="caption"><b>Table {counters["table"]}.</b> {text}</div><table>')
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
    body = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    body = _PLACEHOLDER_RE.sub(lambda m: blocks[int(m.group(1))], body)
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
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Serif:ital,wght@0,400;0,700;1,400&family=Noto+Sans:wght@400;600&display=swap">
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
  .math { margin: 8pt 0; text-align: center; }
  .refs { font-size: 8.5pt; }
  .refs p { text-align: left; padding-left: 18pt; text-indent: -18pt; margin-bottom: 3pt; }
</style></head>
<body>{{BODY}}</body></html>
"""
