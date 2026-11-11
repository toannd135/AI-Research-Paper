"""Figure Layout: quyết định hình nằm trong MỘT cột (mặc định) hay trải cả hai cột của bản PDF hai cột.

Hình chỉ trải hai cột khi cần để đọc được (nhiều nhãn/cột dữ liệu, sơ đồ ngang nhiều nút), không trải chỉ để to hơn:
hình trải hai cột buộc trình duyệt cân bằng cột trước/sau hình và sinh khoảng trắng.
Kích thước vẽ khớp bề rộng thật (Letter, lề 18 mm, khe cột 18 pt) để chữ trong hình in ra ~8–9 pt, không bị thu nhỏ.
"""

from __future__ import annotations

import re
from itertools import pairwise

COLUMN = "column"
WIDE = "wide"
COLUMN_WIDTH_IN = 3.4  # bề rộng một cột
WIDE_WIDTH_IN = 6.9  # bề rộng cả trang (hai cột + khe)

_LONG_LABEL = 18  # ký tự; nhãn dài hơn khó xếp trên trục ngang một cột
_MAX_COLUMN_BARS = 12  # số cột/điểm tối đa vẫn đọc được trong một cột
_MAX_COLUMN_MATRIX_COLS = 5  # heatmap/evidence map: số cột tối đa trong một cột


def _labels(spec: dict) -> list[str]:
    return [str(x) for x in spec.get("labels") or []]


def chart_span(spec: dict) -> str:
    """`layout` do người viết chỉ định thì giữ; không thì suy từ lượng nhãn/dữ liệu cần đọc được."""
    layout = spec.get("layout")
    if layout in (COLUMN, WIDE):
        return layout
    kind = spec.get("type", "bar")
    if kind == "panels":  # lưới nhiều ô con luôn chiếm cả trang
        return WIDE
    if kind == "timeline":  # nhiều mốc trên trục năm cần bề ngang để nhãn không chồng
        return WIDE if len(spec.get("events") or []) > 8 else COLUMN
    if kind in ("heatmap", "evidence_map"):
        cols = len(spec.get("x_labels") or [])
        longest = max((len(str(x)) for x in spec.get("x_labels") or []), default=0)
        return WIDE if cols > _MAX_COLUMN_MATRIX_COLS or (cols > 3 and longest > _LONG_LABEL) else COLUMN
    if kind in ("bar", "line", "stacked_bar"):  # nhãn nằm trên trục ngang
        labels = _labels(spec)
        n_series = max(1, len(spec.get("series") or []))
        longest = max((len(x) for x in labels), default=0)
        crowded = len(labels) * n_series > _MAX_COLUMN_BARS or (len(labels) > 4 and longest > _LONG_LABEL)
        return WIDE if crowded else COLUMN
    return COLUMN  # barh, dot, dumbbell, xy, phân phối: nhãn nằm trục dọc, một cột đủ đọc


def chart_width(spec: dict) -> float:
    return WIDE_WIDTH_IN if chart_span(spec) == WIDE else COLUMN_WIDTH_IN


_MERMAID_NODE_RE = re.compile(r"(?<![\w\"])([A-Za-z][\w-]*)\s*[\[({]")


def mermaid_span(code: str) -> str:
    """Sơ đồ ngang (LR/RL) từ 4 nút cần cả trang (một cột thì hộp bị thu quá nhỏ); sơ đồ dọc (TD/TB) hoặc ít nút vừa một cột."""
    horizontal = re.match(r"\s*(?:graph|flowchart)\s+(?:LR|RL)\b", code) is not None
    nodes = len(set(_MERMAID_NODE_RE.findall(code)))
    return WIDE if (horizontal and nodes >= 4) or nodes > 12 else COLUMN


_TREE_HEADER_RE = re.compile(r"^(\s*)(?:graph|flowchart)\s+(?:LR|RL|TD|TB)\b[^\n]*", re.M)
_SIMPLE_EDGE_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*-->\s*([A-Za-z][\w-]*)\s*;?\s*$")
_ANY_EDGE_RE = re.compile(r"--|==|-\.|~~~")
COMPACT_TREE_MIN_LEAVES = 12
COMPACT_TREE_MAX_BRANCHES = 8


