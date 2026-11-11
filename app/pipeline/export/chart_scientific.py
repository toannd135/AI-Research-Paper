"""Biểu đồ khoa học (xy / phân phối / heatmap) cho khối ```chart.

Các type: xyline (hội tụ, độ nhạy 1D, scalability), scatter (PCA/t-SNE/UMAP), cdf (latency),
histogram, boxplot, heatmap (độ nhạy 2D, Δ theo cấu hình; ô null = NR), dot (so sánh phương pháp × metric),
dumbbell (hai điều kiện ghép cặp: validation/test, có/không module), evidence_map (nghiên cứu × tiêu chí: Yes/No/NR),
panels (lưới small multiples dot/line/xyline, chú giải chung), timeline (năm × nhóm phương pháp; năm kiểm chứng theo References).
Chỉ vẽ số liệu có trong spec — không sinh dữ liệu; giá trị thiếu không bao giờ vẽ thành 0.
"""

import io
import math
import textwrap

# Font hình thống nhất cho mọi biểu đồ và sơ đồ Mermaid (Chromium: Arial → Liberation Sans), cỡ 8 pt như chú thích IEEE
FIGURE_FONT = ["Liberation Sans", "DejaVu Sans"]  # Liberation Sans = metric Arial; máy không có thì DejaVu Sans
FIGURE_FONT_PT = 8
SCIENTIFIC_TYPES = {"xyline", "scatter", "cdf", "histogram", "boxplot", "heatmap", "dot", "dumbbell", "evidence_map", "panels", "timeline"}
PANEL_TYPES = {"dot", "xyline", "line"}
MAX_PANELS = 8
_EVIDENCE_COLORS = {"yes": "#4f9a5b", "partial": "#e3b448", "no": "#c8553d", "nr": "#e6e6e6"}

_PALETTE = ["#1f4e79", "#c55a11", "#548235", "#7f6000", "#7030a0", "#2e75b6"]
# 7 marker × 6 màu (nguyên tố cùng nhau): 42 series đầu không trùng cặp màu–marker
_MARKERS = ["o", "s", "^", "D", "v", "P", "X"]


def _floats(seq) -> list[float]:
    out = []
    for v in seq or []:
        if isinstance(v, bool) or v is None:
            continue
        try:
            out.append(float(str(v).replace("%", "").replace(",", "").strip()))
        except ValueError:
            continue
    return out


def _pairs(xs, ys, errs=None) -> list[tuple[float, float, float | None]]:
    """Ghép (x, y, err); bỏ điểm thiếu x hoặc y."""
    pts = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        fx, fy = _floats([x]), _floats([y])
        if not fx or not fy:
            continue
        e = _floats([errs[i]]) if errs and i < len(errs) else []
        pts.append((fx[0], fy[0], e[0] if e else None))
    return pts


def _cell(v) -> float:
    f = _floats([v])
    return f[0] if f else float("nan")


def _labelled_values(spec: dict) -> tuple[list[str], list[tuple[str, list[float]]]]:
    """labels + series[{name, values}] → (nhãn, [(tên, giá trị float|nan)]) — dùng cho dot/dumbbell."""
    labels = [str(x) for x in spec.get("labels") or []]
    out = []
    for s in spec.get("series") or []:
        if isinstance(s, dict) and len(s.get("values") or []) == len(labels):
            out.append((str(s.get("name") or ""), [_cell(v) for v in s["values"]]))
    return labels, out


def _evidence_key(v) -> str:
    t = str(v or "").strip().lower()
    for key in ("yes", "partial", "no"):
        if t.startswith(key):
            return key
    return "nr"


def _draw_dot(ax, spec: dict, colors: list[str] | None = None, markers: list[str] | None = None) -> int:
    colors, markers = colors or _PALETTE, markers or _MARKERS
    labels, series = _labelled_values(spec)
    keep = [i for i in range(len(labels)) if any(not math.isnan(v[i]) for _, v in series)]
    if not keep:
        return 0
    ys = list(range(len(keep)))
    offs = [0.0] if len(series) == 1 else [(-0.25 + 0.5 * k / (len(series) - 1)) for k in range(len(series))]
    for k, (name, vals) in enumerate(series):
        pts = [(vals[i], y + offs[k]) for y, i in zip(ys, keep, strict=True) if not math.isnan(vals[i])]
        ax.scatter([p[0] for p in pts], [p[1] for p in pts], s=26, color=colors[k % len(colors)],
                   marker=markers[k % len(markers)], label=name, zorder=3)
    ax.set_yticks(ys, [labels[i] for i in keep])
    ax.invert_yaxis()
    ax.grid(axis="y", color="#eee", linewidth=0.6)
    return len(series)


