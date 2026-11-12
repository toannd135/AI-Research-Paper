import logging
import time

from app.agent.profiles import field_profile
from app.agent.state import ResearchState
from app.agent.tools.ensure_coverage import collect_result_chunks, ensure_corpus_coverage
from app.core.config import get_settings
from app.core.scope import external_search_allowed

logger = logging.getLogger(__name__)


def is_reference_list_chunk(chunk) -> bool:
    """Kiểm tra xem chunk có phải là phần References/Bibliography thuần túy không."""
    sec = (chunk.section or "").strip().lower()
    if sec in ("references", "bibliography", "tài liệu tham khảo", "works cited", "reference list"):
        return True
    text_lower = chunk.text.strip().lower()
    return text_lower.startswith(("references\n", "bibliography\n"))


def is_domain_relevant(chunk, question: str, field: str | None = None) -> bool:
    """Lọc bỏ các bài báo hoàn toàn lệch miền nghiên cứu do OpenAlex trả về từ khóa chung.

    Danh sách lệch miền lấy theo hồ sơ lĩnh vực: đề tài CS/NLP gạt bài cháy rừng, nông nghiệp...;
    đề tài môi trường, y tế... không bị lọc theo các từ đó.
    """
    text_lower = f"{chunk.paper_id} {chunk.text}".lower()
    q_lower = question.lower()

    off_domain_indicators = field_profile({"field": field})["off_domain"]
    return not any(indicator in text_lower and indicator not in q_lower for indicator in off_domain_indicators)


def search_node(state: ResearchState) -> ResearchState:
    from app.agent.tools.retrieve_evidence import retrieve_evidence
    from app.agent.tools.search_external_papers import retrieve_external_evidence

    queries = state.get("search_queries") or [state["question"]]
    settings = get_settings()

    # Chunk bảng/kết quả riêng cho từng paper (kho nhỏ) để bước trích số liệu không phụ thuộc evidence theo câu hỏi
    result_evidence = collect_result_chunks(_results_query(state, queries[0]))

    if not external_search_allowed():
        return {
            **state,
            "evidence": _local_only_evidence(queries, settings.local_max_chunks_per_paper),
            "result_evidence": result_evidence,
        }

    # 1. Tìm kiếm evidence trên CSDL nội bộ (Qdrant)
    internal_evidence = retrieve_evidence(queries)
    # Lọc bỏ các chunk thuộc phần danh mục tài liệu tham khảo (References list) để tránh trích dẫn nhầm
    clean_internal = [sc for sc in internal_evidence if not is_reference_list_chunk(sc.chunk)]
    filtered_internal = ensure_corpus_coverage(clean_internal if clean_internal else internal_evidence, queries[0])

    # 2. Truy xuất tài liệu học thuật liên quan từ Internet (OpenAlex)
    external_evidence = retrieve_external_evidence(queries, count_per_query=12, max_total=50)
    # Lọc bỏ các bài báo bị lệch miền nghiên cứu (off-domain)
    relevant_external = [sc for sc in external_evidence if is_domain_relevant(sc.chunk, state["question"], state.get("field"))]
    filtered_external = relevant_external if relevant_external else external_evidence

    # 3. Hợp nhất bằng chứng: loại bỏ trùng lặp, không bị phụ thuộc duy nhất vào CSDL nội bộ
    seen_ids = set()
    combined = []

    for sc in filtered_internal:
        if sc.chunk.id not in seen_ids:
            seen_ids.add(sc.chunk.id)
            combined.append(sc)

    for sc in filtered_external:
        if sc.chunk.id not in seen_ids:
            seen_ids.add(sc.chunk.id)
            combined.append(sc)

    combined.sort(key=lambda s: s.score, reverse=True)
    return {**state, "evidence": combined, "result_evidence": result_evidence}


def _results_query(state: ResearchState, topic: str) -> str:
    """Truy vấn nhắm bảng kết quả định lượng: chủ đề + metric chuẩn của lĩnh vực (profiles.py)."""
    return f"{topic} quantitative results table comparison {field_profile(state)['metrics']}"


def _local_only_evidence(queries: list[str], max_per_paper: int) -> list:
    """Chỉ lấy evidence từ kho nội bộ, mở rộng tập ứng viên và giới hạn số chunk mỗi paper
    để context (cắt theo token) phủ được nhiều bài thay vì dồn vào vài bài điểm cao."""
    from app.agent.tools.search_papers import search_papers

    # Chạy tuần tự: rerank trên CPU song song nhiều query chỉ tranh nhau nhân, không nhanh hơn
    best: dict[str, object] = {}
    for query in queries:
        start = time.perf_counter()
        for sc in search_papers(query, top_k=30, candidate_k=60):
            if sc.chunk.id not in best or sc.score > best[sc.chunk.id].score:
                best[sc.chunk.id] = sc
        logger.info("Search local '%s' chạy %.1fs", query[:60], time.perf_counter() - start)
    evidence = sorted(best.values(), key=lambda s: s.score, reverse=True)
    clean = [sc for sc in evidence if not is_reference_list_chunk(sc.chunk)] or evidence

    per_paper: dict[str, int] = {}
    selected = []
    for sc in clean:  # đã sort theo score giảm dần
        count = per_paper.get(sc.chunk.paper_id, 0)
        if count < max_per_paper:
            per_paper[sc.chunk.paper_id] = count + 1
            selected.append(sc)
    return ensure_corpus_coverage(selected, queries[0] if queries else "")
