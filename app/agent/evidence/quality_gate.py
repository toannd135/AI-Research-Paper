"""Scientific Quality Gate: gom kiểm tra tham khảo, tính so sánh được và truy vết số liệu thành validation_report.

Chạy trên văn bản CHƯA đánh số lại [n] (khớp state["citations"]). Gate chỉ báo cáo và quyết định `passed`;
không bao giờ sửa số liệu hay nâng trạng thái bằng LLM. `blocking` liệt kê lỗi đáng chặn xuất bản.
"""

from __future__ import annotations

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

_CHART_RE = re.compile(r"```chart\s*\n(.*?)```", re.DOTALL)
_MAX_LISTED = 40  # số mục chi tiết tối đa trong báo cáo (tổng số vẫn đếm đủ)


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
    review_claims = check_review_claims(text)
    blocking += [f"tuyên bố sai về quy trình tổng quan: {p}" for p in review_claims]
    if len(cited_numbers) < 2:
        warnings.append("bài cite ít hơn 2 nguồn")
    from app.agent.research_model import contribution_profile

    display = check_display_items(text, state.get("paper_type") or contribution_profile(state)["paper_type"])
    warnings += display["warnings"]
    consistency = check_consistency(text)
    warnings += [f"nhất quán: {w}" for w in consistency]

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
        "review_claims": {"problems": review_claims},
        "display_items": display,
        "consistency": consistency,
    }


def merge_structure_issues(report: dict[str, Any] | None, blocking: list[str], warnings: list[str]) -> dict[str, Any] | None:
    """Gộp lỗi cấu trúc phát hiện SAU khi đánh số lại bảng/hình (gate chính chạy trước bước đó) vào validation_report."""
    if report is None or not (blocking or warnings):
        return report
    merged_blocking = [*report["blocking"], *blocking]
    return {**report, "blocking": merged_blocking, "warnings": [*report["warnings"], *warnings], "passed": not merged_blocking}