def _draw_dumbbell(ax, spec: dict) -> int:
    labels, series = _labelled_values(spec)
    if len(series) != 2:
        raise ValueError("dumbbell cần đúng 2 series (hai điều kiện ghép cặp)")
    (n1, a), (n2, b) = series
    keep = [i for i in range(len(labels)) if not math.isnan(a[i]) and not math.isnan(b[i])]
    if not keep:
        return 0
    ys = list(range(len(keep)))
    for y, i in zip(ys, keep, strict=True):
        ax.plot([a[i], b[i]], [y, y], color="#9a9a9a", linewidth=2.2, zorder=1)
        ax.annotate(f"{b[i] - a[i]:+.3g}", (max(a[i], b[i]), y), textcoords="offset points", xytext=(6, -3), fontsize=7, color="#444")
    ax.scatter([a[i] for i in keep], ys, s=34, color=_PALETTE[0], label=n1, zorder=3)
    ax.scatter([b[i] for i in keep], ys, s=34, color=_PALETTE[1], marker="s", label=n2, zorder=3)
    ax.set_yticks(ys, [labels[i] for i in keep])
    ax.invert_yaxis()
    lo, hi = min(min(a[i], b[i]) for i in keep), max(max(a[i], b[i]) for i in keep)
    pad = (hi - lo) * 0.25 or 1.0
    ax.set_xlim(lo - pad * 0.4, hi + pad)
    return 2


def _draw_heatmap(fig, ax, spec: dict) -> int:
    import matplotlib

    xl, yl = [str(x) for x in spec.get("x_labels", [])], [str(y) for y in spec.get("y_labels", [])]
    rows = spec.get("matrix") or []
    if not rows or len(rows) != len(yl) or not all(isinstance(r, list) and len(r) == len(xl) for r in rows):
        return 0
    matrix = [[_cell(v) for v in r] for r in rows]
    flat = [v for r in matrix for v in r if not math.isnan(v)]
    if not flat:
        return 0
    lo, hi = min(flat), max(flat)
    diverging = lo < 0 < hi  # Δ so với mốc: âm/dương đối xứng quanh 0
    if diverging:
        bound = max(abs(lo), abs(hi))
        cmap, vmin, vmax = matplotlib.colormaps["RdBu"].with_extremes(bad="#eeeeee"), -bound, bound
    elif hi <= 0:  # toàn Δ âm (suy giảm): đỏ đậm = giảm nhiều
        cmap, vmin, vmax = matplotlib.colormaps["Reds_r"].with_extremes(bad="#eeeeee"), lo, 0.0
    else:
        cmap, vmin, vmax = matplotlib.colormaps["viridis"].with_extremes(bad="#eeeeee"), lo, hi
    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax if vmax > vmin else vmin + 1, aspect="auto")
    ax.set_xticks(range(len(xl)), xl, rotation=30 if max(map(len, xl)) > 6 else 0, ha="right" if max(map(len, xl)) > 6 else "center")
    ax.set_yticks(range(len(yl)), yl)
    for yi, row in enumerate(matrix):
        for xi, v in enumerate(row):
            if math.isnan(v):
                ax.text(xi, yi, "NR", ha="center", va="center", fontsize=6.5, color="#777")
                continue
            t = (v - vmin) / ((vmax - vmin) or 1.0)
            dark = (t < 0.2 or t > 0.8) if diverging else (t < 0.45 if hi <= 0 else t < 0.6)
            signed = diverging or hi <= 0
            v = 0.0 if abs(v) < 1e-9 else v  # tránh "-0"
            ax.text(xi, yi, f"{v:+.3g}" if signed and v else f"{v:g}", ha="center", va="center", fontsize=6.5, color="white" if dark else "#222")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label=spec.get("c_label", ""))
    return 1


