"""Node tìm kiếm evidence trên toàn kho paper (nội bộ Qdrant + mở rộng OpenAlex trên Internet)."""

from app.agent.state import ResearchState
from app.agent.tools.retrieve_evidence import retrieve_evidence
from app.agent.tools.search_external_papers import retrieve_external_evidence


def is_reference_list_chunk(chunk) -> bool:
    """Kiểm tra xem chunk có phải là phần References/Bibliography thuần túy không."""
    sec = (chunk.section or "").strip().lower()
    if sec in ("references", "bibliography", "tài liệu tham khảo", "works cited", "reference list"):
        return True
    text_lower = chunk.text.strip().lower()
    if text_lower.startswith("references\n") or text_lower.startswith("bibliography\n"):
        return True
    return False


def is_domain_relevant(chunk, question: str) -> bool:
    """Lọc bỏ các bài báo hoàn toàn lệch miền nghiên cứu do OpenAlex trả về từ khóa chung.

    Ví dụ: Khi nghiên cứu RAG/NLP, gạt bỏ bài về cháy rừng (wildfire), nông nghiệp (crop yield), pin mặt trời.
    """
    text_lower = f"{chunk.paper_id} {chunk.text}".lower()
    q_lower = question.lower()

    off_domain_indicators = [
        "wildfire", "forest fire", "fire fighting", "fire detection",
        "crop yield", "soil moisture", "plant pathology", "agricultural",
        "solar cell", "photovoltaic", "power inverter", "traffic flow",
        "dermatology lesion", "bone fracture detection"
    ]
    for indicator in off_domain_indicators:
        if indicator in text_lower and indicator not in q_lower:
            return False
    return True


def search_node(state: ResearchState) -> ResearchState:
    queries = state.get("search_queries") or [state["question"]]

    # 1. Tìm kiếm evidence trên CSDL nội bộ (Qdrant)
    internal_evidence = retrieve_evidence(queries)
    # Lọc bỏ các chunk thuộc phần danh mục tài liệu tham khảo (References list) để tránh trích dẫn nhầm
    clean_internal = [sc for sc in internal_evidence if not is_reference_list_chunk(sc.chunk)]
    filtered_internal = clean_internal if clean_internal else internal_evidence

    # 2. Truy xuất tài liệu học thuật liên quan từ Internet (OpenAlex)
    external_evidence = retrieve_external_evidence(queries, count_per_query=8, max_total=30)
    # Lọc bỏ các bài báo bị lệch miền nghiên cứu (off-domain)
    relevant_external = [sc for sc in external_evidence if is_domain_relevant(sc.chunk, state["question"])]
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
    return {**state, "evidence": combined}
