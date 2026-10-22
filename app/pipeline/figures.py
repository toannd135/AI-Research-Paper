"""Hình thật trích từ PDF đã upload: lưu PNG + figures.json cạnh PDF, tra cứu an toàn khi render.

Layout: {upload_dir}/figures/{paper_id}/fig_{n}.png và figures.json
(list[{"file", "page", "caption", "kind", "width", "height", "source_title"}]).
Ảnh raster đủ lớn, không quá dẹt, có chú thích "Figure/Fig./Hình N" ngay trên/dưới (hoặc bên cạnh);
ảnh ghép (a)/(b) cùng chú thích hoặc cùng hàng được gộp. Chú thích còn lại → tìm hình vẽ vector
(get_drawings) ngay trên/dưới trong cùng cột; bảng chỉ có kẻ ngang bị loại. Mỗi hình có "kind".
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

import pymupdf

from app.core.config import get_settings

logger = logging.getLogger(__name__)

MIN_SIDE_PT = 100  # cạnh nhỏ nhất của cả hình (point) sau khi gộp các ô con
MIN_PART_PT = 40  # ô con nhỏ hơn mức này coi là icon/logo
MAX_ASPECT = 8  # dài/rộng lớn hơn → thanh phân cách, banner
MAX_FIGURES_PER_PAPER = 20
# "Figure 3:", "Fig. 3.", "Fig 3", "FIGURE 3 The ...", "Hình 3:"; không khớp câu thường kiểu "Figure 3 shows"
_CAPTION_RE = re.compile(
    r"^\s*(?:Figure|Fig\.?|Hình ảnh|Hình)\s*\d+[a-z]?(?:\s*[:.|]|\s+(?=(?-i:[A-Z(\[]))|\s*$)", re.IGNORECASE
)
_CAPTION_GAP_PT = 60  # khoảng cách tối đa giữa ảnh và dòng chú thích
_MIN_OVERLAP = 0.3  # chồng lấn tối thiểu (so với hộp hẹp hơn) để chú thích thuộc về hình, tránh lấy cột bên kia
_MIN_VECTOR_ITEMS = 10  # hình vector cần ít nhất ngần này nét vẽ
_VECTOR_GROW_PT = 40  # khoảng hở tối đa giữa các nét khi gom vùng hình vector
_LABEL_MAX_CHARS = 50  # khối chữ ngắn hơn coi là nhãn trục/chú giải, dài hơn là đoạn văn


def figures_root() -> Path:
    return Path(get_settings().upload_dir) / "figures"


def figures_dir(paper_id: str) -> Path:
    return figures_root() / paper_id


def _overlap_ok(a0: float, a1: float, b0: float, b1: float) -> bool:
    """Hai đoạn chồng lấn ≥ 30% đoạn ngắn hơn."""
    inter = min(a1, b1) - max(a0, b0)
    return inter > 0 and inter >= _MIN_OVERLAP * max(1.0, min(a1 - a0, b1 - b0))


def _text_blocks(blocks: list[tuple]) -> list[tuple[pymupdf.Rect, str]]:
    return [(pymupdf.Rect(b[:4]), " ".join(str(b[4]).split())) for b in blocks if len(b) < 7 or b[6] == 0]


def _find_caption(blocks: list[tuple], rect: pymupdf.Rect) -> str | None:
    """Chú thích 'Figure N' gần nhất ngay dưới (ưu tiên) hoặc trên ảnh; không có thì xét bên trái/phải."""
    best: tuple[float, str] | None = None
    side: tuple[float, str] | None = None
    for b, text in _text_blocks(blocks):
        if not _CAPTION_RE.match(text):
            continue
        if _overlap_ok(b.x0, b.x1, rect.x0, rect.x1):
            if b.y0 >= rect.y1 - 2:
                gap = b.y0 - rect.y1
            elif b.y1 <= rect.y0 + 2:
                gap = rect.y0 - b.y1 + 0.5  # chú thích phía trên ít phổ biến hơn
            else:
                continue
            if gap <= _CAPTION_GAP_PT and (best is None or gap < best[0]):
                best = (gap, text[:400])
        elif _overlap_ok(b.y0, b.y1, rect.y0, rect.y1):
            gap = b.x0 - rect.x1 if b.x0 >= rect.x1 - 2 else rect.x0 - b.x1 if b.x1 <= rect.x0 + 2 else -1
            if 0 <= gap <= _CAPTION_GAP_PT and (side is None or gap < side[0]):
                side = (gap, text[:400])
    found = best or side
    return found[1] if found else None


def _y_overlap(a: pymupdf.Rect, b: pymupdf.Rect) -> float:
    """Tỉ lệ chồng lấn theo chiều dọc so với ảnh thấp hơn (để gom các ô (a)/(b) nằm cạnh nhau)."""
    inter = min(a.y1, b.y1) - max(a.y0, b.y0)
    return max(0.0, inter) / max(1.0, min(a.height, b.height))


def _raster_figures(page: pymupdf.Page, blocks: list[tuple]) -> list[tuple[pymupdf.Rect, str]]:
    """Hình raster + chú thích; ảnh ghép (left/right, a/b) được gộp thành một hình."""
    parts: list[pymupdf.Rect] = []
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        short, long_ = sorted((rect.width, rect.height))
        if short < MIN_PART_PT or long_ / max(short, 1.0) > MAX_ASPECT:
            continue  # icon, logo, thanh phân cách
        if not any(abs(rect.x0 - r.x0) < 1 and abs(rect.y0 - r.y0) < 1 for r in parts):
            parts.append(rect)

    groups: dict[str, pymupdf.Rect] = {}
    orphans: list[pymupdf.Rect] = []
    for rect in parts:
        caption = _find_caption(blocks, rect)
        if caption is None:
            orphans.append(rect)
        elif caption in groups:
            groups[caption] |= rect
        else:
            groups[caption] = pymupdf.Rect(rect)
    for rect in orphans:  # ô con không tự thấy chú thích: gộp vào hình cùng hàng
        for caption, union in groups.items():
            if _y_overlap(rect, union) > 0.5:
                groups[caption] = union | rect
                break
    return [(r, c) for c, r in groups.items() if min(r.width, r.height) >= MIN_SIDE_PT]


def _pad(r: pymupdf.Rect, d: float) -> pymupdf.Rect:
    return pymupdf.Rect(r.x0 - d, r.y0 - d, r.x1 + d, r.y1 + d)


def _caption_column(page: pymupdf.Page, texts: list[tuple[pymupdf.Rect, str]], cap: pymupdf.Rect) -> tuple[float, float]:
    """Cột chứa chú thích: nửa trang nếu trang 2 cột và chú thích nằm gọn một nửa, ngược lại cả bề ngang."""
    pr = page.rect
    mid = (pr.x0 + pr.x1) / 2
    paras = [b for b, t in texts if len(t) > _LABEL_MAX_CHARS]
    two_col = any(b.x1 <= mid + 5 for b in paras) and any(b.x0 >= mid - 5 for b in paras)
    if two_col and cap.x1 <= mid + 5:
        return pr.x0, mid
    if two_col and cap.x0 >= mid - 5:
        return mid, pr.x1
    return pr.x0, pr.x1


def _vector_region(page: pymupdf.Page, texts: list[tuple[pymupdf.Rect, str]], drawings: list[tuple[pymupdf.Rect, int, bool]],
                   cap: pymupdf.Rect) -> pymupdf.Rect | None:
    """Vùng hình vector ngay trên (ưu tiên) hoặc dưới chú thích, trong cột của chú thích, dừng ở đoạn văn gần nhất."""
    cx0, cx1 = _caption_column(page, texts, cap)
    # đoạn văn / chú thích khác trong cùng cột là biên của vùng tìm
    stops = [b for b, t in texts if b != cap and _overlap_ok(b.x0, b.x1, cx0, cx1)
             and (len(t) > _LABEL_MAX_CHARS or _CAPTION_RE.match(t))]
    in_col = [d for d in drawings if cx0 - 1 <= (d[0].x0 + d[0].x1) / 2 <= cx1 + 1]
    for above in (True, False):
        if above:
            top = max([b.y1 for b in stops if b.y1 <= cap.y0 + 1], default=page.rect.y0)
            band = [d for d in in_col if d[0].y0 >= top - 1 and d[0].y1 <= cap.y0 + 1]
            band.sort(key=lambda d: -d[0].y1)
        else:
            bottom = min([b.y0 for b in stops if b.y0 >= cap.y1 - 1], default=page.rect.y1)
            band = [d for d in in_col if d[0].y0 >= cap.y1 - 1 and d[0].y1 <= bottom + 1]
            band.sort(key=lambda d: d[0].y0)
        region: pymupdf.Rect | None = None
        edge = cap.y0 if above else cap.y1
        items, hrules_only = 0, True
        for r, n, hrule in band:  # gom dần các nét liền kề tính từ chú thích ra xa
            if (r.y1 < edge - _VECTOR_GROW_PT) if above else (r.y0 > edge + _VECTOR_GROW_PT):
                break
            region = pymupdf.Rect(r) if region is None else region | r
            edge = min(edge, r.y0) if above else max(edge, r.y1)
            items += n
            hrules_only &= hrule
        if region is None:
            continue
        lo, hi = (region.y0, cap.y0) if above else (cap.y1, region.y1)
        inner = [(b, t) for b, t in texts if b != cap and b.intersects(region) and lo - 1 <= b.y0 and b.y1 <= hi + 1]
        if items < _MIN_VECTOR_ITEMS:
            return None
        if hrules_only and inner:
            return None  # chỉ có kẻ ngang + chữ: bảng, không phải hình
        near = _pad(region, 15)
        for b, t in texts:  # nhãn trục, chú giải ngắn quanh hình
            if b != cap and len(t) <= _LABEL_MAX_CHARS and not _CAPTION_RE.match(t) and b.intersects(near) \
                    and lo - 15 <= b.y0 and b.y1 <= hi + 15:
                region |= b
        region = _pad(region, 2) & page.rect
        return region if min(region.width, region.height) >= MIN_SIDE_PT else None
    return None


def _is_hrule(item: tuple) -> bool:
    """Nét kẻ ngang (đường hoặc hình chữ nhật cao < 2pt), kiểu đường kẻ bảng."""
    if item[0] == "l":
        return abs(item[1].y - item[2].y) < 2 and abs(item[1].x - item[2].x) > 4
    if item[0] == "re":
        return item[1].height < 2 and item[1].width > 4
    return False


def _page_figures(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str, str]]:
    """Vùng hình + chú thích + loại ('raster' | 'vector') trên 1 trang, theo thứ tự trên → dưới."""
    blocks = page.get_text("blocks")
    found = [(r, c, "raster") for r, c in _raster_figures(page, blocks)]
    texts = _text_blocks(blocks)
    used = {c for _, c, _ in found}
    free = [(b, t) for b, t in texts if _CAPTION_RE.match(t) and t[:400] not in used]
    if free:
        pr = page.rect
        drawings = []
        for d in page.get_drawings():
            r = pymupdf.Rect(d["rect"])
            hrule = all(_is_hrule(it) for it in d.get("items", ())) if d.get("items") else r.height < 2
            if r.width < 1:  # nét thẳng đứng/ngang có bề dày 0: nới ra để phép giao/hợp hoạt động
                r.x0, r.x1 = r.x0 - 0.5, r.x1 + 0.5
            if r.height < 1:
                r.y0, r.y1 = r.y0 - 0.5, r.y1 + 0.5
            if not r.intersects(pr):
                continue
            if r.width > 0.9 * pr.width and r.height > 0.9 * pr.height:
                continue  # nền/khung cả trang
            if any(f.contains(r) for f, _, _ in found):
                continue  # khung quanh ảnh raster đã lấy
            drawings.append((r & pr, max(1, len(d.get("items", ()))), hrule))
        for cap, text in free:
            region = _vector_region(page, texts, drawings, cap)
            if region is not None and not any(region.intersects(f) for f, _, _ in found):
                found.append((region, text[:400], "vector"))
    found.sort(key=lambda f: (round(f[0].y0), f[0].x0))
    return found


def extract_figures(pdf_path: str | Path, out_dir: Path, source_title: str = "") -> list[dict]:
    """Cắt vùng hình có chú thích thành PNG (render theo vùng nên xử lý được CMYK, mask, hình vector)."""
    if out_dir.exists():
        shutil.rmtree(out_dir)  # idempotent khi xử lý lại paper
    figures: list[dict] = []
    with pymupdf.open(pdf_path) as doc:
        for page_no, page in enumerate(doc, start=1):
            for rect, caption, kind in _page_figures(page):
                out_dir.mkdir(parents=True, exist_ok=True)
                name = f"fig_{len(figures) + 1}.png"
                pix = page.get_pixmap(clip=rect, dpi=150)
                pix.save(out_dir / name)
                figures.append({
                    "file": name, "page": page_no, "caption": caption, "kind": kind,
                    "width": pix.width, "height": pix.height, "source_title": source_title,
                })
                if len(figures) >= MAX_FIGURES_PER_PAPER:
                    break
            if len(figures) >= MAX_FIGURES_PER_PAPER:
                break
    if figures:
        (out_dir / "figures.json").write_text(json.dumps(figures, ensure_ascii=False, indent=1), encoding="utf-8")
    return figures


def load_figures(paper_id: str) -> list[dict]:
    """Danh sách hình của 1 paper kèm đường dẫn tuyệt đối; [] nếu chưa trích hoặc lỗi."""
    if not re.fullmatch(r"[\w-]{1,64}", paper_id or ""):
        return []
    meta = figures_dir(paper_id) / "figures.json"
    try:
        items = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for item in items:
        path = figures_dir(paper_id) / str(item.get("file", ""))
        if path.is_file():
            out.append({**item, "paper_id": paper_id, "path": str(path.resolve())})
    return out


def resolve_figure_path(path: str | None) -> Path | None:
    """Chỉ chấp nhận PNG nằm trong thư mục figures (đường dẫn đến từ báo cáo do LLM viết)."""
    if not path:
        return None
    try:
        candidate = Path(path).resolve()
        root = figures_root().resolve()
    except (OSError, RuntimeError):
        return None
    if candidate.suffix.lower() != ".png" or not candidate.is_relative_to(root) or not candidate.is_file():
        return None
    return candidate