def _draw_evidence_map(ax, spec: dict) -> int:
    from matplotlib.patches import Patch, Rectangle

    xl, yl = [str(x) for x in spec.get("x_labels", [])], [str(y) for y in spec.get("y_labels", [])]
    rows = spec.get("matrix") or []
    if not rows or len(rows) != len(yl) or not all(isinstance(r, list) and len(r) == len(xl) for r in rows):
        return 0
    for yi, row in enumerate(rows):
        for xi, v in enumerate(row):
            key = _evidence_key(v)
            ax.add_patch(Rectangle((xi - 0.45, yi - 0.42), 0.9, 0.84, color=_EVIDENCE_COLORS[key], linewidth=0))
    ax.set_xlim(-0.5, len(xl) - 0.5)
    ax.set_ylim(len(yl) - 0.5, -0.5)
    dense = len(xl) > 20
    ax.set_xticks(range(len(xl)), xl, rotation=90 if dense else 35, ha="center" if dense else "right",
                  fontsize=FIGURE_FONT_PT - 1 if dense else None)  # nhãn [n] dày vẫn ≥7 pt để đọc được khi in
    ax.set_yticks(range(len(yl)), yl)
    ax.tick_params(length=0)
    ax.legend(handles=[Patch(color=c, label="NR" if k == "nr" else k.capitalize()) for k, c in _EVIDENCE_COLORS.items()
                       if k != "partial" or any(_evidence_key(v) == "partial" for r in rows for v in r)],
              loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=4, frameon=False, fontsize=FIGURE_FONT_PT - 1)
    return 1


_LEGEND_CHARS_PER_ROW = 56  # ~số ký tự 8pt vừa một hàng legend trong hình rộng 1 cột


def finish_figure(fig, fmt: str = "svg") -> str | bytes:
    """Lưu figure: svg → str; pdf/eps → bytes vector (font TrueType nhúng, đạt yêu cầu IEEE)."""
    import matplotlib.pyplot as plt

    if fmt not in ("svg", "pdf", "eps"):
        raise ValueError(f"Định dạng biểu đồ không hỗ trợ: {fmt}")
    plt.rcParams.update({"pdf.fonttype": 42, "ps.fonttype": 42})
    buf = io.StringIO() if fmt == "svg" else io.BytesIO()
    fig.savefig(buf, format=fmt, bbox_inches="tight")
    plt.close(fig)
    data = buf.getvalue()
    return data[data.index("<svg"):] if fmt == "svg" else data


def _timeline_events(spec: dict) -> list[tuple[int, str, str]]:
    out = []
    for e in spec.get("events") or []:
        if not isinstance(e, dict):
            continue
        try:
            year = int(e.get("year"))
        except (TypeError, ValueError):
            continue
        if e.get("label"):
            out.append((year, str(e["label"]), str(e.get("group") or "")))
    return sorted(out)


_YEAR_LABEL_IN = 0.42  # bề rộng tối thiểu dành cho một nhãn năm cỡ 7pt kèm khoảng hở


def _axis_width_in(ax, groups: list[str]) -> float:
    """Ước lượng bề rộng trục ngang (inch) sau khi trừ cột tên nhóm bên trái."""
    fig_w = ax.figure.get_figwidth()
    longest = max((len(line) for g in groups for line in textwrap.wrap(g, 16)), default=0)
    return max(1.0, fig_w - (0.06 * longest + 0.45))


def _spaced_years(years: list[int], lo: float, hi: float, axis_in: float) -> list[int]:
    """Chỉ giữ các năm cách nhau đủ xa để nhãn không chồng; luôn giữ năm đầu và năm cuối."""
    per_year = axis_in / max(hi - lo, 1e-6)
    gap = max(1, math.ceil(_YEAR_LABEL_IN / per_year))
    kept = [years[0]]
    for year in years[1:]:
        if year - kept[-1] >= gap:
            kept.append(year)
    # năm cuối bị bỏ vì quá sát năm giữ trước đó → đổi năm đó thành năm cuối (nếu vẫn đủ xa năm trước nữa)
    if kept[-1] != years[-1] and len(kept) > 1 and years[-1] - kept[-2] >= gap:
        kept[-1] = years[-1]
    return kept


