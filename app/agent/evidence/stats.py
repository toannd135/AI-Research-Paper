"""Kiểm định ý nghĩa thống kê cho so sánh giữa phương pháp đề xuất và baseline từ số liệu từng lần chạy (seed/fold)."""

from __future__ import annotations

import math
from typing import Any

ALPHA = 0.05
_LOWER_IS_BETTER = ("latency", "loss", "error", "time", "cost", "rmse", "mae", "mse", "fid", "lpips", "memory", "flops", "params", "overhead", "fpr")


def lower_is_better(metric: str | None) -> bool:
    return any(k in (metric or "").lower() for k in _LOWER_IS_BETTER)


def compare_runs(proposed: list[float], baseline: list[float], metric: str | None = None) -> dict[str, Any] | None:
    """Welch t-test + Cohen's d. Trả None nếu một bên < 2 lần chạy (không đủ để kiểm định)."""
    if len(proposed) < 2 or len(baseline) < 2:
        return None
    from scipy import stats

    mean_p, mean_b = sum(proposed) / len(proposed), sum(baseline) / len(baseline)
    var_p = sum((x - mean_p) ** 2 for x in proposed) / (len(proposed) - 1)
    var_b = sum((x - mean_b) ** 2 for x in baseline) / (len(baseline) - 1)
    pooled = math.sqrt((var_p + var_b) / 2)
    if pooled == 0:
        # Không có phương sai: kết quả giống hệt nhau mỗi lần chạy, t-test không xác định.
        p_value = 0.0 if mean_p != mean_b else 1.0
        effect = math.inf if mean_p != mean_b else 0.0
    else:
        p_value = float(stats.ttest_ind(proposed, baseline, equal_var=False).pvalue)
        effect = (mean_p - mean_b) / pooled
    improvement = (mean_b - mean_p) if lower_is_better(metric) else (mean_p - mean_b)
    return {
        "n_proposed": len(proposed),
        "n_baseline": len(baseline),
        "mean_proposed": mean_p,
        "mean_baseline": mean_b,
        "p_value": p_value,
        "effect_size": effect,
        "favors_proposed": improvement > 0,
        "significant": p_value < ALPHA and improvement > 0,
    }
