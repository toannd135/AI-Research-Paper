"""Cache in-process cho BM25 index theo scope (paper_id hoặc toàn corpus).

Trước đây bm25_search.py build lại BM25Okapi từ đầu (scroll toàn bộ chunk khớp filter) ở MỖI
lần gọi search_bm25() — với query không giới hạn theo 1 paper_id, chi phí này tỉ lệ thuận với
tổng số chunk trong toàn bộ collection, không sống nổi ở quy mô 10k+ paper. Module này cache lại
BM25Okapi + corpus đã build trong bộ nhớ của worker process, và được invalidate mỗi khi
qdrant_client.upsert_chunks()/delete_paper() thay đổi dữ liệu của paper_id tương ứng.

Đây là cache trong-process (không share giữa các worker) — giảm chi phí rebuild từ "mỗi request"
xuống "mỗi worker, mỗi khi dữ liệu paper đó thay đổi hoặc hết TTL", chưa phải giải pháp triệt để
(xem RAG_UPGRADE_PLAN.md mục P2: native sparse-vector search thay hẳn BM25Okapi tự build).
"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rank_bm25 import BM25Okapi

    from app.core.schemas import Chunk

_TTL_SECONDS = 300
_ALL_SCOPE = "__all__"

_cache: dict[str, tuple[float, "BM25Okapi", list["Chunk"]]] = {}


def _scope_key(paper_id: str | None) -> str:
    return paper_id or _ALL_SCOPE


def get(paper_id: str | None) -> tuple["BM25Okapi", list["Chunk"]] | None:
    entry = _cache.get(_scope_key(paper_id))
    if entry is None:
        return None
    built_at, bm25, corpus = entry
    if time.monotonic() - built_at > _TTL_SECONDS:
        _cache.pop(_scope_key(paper_id), None)
        return None
    return bm25, corpus


def set(paper_id: str | None, bm25: "BM25Okapi", corpus: list["Chunk"]) -> None:
    _cache[_scope_key(paper_id)] = (time.monotonic(), bm25, corpus)


def invalidate(paper_id: str) -> None:
    """Bỏ cache của paper_id này và của scope toàn corpus, vì cả hai đều đã stale."""
    _cache.pop(paper_id, None)
    _cache.pop(_ALL_SCOPE, None)


def clear() -> None:
    _cache.clear()
