"""Kiểm tra tính so sánh được của kết quả định lượng (Dice, HD95...) giữa các nghiên cứu.

Không để LLM quyết định hai kết quả có so sánh được hay không: mỗi kết quả là một `ResultRecord`
có cấu trúc và `compare` áp dụng quy tắc cố định. Thiếu thông tin thì KHÔNG suy diễn (UNVERIFIED).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from itertools import combinations

COMPARABLE = "COMPARABLE"
CONDITIONALLY_COMPARABLE = "CONDITIONALLY_COMPARABLE"
NOT_COMPARABLE = "NOT_COMPARABLE"
UNVERIFIED = "UNVERIFIED"

_SEVERITY = {COMPARABLE: 0, CONDITIONALLY_COMPARABLE: 1, UNVERIFIED: 2, NOT_COMPARABLE: 3}


@dataclass(frozen=True)
class ResultRecord:
    paper_id: str
    model: str
    dataset: str | None
    dataset_version: str | None
    split: str | None
    region: str | None
    metric: str
    value: float
    unit: str | None = None  # "ratio" (0-1) | "percent" (0-100) | "mm"
    metric_definition: str | None = None
    modality: tuple[str, ...] = ()
    preprocessing: str | None = None
    source_page: int | None = None
    source_table: str | None = None
    variant: str | None = None  # tên biến thể ablation (None = mô hình đầy đủ)
    spread: float | None = None  # độ lệch in nguyên văn kèm giá trị (± x); None = nguồn không báo
    spread_type: str | None = None  # "SD" | "SE" | "CI95" — chỉ có khi spread có


def _norm(value: str | None) -> str | None:
    return re.sub(r"\s+", " ", value).strip().lower() if isinstance(value, str) and value.strip() else None


def validate_record(rec: ResultRecord) -> list[str]:
    """Lỗi nội tại của một kết quả; danh sách rỗng = hợp lệ."""
    problems: list[str] = []
    if not rec.paper_id or (rec.source_page is None and not rec.source_table):
        problems.append("không có nguồn PDF (trang/bảng) cho giá trị này")
    metric = (_norm(rec.metric) or "").replace(" ", "")
    if metric in ("dice", "dicescore", "dsc"):
        upper = {"ratio": 1.0, "percent": 100.0}.get(rec.unit or "")
        if upper is None:
            problems.append("Dice thiếu đơn vị gốc (ratio/percent), không tự chuyển đổi")
        elif not 0.0 <= rec.value <= upper:
            problems.append(f"Dice {rec.value} ngoài miền hợp lệ [0, {upper:g}]")
    if metric in ("hd95", "hd", "hausdorff", "hausdorff95") and rec.value < 0:
        problems.append(f"{rec.metric} không được âm ({rec.value})")
    return problems


def compare(a: ResultRecord, b: ResultRecord) -> tuple[str, list[str]]:
    """So sánh hai kết quả; trả về (trạng thái, lý do). Trạng thái xấu nhất thắng."""
    verdicts: list[tuple[str, str]] = []
    for rec in (a, b):
        if any("nguồn" in p for p in validate_record(rec)):
            verdicts.append((NOT_COMPARABLE, f"{rec.paper_id or '?'}: không có nguồn PDF"))

    def strict(label: str, x: str | None, y: str | None) -> None:
        nx, ny = _norm(x), _norm(y)
        if nx is None or ny is None:
            verdicts.append((UNVERIFIED, f"thiếu thông tin {label}"))
        elif nx != ny:
            verdicts.append((NOT_COMPARABLE, f"khác {label}: {x} ≠ {y}"))

    if _norm(a.metric) != _norm(b.metric):
        verdicts.append((NOT_COMPARABLE, f"khác metric: {a.metric} ≠ {b.metric}"))
    strict("dataset", a.dataset, b.dataset)
    strict("split", a.split, b.split)
    from app.agent.domains import is_mri

    if is_mri():  # BraTS: phiên bản (năm) và vùng WT/TC/ET bắt buộc
        strict("phiên bản dataset", a.dataset_version, b.dataset_version)
        strict("vùng/lớp", a.region, b.region)
    else:  # chế độ khác: không có vùng; phiên bản chỉ chặn khi cả hai cùng ghi mà khác nhau
        va, vb = _norm(a.dataset_version), _norm(b.dataset_version)
        if va and vb and va != vb:
            verdicts.append((NOT_COMPARABLE, f"khác phiên bản dataset: {a.dataset_version} ≠ {b.dataset_version}"))
        elif (va is None) != (vb is None):
            verdicts.append((CONDITIONALLY_COMPARABLE, "một nguồn không ghi phiên bản dataset"))
    if _norm(a.unit) != _norm(b.unit):
        verdicts.append((NOT_COMPARABLE, f"khác đơn vị gốc: {a.unit} ≠ {b.unit} (không tự chuyển đổi)"))
    if _norm(a.metric_definition) and _norm(b.metric_definition) and _norm(a.metric_definition) != _norm(b.metric_definition):
        verdicts.append((NOT_COMPARABLE, "khác định nghĩa metric"))
    if sorted(a.modality) != sorted(b.modality):
        verdicts.append((CONDITIONALLY_COMPARABLE, f"khác modality: {list(a.modality)} ≠ {list(b.modality)}"))
    if _norm(a.preprocessing) != _norm(b.preprocessing):
        verdicts.append((CONDITIONALLY_COMPARABLE, "khác tiền xử lý/giao thức huấn luyện hoặc chưa ghi rõ"))

    if not verdicts:
        return COMPARABLE, []
    worst = max(verdicts, key=lambda v: _SEVERITY[v[0]])[0]
    return worst, [reason for status, reason in verdicts if status == worst]


def group_comparable(records: list[ResultRecord]) -> dict:
    """Chia kết quả thành các nhóm được phép đặt chung một biểu đồ/bảng xếp hạng.

    Trả về {"groups": {khóa: [record]}, "conditional": [khóa], "unverified": [...], "rejected": [(record, lý do)]}.
    """
    rejected: list[tuple[ResultRecord, list[str]]] = []
    unverified: list[ResultRecord] = []
    groups: dict[tuple, list[ResultRecord]] = {}
    for rec in records:
        problems = validate_record(rec)
        if problems:
            rejected.append((rec, problems))
            continue
        key = (_norm(rec.dataset), _norm(rec.dataset_version), _norm(rec.split), _norm(rec.region), _norm(rec.metric), _norm(rec.unit))
        from app.agent.domains import is_mri

        # MRI: dataset/phiên bản/split/vùng/metric đều bắt buộc; chế độ khác chỉ cần dataset/split/metric
        if None in ((key[:5]) if is_mri() else (key[0], key[2], key[4])):
            unverified.append(rec)
            continue
        groups.setdefault(key, []).append(rec)
    conditional = [
        key for key, items in groups.items()
        if any(compare(x, y)[0] == CONDITIONALLY_COMPARABLE for x, y in combinations(items, 2))
    ]
    return {"groups": groups, "conditional": conditional, "unverified": unverified, "rejected": rejected}


_REGION_RE = re.compile(r"\b(WT|TC|ET|whole tumou?r|tumou?r core|enhancing tumou?r)\b", re.IGNORECASE)
_REGION_CANON = {"whole tumor": "WT", "whole tumour": "WT", "tumor core": "TC", "tumour core": "TC", "enhancing tumor": "ET", "enhancing tumour": "ET"}
_METRIC_RE = re.compile(r"\b(Dice|HD95|Hausdorff|IoU|mIoU|Precision|Recall|Sensitivity|Specificity)\b", re.IGNORECASE)


def check_chart_block(raw_json: str) -> list[str]:
    """Biểu đồ không được trộn nhiều vùng (WT/TC/ET) hoặc nhiều metric khác bản chất trên cùng một trục."""
    try:
        spec = json.loads(raw_json)
    except ValueError:
        return []
    if not isinstance(spec, dict):
        return []
    series = spec.get("series") if isinstance(spec.get("series"), list) else []
    names = " ".join(str(s.get("name", "")) for s in series if isinstance(s, dict))
    text = f"{spec.get('caption', '')} {names} {spec.get('y_label', '')}"
    from app.agent.domains import is_mri

    # vùng u WT/TC/ET chỉ có nghĩa ở chế độ MRI não
    regions = {_REGION_CANON.get(m.lower(), m.upper()) for m in _REGION_RE.findall(text)} if is_mri() else set()
    metrics = {m.lower() for m in _METRIC_RE.findall(f"{names} {spec.get('y_label', '')}")}
    problems: list[str] = []
    if len(regions) > 1:
        problems.append(f"biểu đồ trộn nhiều vùng phân đoạn ({', '.join(sorted(regions))}) trên cùng một trục")
    if len(metrics) > 1:
        problems.append(f"biểu đồ trộn nhiều metric ({', '.join(sorted(metrics))}) trên cùng một trục")
    return problems
