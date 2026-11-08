"""Chặn xuất bản publication-ready khi Scientific Quality Gate báo lỗi BLOCKING (validation_report.passed=false).

Không có tệp validation (task cũ/không chạy gate) → không chặn. `draft=True` cho phép tải bản nháp có chủ đích.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings


def load_blocking(task_id: str) -> list[str]:
    """Danh sách lỗi chặn của task; rỗng nếu đạt hoặc chưa có validation_report."""
    path = Path(get_settings().upload_dir) / "validation" / f"{task_id}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict) or data.get("passed", True):
        return []
    return [str(x) for x in data.get("blocking", [])] or ["validation_report.passed=false"]