def compact_tree(code: str) -> str:
    """Cây 2 tầng (gốc → nhánh → lá) nhiều lá: vẽ LR thì lá dồn thành một cột rất cao, bị co theo chiều cao trang nên chữ
    không đọc được. Đổi sang TD, mỗi nhánh một cột, lá xếp chồng dưới nhánh bằng liên kết ẩn '~~~'. Sơ đồ khác giữ nguyên."""
    header = _TREE_HEADER_RE.search(code)
    if not header:
        return code
    children: dict[str, list[str]] = {}
    edge_lines: list[int] = []
    lines = code.split("\n")
    for i, line in enumerate(lines):
        m = _SIMPLE_EDGE_RE.match(line)
        if m:
            children.setdefault(m.group(1), []).append(m.group(2))
            edge_lines.append(i)
        elif _ANY_EDGE_RE.search(line.split("%%")[0]) and not line.lstrip().startswith("%%"):
            return code  # cạnh có nhãn/kiểu khác: không phải cây đơn giản
    targets = {c for cs in children.values() for c in cs}
    roots = [p for p in children if p not in targets]
    if len(roots) != 1:
        return code
    branches = children[roots[0]]
    if not 2 <= len(branches) <= COMPACT_TREE_MAX_BRANCHES or any(b not in children for b in branches):
        return code
    leaves = [leaf for b in branches for leaf in children[b]]
    if len(leaves) < COMPACT_TREE_MIN_LEAVES or any(leaf in children for leaf in leaves):
        return code
    indent = header.group(1) or ""
    new_edges = [f"    {roots[0]} --> {b}" for b in branches]
    for b in branches:
        kids = children[b]
        new_edges.append(f"    {b} --> {kids[0]}")
        new_edges += [f"    {a} ~~~ {c}" for a, c in pairwise(kids)]
    drop = set(edge_lines)
    kept = [ln for i, ln in enumerate(lines) if i not in drop]
    out = "\n".join(kept).rstrip() + "\n" + "\n".join(new_edges)
    return _TREE_HEADER_RE.sub(f"{indent}graph TD", out, count=1)


_NODE_LABEL_RE = re.compile(r"^\s*([A-Za-z][\w-]*)\s*(?:\[\"?|\(\"?|\{\"?)(.+?)(?:\"?\]|\"?\)|\"?\})\s*;?\s*$")
_LABEL_CITE_RE = re.compile(r"\s*\[\d+(?:\s*[,–-]\s*\d+)*\]")


def _clean_label(raw: str) -> str:
    """Nhãn nút Mermaid → chữ thuần: bỏ <br/>, trích dẫn [n, m], dấu nháy."""
    text = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    text = _LABEL_CITE_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip(" \"'")


_LABELED_EDGE_RE = re.compile(
    r'^\s*([A-Za-z][\w-]*)(?:\s*\["?(.+?)"?\])?\s*-->\s*([A-Za-z][\w-]*)(?:\s*\["?(.+?)"?\])?\s*;?\s*$'
)


_CHAIN_NODE_RE = re.compile(r'^\s*([A-Za-z][\w-]*)\s*(?:\["?(.+?)"?\]|\("?(.+?)"?\))?\s*$')
_STAGE_PREFIX_RE = re.compile(r"^([A-Z][A-Za-z /&-]{1,30}):\s+(.+)$")
CHAINS_MIN_ROWS = 3


