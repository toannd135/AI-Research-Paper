"""Phase 1 — trích xuất kết quả định lượng CÓ CẤU TRÚC từ evidence (PDF), không để LLM tự điền.

LLM chỉ đề xuất bản ghi từ đoạn văn đã cho; mỗi bản ghi chỉ được giữ khi giá trị xuất hiện NGUYÊN VĂN trong chunk của
đúng paper đó (trang lấy từ chunk, không lấy từ LLM). Dataset/version/split/vùng không thấy trong chunk → None.
Metric hiệu quả (Params, GFLOPs, inference time) là bản ghi riêng. Thiếu thông tin thì để trống, không suy diễn.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app.agent.evidence.quant_check import ResultRecord
from app.ai.llm_gateway.base import LLMGateway, LLMGatewayError, Message

logger = logging.getLogger(__name__)

BATCH_SIZE = 3  # số paper mỗi lần gọi LLM (lô nhỏ → ít bị timeout, đầu ra JSON ngắn hơn)
MAX_CHUNKS_PER_PAPER = 4
MAX_ATTEMPTS = 3  # thử lại khi LLM lỗi; không đặt timeout từng lệnh gọi (chờ LLM trả lời đủ từng lô)
# Ngân sách tổng cho cả bước trích xuất: quá mức này thì bỏ các lô còn lại để graph đi tiếp
# (tránh task bị Celery kill khi LLM bị rate limit). Quyết định 2026-11-09, thay cho "chạy đủ mọi lô".
MAX_TOTAL_SECONDS = 1500.0
MAX_CHARS_PER_CHUNK = 1800
CACHE_ENABLED = True  # cache phản hồi LLM thô theo lô (khóa = prompt + model + đoạn văn); test tắt mặc định
_KEY_RE = re.compile(
    r"\b(dice|hd95|hausdorff|iou|params?|parameters|gflops|flops|inference|latency"
    r"|auc|auroc|eer|acc|accuracy|f1|average precision)\b",
    re.I,
)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_REGIONS = {"wt": "WT", "tc": "TC", "et": "ET", "whole tumor": "WT", "tumor core": "TC", "enhancing tumor": "ET", "avg": "AVG", "average": "AVG", "mean": "AVG"}

_PROMPT = (
    "Extract quantitative results from the passages. Return ONLY a JSON list; each item: "
    '{"paper_id","model","dataset","dataset_version","split","region","metric","value","unit","variant","modality","table","spread","spread_type"}. '
    "metric is one of Dice, HD95, IoU, AUC, EER, ACC, F1, AP, Params, GFLOPs, InferenceTime. region is WT/TC/ET/AVG or null "
    "(null for non-segmentation metrics). unit is ratio|percent|mm|M|G|ms. "
    "For detection tasks, put the evaluation setting (e.g. 'cross-dataset', 'in-domain', 'frame-level') in split only if printed. "
    "value must be the number EXACTLY as printed in the passage. Use null for any field the passage does not state; "
    "never guess, convert or compute. variant = ablation variant name (e.g. 'w/o X') or null for the full model. "
    "spread = the number printed after '±' for that value (std/CI half-width) EXACTLY as printed, else null; "
    "spread_type is SD, SE or CI95 only if the passage says which, else null. "
    "If there are no numeric results, return []."
)
_SPREAD_TYPES = {"SD", "SE", "CI95"}


def _paper_chunks(evidence: list[Any]) -> dict[str, list[dict[str, Any]]]:
    by_paper: dict[str, list[dict[str, Any]]] = {}
    for sc in evidence:
        c = getattr(sc, "chunk", sc)
        text = getattr(c, "text", "") or ""
        if _KEY_RE.search(text) and _NUM_RE.search(text):
            by_paper.setdefault(c.paper_id, []).append({"page": getattr(c, "page", None), "text": text, "score": len(_KEY_RE.findall(text))})
    for chunks in by_paper.values():
        chunks.sort(key=lambda x: -x["score"])
        del chunks[MAX_CHUNKS_PER_PAPER:]
    return by_paper


def _parse_json_list(text: str) -> list[dict[str, Any]]:
    m = re.search(r"\[.*\]", text, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return []
    return [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []


def _s(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _grounded_in(chunks: list[dict[str, Any]], needle: str | None) -> bool:
    return bool(needle) and any(needle.lower() in c["text"].lower() for c in chunks)


def _verified_spread(item: dict[str, Any], hits: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    """Giữ spread chỉ khi có loại sai số hợp lệ và con số đứng ngay sau '±' trong chunk (không suy diễn)."""
    raw, kind = _s(item.get("spread")), (_s(item.get("spread_type")) or "").upper().replace(" ", "").replace("%", "")
    kind = {"STD": "SD", "STDDEV": "SD", "CI": "CI95", "CI95": "CI95", "95CI": "CI95"}.get(kind, kind)
    if not raw or kind not in _SPREAD_TYPES or not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return None, None
    if not any(re.search(rf"(?:±|\+/-|\+-)\s*{re.escape(raw)}(?![\d])", c["text"]) for c in hits):
        return None, None
    return float(raw), kind


def _verify(item: dict[str, Any], chunks: list[dict[str, Any]]) -> ResultRecord | None:
    raw = _s(item.get("value"))
    metric = _s(item.get("metric"))
    if not raw or not metric or not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return None
    hits = [c for c in chunks if re.search(rf"(?<![\d.]){re.escape(raw)}(?![\d])", c["text"])]
    if not hits:
        return None  # giá trị không có nguyên văn trong PDF → bỏ
    spread, spread_type = _verified_spread(item, hits)
    raw_region = _s(item.get("region"))
    region = _REGIONS.get(raw_region.lower()) if raw_region else None
    modality = item.get("modality")
    mods = tuple(str(x).strip() for x in modality if str(x).strip()) if isinstance(modality, list) else ()
    return ResultRecord(
        paper_id=str(item.get("paper_id") or ""),
        model=_s(item.get("model")) or "",
        dataset=_s(item.get("dataset")) if _grounded_in(chunks, _s(item.get("dataset"))) else None,
        dataset_version=_s(item.get("dataset_version")) if _grounded_in(chunks, _s(item.get("dataset_version"))) else None,
        split=_s(item.get("split")) if _grounded_in(chunks, _s(item.get("split"))) else None,
        region=region,
        metric=metric,
        value=float(raw),
        unit=_s(item.get("unit")),
        modality=mods,
        source_page=hits[0]["page"],
        source_table=_s(item.get("table")) if _grounded_in(hits, _s(item.get("table"))) else None,
        variant=_s(item.get("variant")),
        spread=spread,
        spread_type=spread_type,
    )


def _cache_dir() -> Path:
    from app.core.config import get_settings

    return Path(get_settings().upload_dir).parent / "cache" / "extract"


def _cache_key(passages: str, model_name: str | None) -> str:
    return hashlib.sha256("\x00".join((_PROMPT, model_name or "", passages)).encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    """Đọc phản hồi LLM thô đã lưu của lô; không đọc được thì coi như chưa có cache."""
    if not CACHE_ENABLED:
        return None
    try:
        return (_cache_dir() / f"{key}.txt").read_text(encoding="utf-8")
    except OSError:
        return None


def _cache_put(key: str, text: str) -> None:
    """Lưu phản hồi LLM thô (ghi nguyên tử); lỗi ghi không làm hỏng việc trích xuất."""
    if not CACHE_ENABLED:
        return
    try:
        d = _cache_dir()
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / f"{key}.tmp"
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(d / f"{key}.txt")
    except OSError:
        logger.warning("Không ghi được cache trích xuất", exc_info=True)


def _call_llm(gateway: LLMGateway, passages: str, model_name: str | None, no: int, n_batches: int) -> str | None:
    for attempt in range(1, MAX_ATTEMPTS + 1):  # không đặt giới hạn thời gian: chờ LLM trả lời đủ từng lô
        try:
            resp = gateway.generate(
                messages=[Message(role="system", content=_PROMPT), Message(role="user", content=passages)],
                model_name=model_name,
            )
            return resp.text
        except (LLMGatewayError, RuntimeError, ValueError, OSError):
            logger.exception("Trích xuất lô %d/%d lỗi (lần %d/%d)", no, n_batches, attempt, MAX_ATTEMPTS)
    return None


def extract_results(
    evidence: list[Any],
    gateway: LLMGateway,
    model_name: str | None = None,
    max_seconds: float | None = MAX_TOTAL_SECONDS,
) -> list[ResultRecord]:
    """Trích các `ResultRecord` đã kiểm chứng nguyên văn; lỗi LLM/parse của một lô không làm hỏng lô khác.

    Quá `max_seconds` (None = không giới hạn) thì bỏ các lô còn lại và trả về những gì đã trích được.
    """
    by_paper = _paper_chunks(evidence)
    ids = list(by_paper)
    records: list[ResultRecord] = []
    n_batches = -(-len(ids) // BATCH_SIZE)
    start = time.monotonic()
    for i in range(0, len(ids), BATCH_SIZE):
        no = i // BATCH_SIZE + 1
        if max_seconds is not None and time.monotonic() - start > max_seconds:
            logger.warning("Trích xuất: quá ngân sách %.0fs, bỏ %d lô còn lại (từ lô %d/%d)", max_seconds, n_batches - no + 1, no, n_batches)
            break
        batch = ids[i : i + BATCH_SIZE]
        passages = "\n\n".join(
            f"[paper_id={pid}] (page {c['page']})\n{c['text'][:MAX_CHARS_PER_CHUNK]}" for pid in batch for c in by_paper[pid]
        )
        t0 = time.monotonic()
        logger.info("Trích xuất lô %d/%d (%d paper, %d ký tự)...", no, n_batches, len(batch), len(passages))
        key = _cache_key(passages, model_name)
        cached = _cache_get(key)
        if cached is not None:
            logger.info("Trích xuất lô %d/%d: dùng cache", no, n_batches)
            text = cached
        else:
            text = _call_llm(gateway, passages, model_name, no, n_batches)
            if text is None:
                logger.warning("Trích xuất lô %d/%d: lỗi sau %d lần thử, bỏ lô này", no, n_batches, MAX_ATTEMPTS)
                continue
            _cache_put(key, text)
        got = 0
        for item in _parse_json_list(text):
            pid = str(item.get("paper_id") or "")
            if pid not in by_paper:
                continue
            rec = _verify(item, by_paper[pid])
            if rec is not None:
                records.append(rec)
                got += 1
        logger.info("Trích xuất lô %d/%d xong sau %.0fs: giữ %d bản ghi", no, n_batches, time.monotonic() - t0, got)
    logger.info("Trích xuất %d bản ghi định lượng từ %d paper", len(records), len(ids))
    return list(dict.fromkeys(records))


def records_to_dicts(records: list[ResultRecord]) -> list[dict[str, Any]]:
    return [asdict(r) for r in records]


def records_from_dicts(rows: list[dict[str, Any]]) -> list[ResultRecord]:
    out = []
    for r in rows:
        r = dict(r)
        r["modality"] = tuple(r.get("modality") or ())
        out.append(ResultRecord(**r))
    return out
