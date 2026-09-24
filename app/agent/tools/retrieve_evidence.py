"""Mock tool: retrieve_evidence theo chuẩn LangChain @tool."""

from __future__ import annotations

from langchain_core.tools import tool

from app.core.schemas import RetrieveEvidenceInput

# Mock evidence database chứa các đoạn trích dẫn khoa học thực tế
MOCK_EVIDENCE_CHUNKS: list[dict] = [
    # Attention Is All You Need (2017)
    {
        "chunk_id": "attn_001",
        "paper_id": "attention_is_all_you_need",
        "content": "An attention function can be described as mapping a query and a set of key-value pairs to an output, where the query, keys, values, and output are all vectors. The output is computed as a weighted sum of the values.",
        "page_number": 3,
        "section_title": "Scaled Dot-Product Attention",
        "score": 0.95,
    },
    {
        "chunk_id": "attn_002",
        "paper_id": "attention_is_all_you_need",
        "content": "We compute the matrix of outputs as: Attention(Q, K, V) = softmax(Q K^T / sqrt(d_k)) V. We compute the attention function on a set of queries simultaneously, packed together into a matrix Q.",
        "page_number": 4,
        "section_title": "Attention Formula",
        "score": 0.92,
    },
    {
        "chunk_id": "attn_003",
        "paper_id": "attention_is_all_you_need",
        "content": "Multi-head attention allows the model to jointly attend to information from different representation subspaces at different positions. With multi-head attention we linearly project queries, keys and values h times.",
        "page_number": 5,
        "section_title": "Multi-Head Attention",
        "score": 0.88,
    },
    # LoRA (2021)
    {
        "chunk_id": "lora_001",
        "paper_id": "lora_low_rank_adaptation",
        "content": "We propose Low-Rank Adaptation (LoRA), which freezes the pre-trained model weights and injects trainable rank decomposition matrices into each layer of the Transformer architecture, greatly reducing trainable parameters.",
        "page_number": 1,
        "section_title": "Abstract",
        "score": 0.94,
    },
    {
        "chunk_id": "lora_002",
        "paper_id": "lora_low_rank_adaptation",
        "content": "For a pre-trained weight matrix W_0, we constrain its update by representing W = W_0 + B A, where B in R^{d x r} and A in R^{r x k}, and the rank r << min(d, k). During training, W_0 is frozen.",
        "page_number": 3,
        "section_title": "Low-Rank Parameterized Update Matrices",
        "score": 0.91,
    },
    # RAG (2020)
    {
        "chunk_id": "rag_001",
        "paper_id": "rag_retrieval_augmented_generation",
        "content": "Retrieval-Augmented Generation (RAG) models combine pre-trained parametric memory (generator) and non-parametric memory (dense vector index of Wikipedia) accessed via a pre-trained neural retriever.",
        "page_number": 2,
        "section_title": "Methods",
        "score": 0.93,
    },
    {
        "chunk_id": "rag_002",
        "paper_id": "rag_retrieval_augmented_generation",
        "content": "We explore two formulations: RAG-Sequence, which uses the same retrieved documents to generate the complete sequence, and RAG-Token, which can use different retrieved documents for each generated token.",
        "page_number": 4,
        "section_title": "RAG-Sequence vs RAG-Token",
        "score": 0.89,
    },
    # BGE-M3 (2024)
    {
        "chunk_id": "bge_001",
        "paper_id": "bge_m3_embedding",
        "content": "BGE-M3 is a versatile embedding model that supports multi-linguality (over 100 languages), multi-granularity (from short sentences to 8192-token documents), and multi-functionality (dense, lexical, and multi-vector retrieval).",
        "page_number": 2,
        "section_title": "Introduction",
        "score": 0.96,
    },
    {
        "chunk_id": "bge_002",
        "paper_id": "bge_m3_embedding",
        "content": "BGE-M3 integrates dense retrieval (semantic matching), sparse retrieval (lexical/BM25 style matching), and multi-vector ColBERT-style retrieval into a single unified framework.",
        "page_number": 4,
        "section_title": "Hybrid Multi-Functionality",
        "score": 0.90,
    },
]


@tool(args_schema=RetrieveEvidenceInput)
def retrieve_evidence(
    query: str,
    paper_id: str | None = None,
    top_k: int = 5,
) -> list[dict]:
    """Trích xuất các đoạn văn bản (chunks) bằng chứng phù hợp với query từ các bài báo."""
    query_lower = query.strip().lower()
    if not query_lower:
        return []

    import re

    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "not",
        "are",
        "can",
        "present",
        "into",
    }
    query_words = {
        w
        for w in re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", query_lower)
        if w not in stopwords
    }
    matched_chunks: list[dict] = []

    for chunk in MOCK_EVIDENCE_CHUNKS:
        # Nếu chỉ định paper_id thì bắt buộc phải trùng
        if paper_id and chunk["paper_id"] != paper_id:
            continue

        content_words = set(
            re.findall(r"\b[a-zA-Z0-9_\-]{3,}\b", chunk["content"].lower())
        )
        section_words = set(
            re.findall(
                r"\b[a-zA-Z0-9_\-]{3,}\b", (chunk["section_title"] or "").lower()
            )
        )

        # Tính điểm khớp từ khóa theo word overlap
        matched_tokens = query_words.intersection(content_words.union(section_words))
        match_count = len(matched_tokens)

        # Keyword mapping bổ sung cho các chủ đề chính
        if (
            "self-attention" in query_lower
            or "query" in query_lower
            or "key" in query_lower
            or "value" in query_lower
        ) and chunk["paper_id"] == "attention_is_all_you_need":
            match_count += 3

        if (
            "rank" in query_lower
            or "freeze" in query_lower
            or "trainable" in query_lower
            or "weight" in query_lower
        ) and chunk["paper_id"] == "lora_low_rank_adaptation":
            match_count += 3

        if (
            "parametric" in query_lower
            or "generator" in query_lower
            or "dense vector" in query_lower
            or "rag-sequence" in query_lower
        ) and chunk["paper_id"] == "rag_retrieval_augmented_generation":
            match_count += 3

        if (
            "multi-lingual" in query_lower
            or "granularity" in query_lower
            or "colbert" in query_lower
            or "dense" in query_lower
        ) and chunk["paper_id"] == "bge_m3_embedding":
            match_count += 3

        if match_count > 0:
            matched_chunks.append((match_count, chunk))

    # Sắp xếp theo số lượng từ khóa trùng khớp giảm dần rồi lấy top_k
    matched_chunks.sort(key=lambda x: x[0], reverse=True)
    return [item[1] for item in matched_chunks[:top_k]]