def parallel_chains(code: str) -> tuple[list[str], list[list[str]]] | None:
    """Sơ đồ gồm nhiều chuỗi song song cùng độ dài (vd. roadmap Gap → Direction → Evaluation): ([tiêu đề cột], [hàng]).

    Vẽ bằng Mermaid thì hộp chữ dài bị thu theo chiều cao trang, chữ còn ~5 pt; dạng bảng native đọc được.
    Tiêu đề cột lấy từ tiền tố chung 'Gap: …' của mọi ô trong cột (rồi bỏ khỏi ô); không có thì 'Stage k'.
    Không phải các chuỗi rời nhau, đều độ dài → None."""
    if not re.match(r"\s*(?:graph|flowchart)\s+(?:LR|RL)\b", code):
        return None
    labels: dict[str, str] = {}
    nxt: dict[str, str] = {}
    has_prev: set[str] = set()
    for line in code.split("\n")[1:]:
        body = line.split("%%")[0].strip()
        if not body:
            continue
        parts = body.rstrip(";").split("-->")
        nodes = []
        for part in parts:
            m = _CHAIN_NODE_RE.match(part)
            if not m:
                return None  # cạnh có nhãn, kiểu khác, subgraph/style…
            nodes.append(m.group(1))
            if m.group(2) or m.group(3):
                labels[m.group(1)] = m.group(2) or m.group(3)
        for a, b in pairwise(nodes):
            if a in nxt or b in has_prev:
                return None  # rẽ nhánh/hợp nhánh: không phải chuỗi thẳng
            nxt[a] = b
            has_prev.add(b)
    starts = [n for n in nxt if n not in has_prev]
    chains = []
    for s in starts:
        chain, seen = [s], {s}
        while chain[-1] in nxt and nxt[chain[-1]] not in seen:
            chain.append(nxt[chain[-1]])
            seen.add(chain[-1])
        chains.append(chain)
    if len(chains) < CHAINS_MIN_ROWS or sum(len(c) for c in chains) != len(has_prev) + len(starts):
        return None
    width = len(chains[0])
    if not 2 <= width <= 4 or any(len(c) != width for c in chains):
        return None
    rows = [[_clean_label(labels.get(n, n)) for n in c] for c in chains]
    headers = []
    for k in range(width):
        found = [_STAGE_PREFIX_RE.match(r[k]) for r in rows]
        if all(found) and len({f.group(1).lower() for f in found}) == 1:
            headers.append(found[0].group(1))
            for r, f in zip(rows, found, strict=True):
                r[k] = f.group(2)
        else:
            headers.append(f"Stage {k + 1}")
    return headers, rows


def _leaf_items(raw: str) -> list[str]:
    """Ô lá đã gộp '• a<br/>• b' (orient_mermaid) → [a, b]; ô thường → [nhãn]."""
    if "•" not in raw:
        return [_clean_label(raw)]
    parts = re.split(r"<br\s*/?>", raw, flags=re.I)
    return [t for t in (_clean_label(x.replace("•", "")) for x in parts) if t]


def two_level_tree(code: str) -> tuple[str, list[tuple[str, list[str]]]] | None:
    """Cây gốc → nhánh → lá (taxonomy) đọc từ Mermaid: (nhãn gốc, [(nhãn nhánh, [nhãn lá])]); không phải cây đơn giản → None.

    Nhận cả dạng đã gộp lá thành một ô danh sách '• a<br/>• b'. Nhãn đã bỏ trích dẫn: hình taxonomy chỉ cần tên nhóm,
    trích dẫn nằm ở bảng/thân bài."""
    if not _TREE_HEADER_RE.search(code):
        return None
    raw: dict[str, str] = {}
    children: dict[str, list[str]] = {}
    for line in code.split("\n"):
        body = line.split("%%")[0]
        if not body.strip() or _TREE_HEADER_RE.match(body):
            continue
        if m := _LABELED_EDGE_RE.match(body):
            a, la, b, lb = m.groups()
            children.setdefault(a, []).append(b)
            for node, label in ((a, la), (b, lb)):
                if label:
                    raw[node] = label
        elif _ANY_EDGE_RE.search(body):
            return None
        elif m := _NODE_LABEL_RE.match(body):
            raw[m.group(1)] = m.group(2)
    targets = {c for cs in children.values() for c in cs}
    roots = [p for p in children if p not in targets]
    if len(roots) != 1:
        return None
    branches = children[roots[0]]
    if not 2 <= len(branches) <= COMPACT_TREE_MAX_BRANCHES or any(b not in children for b in branches):
        return None
    if any(leaf in children for b in branches for leaf in children[b]):
        return None

    def label(node: str) -> str:
        return _clean_label(raw.get(node, node))

    tree = [(label(b), [item for leaf in children[b] for item in _leaf_items(raw.get(leaf, leaf))]) for b in branches]
    return label(roots[0]), tree
