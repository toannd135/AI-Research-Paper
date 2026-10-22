"""Biểu đồ khoa học (xy / phân phối / heatmap) cho khối ```chart.

Các type: xyline (hội tụ, độ nhạy 1D, scalability), scatter (PCA/t-SNE/UMAP), cdf (latency),
histogram, boxplot, heatmap (độ nhạy 2D). Chỉ vẽ số liệu có trong spec — không sinh dữ liệu.
"""

import io
import math

SCIENTIFIC_TYPES = {"xyline", "scatter", "cdf", "histogram", "boxplot", "heatmap"}

_PALETTE = ["#1f4e79", "#c55a11", "#548235", "#7f6000", "#7030a0", "#2e75b6"]
_MARKERS = ["o", "s", "^", "D", "v", "P"]


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


def render_scientific_svg(spec: dict, fmt: str = "svg") -> str | bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    kind = spec["type"]
    series = [s for s in spec.get("series", []) if isinstance(s, dict)]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "svg.fonttype": "path"})
    fig, ax = plt.subplots(figsize=(6.6, 3.6 if kind != "heatmap" else 3.8))
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
        matrix = [_floats(r) if len(_floats(r)) == len(r) else [float("nan")] * len(r) for r in spec.get("matrix", [])]
        xl, yl = [str(x) for x in spec.get("x_labels", [])], [str(y) for y in spec.get("y_labels", [])]
        if matrix and len(matrix) == len(yl) and all(len(r) == len(xl) for r in matrix):
            im = ax.imshow(matrix, cmap="viridis", aspect="auto")
            ax.set_xticks(range(len(xl)), xl)
            ax.set_yticks(range(len(yl)), yl)
            flat = [v for r in matrix for v in r if not math.isnan(v)]
            lo, hi = (min(flat), max(flat)) if flat else (0.0, 1.0)
            for yi, row in enumerate(matrix):
                for xi, v in enumerate(row):
                    if not math.isnan(v):
                        ax.text(xi, yi, f"{v:g}", ha="center", va="center", fontsize=7.5,
                                color="white" if (v - lo) / ((hi - lo) or 1.0) < 0.6 else "#222")
            fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02, label=spec.get("c_label", ""))
            drawn = 1

    if not drawn:
        plt.close(fig)
        raise ValueError(f"chart {kind} thiếu dữ liệu hợp lệ")

    if spec.get("x_label"):
        ax.set_xlabel(spec["x_label"])
    if spec.get("y_label"):
        ax.set_ylabel(spec["y_label"])
    if kind == "heatmap":
        ax.spines[:].set_visible(False)
    else:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(linestyle=":", alpha=0.6)
        ax.set_axisbelow(True)
    if kind in ("xyline", "scatter", "cdf", "histogram") and len([s for s in series if s.get("name")]) > 1:
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=min(len(series), 4), frameon=True, fontsize=8, edgecolor="#bbb")
    fig.tight_layout()

    return finish_figure(fig, fmt)
