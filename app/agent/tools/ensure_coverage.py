"""Bổ sung evidence cho mọi paper trong kho nội bộ mà truy xuất theo câu hỏi bỏ sót (kho nhỏ)."""

import logging

from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from app.agent.evidence.coverage import full_coverage_applies
from app.ai.retrieval.hybrid import search_hybrid
from app.core.schemas import ScoredChunk
from app.core.scope import get_allowed_paper_ids
from app.pipeline.vector_store.qdrant_client import list_paper_ids

logger = logging.getLogger(__name__)


def _scoped_corpus(limit: int | None = None) -> set[str] | None:
    """Paper trong Qdrant thuộc phạm vi người dùng; None khi không liệt kê được hoặc kho vượt `full_corpus_coverage_limit`."""
    try:
        corpus = list_paper_ids()
    except (ResponseHandlingException, UnexpectedResponse, OSError):
        logger.exception("Không liệt kê được paper trong Qdrant; bỏ qua bước bổ sung độ phủ kho")
        return None
    allowed = get_allowed_paper_ids()
    if allowed is not None:
        corpus &= allowed
    if limit is not None:  # giới hạn riêng (chunk kết quả), không theo full_corpus_coverage_limit
        return corpus if 0 < len(corpus) <= limit else None
    return corpus if full_coverage_applies(len(corpus)) else None


def collect_result_chunks(query: str, per_paper: int = 3) -> list[ScoredChunk]:
    """Mỗi paper trong kho nhỏ: lấy `per_paper` chunk khớp nhất truy vấn bảng/kết quả định lượng.

    Độc lập với evidence theo câu hỏi (vốn chỉ 1-2 chunk/paper, hiếm khi trúng bảng kết quả), chỉ dùng cho bước
    trích số liệu (extractor) để ledger phủ được nhiều paper hơn.
    """
    from app.core.config import get_settings

    corpus = _scoped_corpus(get_settings().result_chunks_paper_limit)
    if not corpus:
        return []
    out: list[ScoredChunk] = []
    for pid in sorted(corpus):
        out.extend(search_hybrid(query, top_k=per_paper, paper_id=pid))
    logger.info("Chunk kết quả: %d chunk từ %d/%d paper", len(out), len({sc.chunk.paper_id for sc in out}), len(corpus))
    return out


def ensure_corpus_coverage(selected: list[ScoredChunk], query: str, per_paper: int = 1) -> list[ScoredChunk]:
    """Mỗi paper trong kho (theo phạm vi người dùng) có ≥1 chunk trong evidence; chunk bổ sung là chunk liên quan nhất tới `query`.

    Chỉ chạy khi kho ≤ `full_corpus_coverage_limit` paper; paper vector hóa chưa xong (không có trong Qdrant) thì không thể bổ sung.
    """
    corpus = _scoped_corpus()
    if corpus is None:
        return selected
    have = {sc.chunk.paper_id for sc in selected}
    extra: list[ScoredChunk] = []
    for pid in sorted(corpus - have):
        hits = search_hybrid(query, top_k=per_paper, paper_id=pid)
        if not hits:
            logger.warning("Paper %s có trong kho nhưng không truy xuất được chunk nào", pid)
        extra.extend(hits)
    if extra:
        logger.info("Phủ kho: bổ sung %d chunk cho %d/%d paper bị bỏ sót", len(extra), len({e.chunk.paper_id for e in extra}), len(corpus))
    return selected + extra
