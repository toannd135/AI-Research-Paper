"""Mock tool: search_papers theo chuẩn LangChain @tool."""

from __future__ import annotations

from langchain_core.tools import tool

from app.core.schemas import SearchPapersInput

# Danh mục các bài báo khoa học mẫu dùng cho mock local/offline
MOCK_PAPERS: list[dict] = [
    {
        "paper_id": "attention_is_all_you_need",
        "title": "Attention Is All You Need",
        "authors": [
            "Ashish Vaswani",
            "Noam Shazeer",
            "Niki Parmar",
            "Jakob Uszkoreit",
            "Llion Jones",
            "Aidan N. Gomez",
            "Łukasz Kaiser",
            "Illia Polosukhin",
        ],
        "year": 2017,
    },
    {
        "paper_id": "lora_low_rank_adaptation",
        "title": "LoRA: Low-Rank Adaptation of Large Language Models",
        "authors": [
            "Edward J. Hu",
            "Yelong Shen",
            "Phillip Wallis",
            "Zeyuan Allen-Zhu",
            "Yuanzhi Li",
            "Shean Wang",
            "Lu Wang",
            "Weizhu Chen",
        ],
        "year": 2021,
    },
    {
        "paper_id": "rag_retrieval_augmented_generation",
        "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "authors": [
            "Patrick Lewis",
            "Ethan Perez",
            "Aleksandra Piktus",
            "Fabio Petroni",
            "Vladimir Karpukhin",
            "Naman Goyal",
            "Heinrich Küttler",
            "Mike Lewis",
            "Wen-tau Yih",
            "Tim Rocktäschel",
            "Sebastian Riedel",
            "Douwe Kiela",
        ],
        "year": 2020,
    },
    {
        "paper_id": "bge_m3_embedding",
        "title": "BGE M3-Embedding: Multi-Lingual, Multi-Functionality, Multi-Granularity Text Embeddings",
        "authors": [
            "Jianlyu Chen",
            "Shitao Xiao",
            "Peitian Zhang",
            "Kun Luo",
            "Defu Lian",
            "Zheng Liu",
        ],
        "year": 2024,
    },
]


@tool(args_schema=SearchPapersInput)
def search_papers(query: str, top_k: int = 5) -> list[dict]:
    """Tìm kiếm danh sách bài báo khoa học dựa theo từ khóa hoặc câu hỏi."""
    query_lower = query.strip().lower()
    if not query_lower:
        return []

    results: list[dict] = []
    # Keyword-based matching trên title, paper_id và tác giả
    for paper in MOCK_PAPERS:
        title_lower = paper["title"].lower()
        id_lower = paper["paper_id"].lower()
        authors_lower = " ".join(paper["authors"]).lower()

        # Tách query thành các từ khóa
        tokens = [t for t in query_lower.split() if len(t) > 1]
        matches = any(
            t in title_lower or t in id_lower or t in authors_lower for t in tokens
        )

        # Hỗ trợ thêm các từ đồng nghĩa/chủ đề phổ biến
        if not matches:
            if "attention" in query_lower or "transformer" in query_lower:
                matches = paper["paper_id"] == "attention_is_all_you_need"
            elif (
                "lora" in query_lower
                or "fine-tuning" in query_lower
                or "adaptation" in query_lower
            ):
                matches = paper["paper_id"] == "lora_low_rank_adaptation"
            elif "rag" in query_lower or "retrieval" in query_lower:
                matches = paper["paper_id"] == "rag_retrieval_augmented_generation"
            elif (
                "embedding" in query_lower
                or "bge" in query_lower
                or "m3" in query_lower
            ):
                matches = paper["paper_id"] == "bge_m3_embedding"

        if matches:
            results.append(paper)

    return results[:top_k]
