"""Local Mermaid/KaTeX assets and a shared, fully rendered page for PDF/SVG export."""

from __future__ import annotations

import base64
import logging
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)
ASSET_ORIGIN = "https://paperai-assets.invalid"


def launch_browser(playwright):
    return playwright.chromium.launch(executable_path=os.environ.get("PAPERAI_CHROMIUM_EXECUTABLE") or None)


def asset_path(name: str) -> Path:
    """Use image-bundled assets in Docker or npm packages in a development checkout."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Invalid PDF asset path")
    if name == "mermaid-math.js":
        return Path(__file__).resolve().parent / "assets" / name
    roots = [Path(os.environ.get("PAPERAI_RENDER_ASSETS_DIR", "/opt/paperai/render-assets"))]
    here = Path(__file__).resolve().parent
    packages = [here / "assets" / "node_modules", here.parents[3] / "frontend-paper-ai" / "node_modules"]
    for root in roots:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    for packages_dir in packages:
        candidate = (packages_dir / "mermaid" / "dist" / relative) if name == "mermaid.min.js" else (
            packages_dir / "katex" / "dist" / Path(*relative.parts[1:])
        )
        if (name.startswith("katex/") or name == "mermaid.min.js") and candidate.is_file():
            return candidate
    raise RuntimeError(
        "Thiếu thư viện render PDF. Chạy docker compose up -d --build api worker "
        "hoặc npm ci trong app/pipeline/export/assets khi chạy local."
    )


def install_asset_routes(page) -> None:
    # Validate before printing: a missing JS library must not produce an empty diagram.
    for name in ("mermaid.min.js", "mermaid-math.js", "katex/katex.min.js", "katex/katex.min.css", "katex/contrib/auto-render.min.js"):
        asset_path(name)

    def serve(route):
        url = urlparse(route.request.url)
        if f"{url.scheme}://{url.netloc}" != ASSET_ORIGIN:
            route.abort()
            return
        try:
            path = asset_path(url.path.lstrip("/"))
            route.fulfill(
                path=str(path),
                content_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                headers={"Access-Control-Allow-Origin": "*"},
            )
        except (ValueError, RuntimeError):
            route.abort()

    page.route("**/*", serve)


def prepare_report_page(page, page_html: str) -> list[str]:
    """Wait for every diagram, formula and font, then fit objects to printable A4 space."""
    install_asset_routes(page)
    page.emulate_media(media="print")
    page.set_viewport_size({"width": 658, "height": 972})
    page.set_content(page_html, wait_until="load", timeout=60_000)
    warnings = page.evaluate(r"""async assetOrigin => {
        if (!window.mermaid || !window.renderMathInElement) {
            throw new Error('Không tải được Mermaid/KaTeX để xuất PDF');
        }
        const warnings = [];
        const {normalizeMermaidMath} = await import(assetOrigin + '/mermaid-math.js');
        mermaid.initialize({startOnLoad: false, theme: 'neutral', securityLevel: 'strict', htmlLabels: true,
            fontFamily: 'Arial, sans-serif', flowchart: {htmlLabels: true, useMaxWidth: false, rankSpacing: 65}});
        let index = 0;
        for (const pre of document.querySelectorAll('pre.mermaid')) {
            const id = `pdf-mermaid-${++index}`;
            try {
                const {svg} = await mermaid.render(id, normalizeMermaidMath(pre.textContent));
                const container = document.createElement('div');
                container.className = 'mermaid-rendered';
                container.innerHTML = svg;
                pre.replaceWith(container);
            } catch (error) {
                // Keep the complete source and an explicit notice; never invent a replacement graph.
                document.getElementById(id)?.remove();
                document.getElementById('d' + id)?.remove();
                pre.className = 'render-error';
                const notice = document.createElement('p');
                notice.className = 'render-warning';
                notice.textContent = 'Không render được sơ đồ; mã nguồn được giữ bên dưới.';
                pre.before(notice);
                warnings.push(`Sơ đồ ${index}: ${String(error)}`);
            }
        }
        renderMathInElement(document.body, {delimiters: [
            {left: '\\[', right: '\\]', display: true},
            {left: '\\(', right: '\\)', display: false},
            {left: '$$', right: '$$', display: true},
            {left: '$', right: '$', display: false}
        ], throwOnError: false, strict: false, ignoredClasses: ['mermaid-rendered']});
        await document.fonts.ready;
        for (const image of Array.from(document.images)) {
            try { await image.decode(); } catch (_) {
                const notice = document.createElement('p');
                notice.className = 'render-warning';
                notice.textContent = 'Không tải được hình ảnh: ' + (image.alt || image.src);
                image.replaceWith(notice);
                warnings.push(notice.textContent);
            }
        }
        const width = document.body.clientWidth;
        const height = 220 * 96 / 25.4; // Leave room for the caption and page footer.
        for (const svg of document.querySelectorAll('figure.fig svg')) {
            const box = svg.viewBox.baseVal;
            const rect = svg.getBoundingClientRect();
            const w = box.width || rect.width;
            const h = box.height || rect.height;
            if (!w || !h) continue;
            const scale = Math.min(width / w, height / h);
            svg.style.width = `${w * scale}px`;
            svg.style.height = `${h * scale}px`;
            svg.style.maxWidth = '100%';
            svg.style.maxHeight = 'none';
        }
        for (const table of document.querySelectorAll('table')) {
            const columns = Array.from(table.rows[0]?.cells || []).reduce((n, cell) => n + cell.colSpan, 0);
            if (columns > 6) table.classList.add('wide');
            const wrapper = table.closest('.tbl');
            if (wrapper && wrapper.getBoundingClientRect().height < height) {
                wrapper.classList.add('keep-together');
            }
        }
        for (const equation of document.querySelectorAll('.katex-display > .katex')) {
            const available = Math.min(width, equation.parentElement.getBoundingClientRect().width);
            if (equation.scrollWidth > available) {
                equation.style.fontSize = `${available / equation.scrollWidth * 100}%`;
            }
        }
        for (const error of document.querySelectorAll('.katex-error')) {
            warnings.push('Công thức chưa render được: ' + error.textContent);
        }
        return warnings;
    }""", ASSET_ORIGIN)
    for warning in warnings:
        logger.warning("PDF render: %s", warning)
    return warnings


def mermaid_to_svg(code: str) -> str:
    """Render locally; flatten MathML labels for Typst's SVG reader."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = launch_browser(p)
        try:
            page = browser.new_page(device_scale_factor=3)
            install_asset_routes(page)
            page.set_content(f'<script src="{ASSET_ORIGIN}/mermaid.min.js"></script>', wait_until="load")
            svg = page.evaluate("""async ({code, assetOrigin}) => {
                const {normalizeMermaidMath} = await import(assetOrigin + '/mermaid-math.js');
                const normalized = normalizeMermaidMath(code);
                const math = normalized.includes('$$');
                mermaid.initialize({startOnLoad:false, theme:'neutral', securityLevel:'strict', htmlLabels:math,
                    flowchart:{htmlLabels:math, useMaxWidth:false, rankSpacing:65}});
                return (await mermaid.render('typst-flowchart', normalized)).svg;
            }""", {"code": code, "assetOrigin": ASSET_ORIGIN})
            if "<foreignObject" not in svg:
                return svg
            # Typst does not render HTML/MathML inside SVG foreignObject. Preserve those labels as pixels.
            page.set_content('<style>body{margin:0}</style>' + svg, wait_until="load")
            page.evaluate("() => document.fonts.ready")
            diagram = page.locator("body > svg")
            bounds = diagram.bounding_box()
            encoded = base64.b64encode(diagram.screenshot(type="png")).decode("ascii")
            width, height = bounds["width"], bounds["height"]
            return (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
                f'<image width="{width}" height="{height}" href="data:image/png;base64,{encoded}"/></svg>'
            )
        finally:
            browser.close()