def _draw_timeline(ax, spec: dict) -> int:
    """Dòng thời gian: trục ngang = năm, mỗi làn = một nhóm phương pháp; nhãn so le trên/dưới để không chồng nhau."""
    events = _timeline_events(spec)
    if len(events) < 2:
        return 0
    groups = list(dict.fromkeys(g for _, _, g in events))
    lane = {g: i for i, g in enumerate(groups)}
    slot: dict[str, int] = {}
    for year, label, group in events:
        # so le trên/dưới theo thứ tự mốc trong làn (không chỉ cùng năm) để nhãn của các năm gần nhau không đè lên nhau
        k = slot.get(group, 0)
        slot[group] = k + 1
        y = lane[group]
        color = _PALETTE[lane[group] % len(_PALETTE)]
        ax.scatter([year], [y], s=22, color=color, marker=_MARKERS[lane[group] % len(_MARKERS)], zorder=3)
        dy = (0.28 + 0.14 * ((k // 2) % 2)) * (1 if k % 2 == 0 else -1)
        ax.annotate(label, (year, y), xytext=(year, y + dy), fontsize=FIGURE_FONT_PT - 1, ha="center", va="center", color="#222",
                    arrowprops={"arrowstyle": "-", "color": "#bbb", "linewidth": 0.5})
    years = [y for y, _, _ in events]
    lo, hi = min(years) - 0.7, max(years) + 0.7
    ax.set_xlim(lo, hi)
    # tên nhóm dài xuống dòng → trục ngang còn đủ rộng
    ax.set_yticks(range(len(groups)), [textwrap.fill(g, 16) for g in groups])
    ax.tick_params(axis="x", labelsize=7)
    ax.set_xticks(_spaced_years(sorted(set(years)), lo, hi, _axis_width_in(ax, groups)))
    ax.set_ylim(len(groups) - 0.4, -0.6)
    for i in range(len(groups)):
        ax.axhline(i, color="#eee", linewidth=0.8, zorder=1)
    return len(events)


def _draw_panel(ax, spec: dict, colors: list[str], markers: list[str]) -> int:
    """Một ô con của lưới: dot (nhãn trục dọc), xyline (x số thực) hoặc line (nhãn thứ tự trên trục ngang).

    colors/markers xếp theo thứ tự series của ô (đã ánh xạ theo tên ở cấp lưới)."""
    kind = spec.get("type", "line")
    if kind == "dot":
        return _draw_dot(ax, spec, colors, markers)
    drawn = 0
    if kind == "xyline":
        for i, s in enumerate(x for x in spec.get("series", []) if isinstance(x, dict)):
            pts = sorted(_pairs(s.get("x", []), s.get("y", [])))
            if pts:
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=markers[i % len(markers)], markersize=3.5,
                        linewidth=1.4, color=colors[i % len(colors)], label=s.get("name"))
                drawn += 1
        return drawn
    labels, series = _labelled_values(spec)
    xs = list(range(len(labels)))
    for i, (name, vals) in enumerate(series):
        pts = [(x, v) for x, v in zip(xs, vals, strict=True) if not math.isnan(v)]  # NR = đứt nét, không nội suy
        if pts:
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker=markers[i % len(markers)], markersize=3.5,
                    linewidth=1.4, color=colors[i % len(colors)], label=name)
            drawn += 1
    ax.set_xticks(xs, labels)
    return drawn


def render_panels_svg(spec: dict, fmt: str = "svg") -> str | bytes:
    """Lưới small multiples: mỗi ô một setting/điều kiện, chú giải chung bên dưới; màu/marker theo TÊN series nhất quán mọi ô.

    spec: {type: "panels", ncols, panels: [{type: dot|xyline|line, title, labels?, series, x_label?, y_label?}], sharey?}
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from app.pipeline.export.figure_layout import WIDE_WIDTH_IN

    panels = [p for p in spec.get("panels", []) if isinstance(p, dict) and p.get("type", "line") in PANEL_TYPES][:MAX_PANELS]
    if not panels:
        raise ValueError("chart panels thiếu ô con hợp lệ")
    names: list[str] = []
    for p in panels:
        for s in p.get("series", []):
            if isinstance(s, dict) and s.get("name") and s["name"] not in names:
                names.append(s["name"])
    order = {n: i for i, n in enumerate(names)}
    ncols = max(1, min(int(spec.get("ncols") or (4 if len(panels) >= 4 else len(panels))), len(panels)))
    nrows = math.ceil(len(panels) / ncols)
    dot_rows = max((len(p.get("labels") or []) for p in panels if p.get("type") == "dot"), default=0)
    cell_h = max(1.9, 0.22 * dot_rows + 0.9)
    plt.rcParams.update({"font.family": FIGURE_FONT, "font.size": FIGURE_FONT_PT - 0.5, "svg.fonttype": "path"})
    fig, axes = plt.subplots(nrows, ncols, figsize=(WIDE_WIDTH_IN, cell_h * nrows + 0.5), squeeze=False,
                             sharey=bool(spec.get("sharey")))
    drawn = 0
    for idx, ax in enumerate(axes.flat):
        if idx >= len(panels):
            ax.set_visible(False)
            continue
        p = dict(panels[idx])
        # màu theo vị trí tên series trong toàn lưới → cùng phương pháp cùng màu ở mọi ô
        p["series"] = sorted((s for s in p.get("series", []) if isinstance(s, dict)), key=lambda s: order.get(s.get("name"), 99))
        idxs = [order.get(s.get("name"), k) for k, s in enumerate(p["series"])]
        drawn += _draw_panel(
            ax, p, [_PALETTE[i % len(_PALETTE)] for i in idxs] or _PALETTE, [_MARKERS[i % len(_MARKERS)] for i in idxs] or _MARKERS
        )
        ax.set_title(str(p.get("title") or ""), fontsize=8)
        if p.get("x_label"):
            ax.set_xlabel(p["x_label"])
        if p.get("y_label"):
            ax.set_ylabel(p["y_label"])
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(linestyle=":", alpha=0.6)
        ax.set_axisbelow(True)
    if not drawn:
        plt.close(fig)
        raise ValueError("chart panels thiếu dữ liệu hợp lệ")
    if spec.get("title"):
        fig.suptitle(str(spec["title"]), fontsize=9)
    handles: dict[str, object] = {}
    for ax in axes.flat:
        for h, lab in zip(*ax.get_legend_handles_labels(), strict=True):
            handles.setdefault(lab, h)
    fig.tight_layout(rect=(0, 0.08 if len(handles) > 1 else 0, 1, 1))
    if len(handles) > 1:
        fig.legend(handles.values(), handles.keys(), loc="lower center", ncol=min(len(handles), 5), frameon=True, fontsize=7.5,
                   edgecolor="#bbb", bbox_to_anchor=(0.5, 0.0))
    return finish_figure(fig, fmt)


def render_scientific_svg(spec: dict, fmt: str = "svg") -> str | bytes:
    if spec.get("type") == "panels":
        return render_panels_svg(spec, fmt)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from app.pipeline.export.figure_layout import COLUMN_WIDTH_IN, chart_width

    kind = spec["type"]
    series = [s for s in spec.get("series", []) if isinstance(s, dict)]
    width = chart_width(spec)
    narrow = width <= COLUMN_WIDTH_IN
    n_rows = len(spec.get("y_labels") or spec.get("labels") or [])
    if kind in ("heatmap", "evidence_map", "dot", "dumbbell"):  # một hàng mỗi nhãn: cao theo số hàng
        height = max(2.0, 0.24 * n_rows + 1.1)
    elif kind == "timeline":  # một làn mỗi nhóm, chừa chỗ cho nhãn so le
        height = max(1.8, 0.5 * len({g for _, _, g in _timeline_events(spec)}) + 0.8)  # ít nhóm → hình thấp, không thừa khoảng trắng
    else:
        height = 2.7 if narrow else 3.6
    plt.rcParams.update({"font.family": FIGURE_FONT, "font.size": FIGURE_FONT_PT, "svg.fonttype": "path"})
    fig, ax = plt.subplots(figsize=(width, height))
    drawn = 0

    if kind in ("xyline", "scatter"):
        for i, s in enumerate(series):
            pts = sorted(_pairs(s.get("x", []), s.get("y", []), s.get("errors"))) if kind == "xyline" else _pairs(s.get("x", []), s.get("y", []))
            if not pts:
                continue
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            color = _PALETTE[i % len(_PALETTE)]
            if kind == "scatter":
                ax.scatter(xs, ys, s=14, color=color, alpha=0.75, marker=_MARKERS[i % len(_MARKERS)], label=s.get("name"))
            else:
                errs = [p[2] for p in pts]
                if any(e is not None for e in errs):
                    ax.errorbar(xs, ys, yerr=[e or 0.0 for e in errs], marker=_MARKERS[i % len(_MARKERS)], markersize=4,
                                linewidth=1.5, capsize=2.5, color=color, label=s.get("name"))
                else:
                    ax.plot(xs, ys, marker=_MARKERS[i % len(_MARKERS)], markersize=4, linewidth=1.5, color=color, label=s.get("name"))
            drawn += 1
        if spec.get("x_scale") == "log":
            ax.set_xscale("log")
        if spec.get("y_scale") == "log":
            ax.set_yscale("log")
    elif kind == "cdf":
        for i, s in enumerate(series):
            vals = sorted(_floats(s.get("samples")))
            if not vals:
                continue
            n = len(vals)
            ax.step(vals, [(k + 1) / n for k in range(n)], where="post", linewidth=1.6, color=_PALETTE[i % len(_PALETTE)], label=s.get("name"))
            drawn += 1
        for q in _floats(spec.get("percentiles", [])):
            ax.axhline(q / 100.0, color="#888", linestyle="--", linewidth=0.8)
        ax.set_ylim(0, 1.02)
        if not spec.get("y_label"):
            spec = {**spec, "y_label": "CDF"}
    elif kind == "histogram":
        bins = int(spec.get("bins", 20))
        for i, s in enumerate(series):
            vals = _floats(s.get("samples"))
            if vals:
                ax.hist(vals, bins=bins, alpha=0.65, color=_PALETTE[i % len(_PALETTE)], label=s.get("name"), edgecolor="white", linewidth=0.5)
                drawn += 1
    elif kind == "boxplot":
        data = [(s.get("name") or "", _floats(s.get("samples"))) for s in series]
        data = [d for d in data if d[1]]
        if data:
            bp = ax.boxplot([d[1] for d in data], tick_labels=[d[0] for d in data], patch_artist=True, widths=0.55,
                            medianprops={"color": "#222"}, flierprops={"markersize": 3})
            for i, box in enumerate(bp["boxes"]):
                box.set_facecolor(_PALETTE[i % len(_PALETTE)])
                box.set_alpha(0.6)
            drawn = len(data)
    elif kind == "heatmap":
        drawn = _draw_heatmap(fig, ax, spec)
    elif kind == "evidence_map":
        drawn = _draw_evidence_map(ax, spec)
    elif kind == "dot":
        drawn = _draw_dot(ax, spec)
    elif kind == "dumbbell":
        drawn = _draw_dumbbell(ax, spec)
    elif kind == "timeline":
        drawn = _draw_timeline(ax, spec)

    if not drawn:
        plt.close(fig)
        raise ValueError(f"chart {kind} thiếu dữ liệu hợp lệ")

    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"])
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"])
    if kind in ("heatmap", "evidence_map", "timeline"):
        ax.spines[:].set_visible(False)
    elif kind in ("dot", "dumbbell"):
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", linestyle=":", alpha=0.6)
        ax.set_axisbelow(True)
    else:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(linestyle=":", alpha=0.6)
        ax.set_axisbelow(True)
    named = [str(s.get("name")) for s in series if s.get("name")]
    if kind in ("xyline", "scatter", "cdf", "histogram", "dot", "dumbbell") and len(named) > 1:
        # Số cột legend theo độ dài nhãn: legend rộng hơn hình làm bbox "tight" nở ngang, LaTeX thu nhỏ cả hình -> chữ không đọc được
        ncol = max(1, min(4, len(named), _LEGEND_CHARS_PER_ROW // (max(map(len, named)) + 4)))
        legend_rows = -(-len(named) // ncol)
        if legend_rows > 1:  # legend nhiều dòng chiếm chỗ của trục: nới chiều cao để vùng vẽ không bị bẹp
            w, h = fig.get_size_inches()
            fig.set_size_inches(w, h + min(0.6, 0.1 * (legend_rows - 1)))
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=ncol, frameon=True, fontsize=7 if len(named) > 4 else 8, edgecolor="#bbb")
    fig.tight_layout()

    return finish_figure(fig, fmt)
