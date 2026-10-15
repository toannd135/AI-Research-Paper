"""Node tự phản biện kết quả: kiểm tra citation hợp lệ, phát hiện gán ép nguồn, hallucination và mâu thuẫn kỹ thuật."""

from app.agent.evidence.citation_validator import (
    find_citation_misattributions,
    find_invalid_citations,
)
from app.agent.evidence.hallucination_detector import find_unsupported_sentences
from app.agent.state import ResearchState
from app.ai.context_builder import build_context
from app.ai.llm_gateway.base import LLMGateway


def critique_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    draft = state.get("draft", "")
    citations = state.get("citations", [])

    invalid_citations = find_invalid_citations(draft, citations)
    misattributions = find_citation_misattributions(draft, citations)

    if invalid_citations or misattributions:
        # Nếu trích dẫn sai chỉ số hoặc gán ép sai nguồn bài báo, bắt buộc viết lại ngay
        unsupported: list[str] = []
    else:
        evidence_text, _ = build_context(state.get("evidence", []))
        unsupported = find_unsupported_sentences(draft, evidence_text, llm=llm)

    iterations = state.get("iterations", 0) + 1

    # 1. Kiểm tra nhãn placeholder không mong muốn
    placeholders_found = [
        tag for tag in ["[CẦN THÊM NGUỒN]", "[TODO]", "[TBD]", "[Trống]"] if tag in draft
    ]

    # 2. Kiểm tra văn phong thổi phồng (Anti-Hype check)
    hype_terms = [
        term for term in ["first framework", "mechanistic guarantee", "guarantees that error", "proves that error"]
        if term in draft.lower()
    ]

    # 3. Kiểm tra mâu thuẫn kiến trúc (Encoder dùng làm Generative rewrite)
    encoder_conflict = False
    draft_lower = draft.lower()
    if "deberta" in draft_lower and any(act in draft_lower for act in ["generate", "rewrite", "sinh văn bản", "sinh câu trả lời"]):
        encoder_conflict = True

    # 4. Kiểm tra rò rỉ pipeline nội bộ (Pipeline Leakage)
    leakage_terms = [
        term for term in ["blueprint §", "chặng 1", "chặng 2", "chặng 3", "chặng 4", "chặng 5", "tóm tắt chặng", "global notation lock"]
        if term in draft_lower
    ]

    # 5. Kiểm tra ngôn ngữ lai tạp (Bilingual mixing): Nếu bài báo là tiếng Anh nhưng lẫn tiếng Việt
    vietnamese_terms = [
        w for w in ["chúng tôi", "phán quyết", "thực nghiệm", "phân tầng chất lượng", "mô hình giám khảo", "ước lượng điểm"]
        if w in draft_lower
    ]

    # 6. Kiểm tra mâu thuẫn số học ngân sách (Arithmetic conflict): ví dụ cả $2.70 và $0.90
    budget_conflict = False
    if "$2.70" in draft and "$0.90" in draft:
        budget_conflict = True
    if "18m" in draft_lower and "6m" in draft_lower and "token" in draft_lower:
        budget_conflict = True

    if (
        not invalid_citations
        and not misattributions
        and not unsupported
        and not placeholders_found
        and not hype_terms
        and not encoder_conflict
        and not leakage_terms
        and not vietnamese_terms
        and not budget_conflict
    ):
        return {**state, "critique_feedback": None, "iterations": iterations}

    feedback_parts = []
    if invalid_citations:
        feedback_parts.append(f"Các trích dẫn không hợp lệ (ngoài phạm vi context): {invalid_citations}")
    if misattributions:
        feedback_parts.append("Lỗi gán ép sai nguồn trích dẫn (Citation Misattribution):\n" + "\n".join(misattributions) + "\n-> Chỉ được cite tên phương pháp khi bài báo tương ứng thực sự nói về phương pháp đó.")
    if unsupported:
        feedback_parts.append(
            "Các câu sau không có evidence hỗ trợ từ context, hãy viết lại dựa trên bằng chứng xác thực hoặc lược bỏ khẳng định không có căn cứ: "
            + " | ".join(unsupported)
        )
    if placeholders_found:
        feedback_parts.append(
            f"Bản draft còn chứa các nhãn giữ chỗ {placeholders_found}. Tuyệt đối loại bỏ các nhãn này và diễn đạt thành phân tích học thuật hoàn chỉnh, khách quan."
        )
    if hype_terms:
        feedback_parts.append(
            f"Phát hiện văn phong khẳng định tuyệt đối quá mức ({hype_terms}). Hãy sửa lại bằng văn phong học thuật khiêm tốn: 'we propose a conceptual framework', 'we hypothesize', 'our formulation aims to bound error'."
        )
    if encoder_conflict:
        feedback_parts.append(
            "Mâu thuẫn kỹ thuật: DeBERTa là mô hình Encoder-only (chỉ dùng để phân loại/scoring), không thể dùng để REWRITE/sinh câu trả lời. Hãy dùng Generative Decoder (như Llama hoặc SLM Decoder) cho nhiệm vụ sinh câu trả lời."
        )
    if leakage_terms:
        feedback_parts.append(
            f"Rò rỉ siêu dữ liệu pipeline ({leakage_terms}): Tuyệt đối không dùng các từ nội bộ như 'Blueprint', 'Chặng', 'Global Notation Lock' trong bản thảo. Diễn đạt hoàn toàn bằng văn phong khoa học tự nhiên."
        )
    if vietnamese_terms:
        feedback_parts.append(
            f"Lẫn lộn ngôn ngữ: Phát hiện từ tiếng Việt ({vietnamese_terms}) trong bản thảo. Toàn bộ bài báo phải được viết 100% bằng tiếng Anh học thuật (Academic English)."
        )
    if budget_conflict:
        feedback_parts.append(
            "Mâu thuẫn số học ngân sách: Phát hiện số liệu chi phí hoặc số token không nhất quán giữa bảng và phần mô tả. Hãy đồng bộ chính xác số lời gọi của từng mô hình theo công thức 2 * N * R."
        )

    return {**state, "critique_feedback": "\n".join(feedback_parts), "iterations": iterations}
