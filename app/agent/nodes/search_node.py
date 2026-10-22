from app.agent.profiles import field_profile
from app.agent.state import ResearchState


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

    # 1. Tìm kiếm evidence trên CSDL nội bộ (Qdrant)
    internal_evidence = retrieve_evidence(queries)
    # Lọc bỏ các chunk thuộc phần danh mục tài liệu tham khảo (References list) để tránh trích dẫn nhầm
    clean_internal = [sc for sc in internal_evidence if not is_reference_list_chunk(sc.chunk)]
    filtered_internal = clean_internal if clean_internal else internal_evidence

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
    return {**state, "evidence": combined}
