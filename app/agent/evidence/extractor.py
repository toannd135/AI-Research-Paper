"""Phase 1 — trích xuất kết quả định lượng CÓ CẤU TRÚC từ evidence (PDF), không để LLM tự điền.

LLM chỉ đề xuất bản ghi từ đoạn văn đã cho; mỗi bản ghi chỉ được giữ khi giá trị xuất hiện NGUYÊN VĂN trong chunk của
đúng paper đó (trang lấy từ chunk, không lấy từ LLM). Dataset/version/split/vùng không thấy trong chunk → None.
Metric hiệu quả (Params, GFLOPs, inference time) là bản ghi riêng. Thiếu thông tin thì để trống, không suy diễn.
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import asdict
from typing import Any

from app.agent.evidence.quant_check import ResultRecord
from app.ai.llm_gateway.base import LLMGateway, Message

logger = logging.getLogger(__name__)

BATCH_SIZE = 3  # số paper mỗi lần gọi LLM (lô nhỏ → ít bị timeout, đầu ra JSON ngắn hơn)
MAX_CHUNKS_PER_PAPER = 4
BATCH_TIMEOUT_S = 120  # một lô chậm không được chặn cả bài
MAX_ATTEMPTS = 2  # thử lại 1 lần khi lô quá giờ
TOTAL_BUDGET_S = 600  # quá ngân sách thì bỏ các lô còn lại (ledger thưa hơn, không bịa)
MAX_CHARS_PER_CHUNK = 1800
_KEY_RE = re.compile(r"\b(dice|hd95|hausdorff|iou|params?|parameters|gflops|flops|inference|latency)\b", re.I)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
_REGIONS = {"wt": "WT", "tc": "TC", "et": "ET", "whole tumor": "WT", "tumor core": "TC", "enhancing tumor": "ET", "avg": "AVG", "average": "AVG", "mean": "AVG"}

_PROMPT = (
    "Extract quantitative results from the passages. Return ONLY a JSON list; each item: "
    '{"paper_id","model","dataset","dataset_version","split","region","metric","value","unit","variant","modality","table"}. '
    "metric is one of Dice, HD95, Params, GFLOPs, InferenceTime, IoU. region is WT/TC/ET/AVG or null. unit is ratio|percent|mm|M|G|ms. "
    "value must be the number EXACTLY as printed in the passage. Use null for any field the passage does not state; "
    "never guess, convert or compute. variant = ablation variant name (e.g. 'w/o X') or null for the full model. "
    "If there are no numeric results, return []."
)


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


def _verify(item: dict[str, Any], chunks: list[dict[str, Any]]) -> ResultRecord | None:
    raw = _s(item.get("value"))
    metric = _s(item.get("metric"))
    if not raw or not metric or not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        return None
    hits = [c for c in chunks if re.search(rf"(?<![\d.]){re.escape(raw)}(?![\d])", c["text"])]
    if not hits:
        return None  # giá trị không có nguyên văn trong PDF → bỏ
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
    )


def extract_results(evidence: list[Any], gateway: LLMGateway, model_name: str | None = None) -> list[ResultRecord]:
    """Trích các `ResultRecord` đã kiểm chứng nguyên văn; lỗi LLM/parse của một lô không làm hỏng lô khác."""
    by_paper = _paper_chunks(evidence)
    ids = list(by_paper)
    records: list[ResultRecord] = []
    n_batches = -(-len(ids) // BATCH_SIZE)
    started = time.monotonic()
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        for i in range(0, len(ids), BATCH_SIZE):
            no = i // BATCH_SIZE + 1
            if time.monotonic() - started > TOTAL_BUDGET_S:
                logger.warning("Trích xuất: hết ngân sách %ds, bỏ %d lô còn lại", TOTAL_BUDGET_S, n_batches - no + 1)
                break
            batch = ids[i : i + BATCH_SIZE]
            passages = "\n\n".join(
                f"[paper_id={pid}] (page {c['page']})\n{c['text'][:MAX_CHARS_PER_CHUNK]}" for pid in batch for c in by_paper[pid]
            )
            t0 = time.monotonic()
            logger.info("Trích xuất lô %d/%d (%d paper, %d ký tự)...", no, n_batches, len(batch), len(passages))
            resp = None
            for attempt in range(1, MAX_ATTEMPTS + 1):
                future = pool.submit(
                    gateway.generate,
                    messages=[Message(role="system", content=_PROMPT), Message(role="user", content=passages)],
                    model_name=model_name,
                )
                try:
                    resp = future.result(timeout=BATCH_TIMEOUT_S)
                    break
                except FutureTimeout:
                    logger.warning("Trích xuất lô %d/%d quá %ds (lần %d/%d)", no, n_batches, BATCH_TIMEOUT_S, attempt, MAX_ATTEMPTS)
                    pool.shutdown(wait=False, cancel_futures=True)
                    pool = ThreadPoolExecutor(max_workers=1)
                    if time.monotonic() - started > TOTAL_BUDGET_S:
                        break
                except (RuntimeError, ValueError, OSError):
                    logger.exception("Trích xuất lô %d/%d lỗi, bỏ qua lô này", no, n_batches)
                    break
            if resp is None:
                logger.warning("Trích xuất lô %d/%d: bỏ lô này", no, n_batches)
                continue
            got = 0
            for item in _parse_json_list(resp.text):
                pid = str(item.get("paper_id") or "")
                if pid not in by_paper:
                    continue
                rec = _verify(item, by_paper[pid])
                if rec is not None:
                    records.append(rec)
                    got += 1
            logger.info("Trích xuất lô %d/%d xong sau %.0fs: giữ %d bản ghi", no, n_batches, time.monotonic() - t0, got)
    finally:
        pool.shutdown(wait=False)
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
