"""Scientific Quality Gate: gom kiểm tra tham khảo, tính so sánh được và truy vết số liệu thành validation_report.

Chạy trên văn bản CHƯA đánh số lại [n] (khớp state["citations"]). Gate chỉ báo cáo và quyết định `passed`;
không bao giờ sửa số liệu hay nâng trạng thái bằng LLM. `blocking` liệt kê lỗi đáng chặn xuất bản.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.agent.evidence.consistency_check import check_consistency, check_review_claims
from app.agent.evidence.display_check import check_display_items
from app.agent.evidence.quant_check import check_chart_block
from app.agent.evidence.reference_check import (
    CONFLICT,
    INVALID,
    PARTIALLY_VERIFIED,
    PREPRINT,
    UNVERIFIED,
    verify_references,
)
from app.agent.evidence.rq_sync import check_rq_definitions
from app.agent.evidence.traceability import (
    NO_CITATION,
    TRACED,
    UNTRACED,
    extract_numeric_claims,
    pdf_sha256,
    trace_claims,
)
from app.core.config import get_settings

_SURVEY_TITLE_RE = re.compile(r"\b(?:survey|review|overview|state of the art|state-of-the-art|tutorial)\b", re.IGNORECASE)
_CHART_RE = re.compile(r"```chart\s*\n(.*?)```", re.DOTALL)
_MAX_LISTED = 40  # số mục chi tiết tối đa trong báo cáo (tổng số vẫn đếm đủ)

logger = logging.getLogger(__name__)


def _build_sources(citations: list[Any], evidence: list[Any]) -> dict[int, dict[str, Any]]:
    upload_dir = Path(get_settings().upload_dir)
    chunks_by_paper: dict[str, list[dict[str, Any]]] = {}
    for sc in evidence:
        chunk = getattr(sc, "chunk", sc)
        chunks_by_paper.setdefault(chunk.paper_id, []).append({"page": chunk.page, "text": chunk.text})
    hashes: dict[str, str | None] = {}
    sources: dict[int, dict[str, Any]] = {}
    for n, cit in enumerate(citations, start=1):
        pid = cit.paper_id
        if pid not in hashes:
            hashes[pid] = pdf_sha256(upload_dir / f"{pid}.pdf")
        sources[n] = {"paper_id": pid, "chunks": chunks_by_paper.get(pid, []), "pdf_sha256": hashes[pid]}
    return sources


def run_quality_gate(state: dict[str, Any], text: str, catalog: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    from app.agent.evidence.citation_cleaner import _local_catalog

    citations = state.get("citations", [])
    catalog = _local_catalog() if catalog is None else catalog
    cited_numbers = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    cited_ids = [citations[n - 1].paper_id for n in sorted(cited_numbers) if 1 <= n <= len(citations)]

    references = verify_references(cited_ids, catalog)
    if get_settings().reference_external_verify:
        from app.agent.evidence.external_verify import external_verify

        references = external_verify(references, catalog)
    claims = extract_numeric_claims(text)
    evidence_records = trace_claims(claims, _build_sources(citations, state.get("evidence", [])))
    chart_problems = [p for raw in _CHART_RE.findall(text) for p in check_chart_block(raw)]

    trace_counts = {s: sum(1 for r in evidence_records if r["status"] == s) for s in (TRACED, UNTRACED, NO_CITATION)}
    blocking: list[str] = []
    warnings: list[str] = []
    for res in references["references"]:
        if res["status"] in (INVALID, CONFLICT):
            blocking.append(f"reference {res['paper_id']}: {res['status']} — {'; '.join(res['issues'])}")
        elif res["status"] == UNVERIFIED:
            warnings.append(f"reference {res['paper_id']}: UNVERIFIED — {'; '.join(res['issues'])}")
    if trace_counts[UNTRACED] or trace_counts[NO_CITATION]:
        blocking.append(
            f"{trace_counts[UNTRACED]} giá trị không tìm thấy trong nguồn được trích và {trace_counts[NO_CITATION]} giá trị không có [n] "
            "trong bảng/biểu đồ — không được dùng làm bảng kết quả"
        )
    blocking += [f"so sánh không tương đương: {p}" for p in chart_problems]
    rq_problems = check_rq_definitions(text)
    blocking += [f"RQ không nhất quán: {p}" for p in rq_problems]
    incomplete = [r for r in references["references"] if r["status"] == PARTIALLY_VERIFIED]
    if incomplete:
        warnings.append(f"{len(incomplete)}/{len(references['references'])} reference thiếu metadata ({', '.join(sorted({m for r in incomplete for m in r['missing']}))}) — cần bổ sung/đối chiếu nguồn")
    preprints = references["publication"].get(PREPRINT, 0)
    if preprints:
        warnings.append(f"{preprints}/{len(references['references'])} reference là preprint/arXiv, chưa chắc đã bình duyệt — ghi rõ khi dùng làm bằng chứng")
    from app.agent.evidence.review_protocol import load_protocol, validate_protocol

    protocol = load_protocol()
    protocol_problems = validate_protocol(protocol, len(catalog) or None) if protocol else []
    if protocol_problems:
        warnings.append(f"review_protocol.json không hợp lệ, KHÔNG dùng (bài giữ mô tả retrieval coverage): {'; '.join(protocol_problems[:6])}")
    declared = protocol["review_type"] if protocol and not protocol_problems else None
    review_claims = check_review_claims(text, declared)
    blocking += [f"tuyên bố sai về quy trình tổng quan: {p}" for p in review_claims]
    if state.get("research_mode", "survey") != "novel_research" and not any(
        _SURVEY_TITLE_RE.search(str((catalog.get(pid) or {}).get("title", ""))) for pid in cited_ids
    ):
        warnings.append(
            "novelty: bài không cite survey/review trước nào (theo tiêu đề catalog) — không chứng minh được điểm mới so với các survey đã có; "
            "thêm các survey liên quan vào kho rồi chạy lại"
        )
    if len(cited_numbers) < 2:
        warnings.append("bài cite ít hơn 2 nguồn")
    from app.agent.evidence.coverage import full_coverage_applies, uncited_papers

    available_ids = {getattr(c, "paper_id", None) for c in citations} - {None, ""}
    if full_coverage_applies(len(available_ids)):
        missing = uncited_papers(citations, text)
        if missing:
            titles = [(catalog.get(pid) or {}).get("title") or pid for pid in missing]
            warnings.append(f"độ phủ kho: {len(missing)}/{len(available_ids)} paper trong kho chưa được cite ({'; '.join(t[:60] for t in titles[:8])}{'…' if len(titles) > 8 else ''})")
    from app.agent.research_model import contribution_profile

    display = check_display_items(text, state.get("paper_type") or contribution_profile(state)["paper_type"])
    warnings += display["warnings"]
    consistency = check_consistency(text)
    warnings += [f"nhất quán: {w}" for w in consistency]
    science_qa, study_attrs = _science_qa(state, text)
    warnings += [f"science QA: {w}" for w in science_qa]

    return {
        "passed": not blocking,
        "blocking": blocking,
        "warnings": warnings,
        "references": references,
        "traceability": {
            "counts": trace_counts,
            "untraced": [r for r in evidence_records if r["status"] != TRACED][:_MAX_LISTED],
            "traced_sample": [r for r in evidence_records if r["status"] == TRACED][:_MAX_LISTED],
        },
        "comparability": {"chart_problems": chart_problems},
        "research_questions": {"problems": rq_problems},
        "review_claims": {"problems": review_claims, "declared_review_type": declared, "protocol_problems": protocol_problems},
        "display_items": display,
        "consistency": consistency,
        "science_qa": science_qa,
        # câu nguyên văn + trang làm căn cứ cho bảng hồ sơ nghiên cứu, để người dùng đối chiếu với PDF
        "study_profile": study_attrs,
    }


def _science_qa(state: dict[str, Any], text: str) -> tuple[list[str], dict[str, Any]]:
    from app.agent.evidence.extractor import records_from_dicts
    from app.agent.evidence.science_qa import run_science_qa
    from app.agent.evidence.study_profile import study_attributes

    paper_to_n: dict[str, int] = {}
    for n, cit in enumerate(state.get("citations", []), start=1):
        paper_to_n.setdefault(getattr(cit, "paper_id", ""), n)
    try:
        records = records_from_dicts(state.get("results") or [])
    except TypeError:
        logger.exception("results trong state sai cấu trúc, Science QA bỏ qua record")
        records = []
    attrs = study_attributes(state.get("evidence", []))
    return run_science_qa(text, records, paper_to_n, attrs), attrs


def merge_structure_issues(report: dict[str, Any] | None, blocking: list[str], warnings: list[str]) -> dict[str, Any] | None:
    """Gộp lỗi cấu trúc phát hiện SAU khi đánh số lại bảng/hình (gate chính chạy trước bước đó) vào validation_report."""
    if report is None or not (blocking or warnings):
        return report
    merged_blocking = [*report["blocking"], *blocking]
    return {**report, "blocking": merged_blocking, "warnings": [*report["warnings"], *warnings], "passed": not merged_blocking}
