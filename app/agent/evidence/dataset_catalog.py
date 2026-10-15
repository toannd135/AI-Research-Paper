"""Catalog các benchmark dataset chuẩn và đặc tính thực tế (Ground-Truth Dataset Specs).

Ngăn chặn triệt để hiện tượng LLM tự bịa (hallucinate) kích thước dataset,
cấu trúc nhãn người (majority vote), hoặc phân bố nhãn.
"""

from __future__ import annotations

from typing import Any

KNOWN_DATASETS: dict[str, dict[str, Any]] = {
    "llmbar": {
        "canonical_name": "LLMBar",
        "primary_authors": "Zeng et al.",
        "year": 2023,
        "paper_title": "Evaluating Large Language Models at Evaluating Instruction Following with LLMBar",
        "total_pairs": 419,
        "subsets": {
            "natural": 100,
            "adversarial": 319,
        },
        "label_type": "Binary human preference (chosen vs. rejected)",
        "annotator_details": "Aggregated consensus labels; individual annotator votes are NOT publicly released.",
        "notes": "Small-scale evaluation set. N >= 5,000 studies CANNOT be fulfilled by LLMBar alone without data expansion.",
    },
    "mt-bench": {
        "canonical_name": "MT-Bench Human Judgments",
        "primary_authors": "Zheng et al.",
        "year": 2023,
        "paper_title": "Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena",
        "total_pairs": 3300,
        "label_type": "Pairwise human preference across 8 categories (Coding, Reasoning, Roleplay, etc.)",
        "annotator_details": "Pairwise win/loss/tie outcomes collected from expert and crowd judges.",
        "notes": "Standard multi-turn evaluation benchmark.",
    },
    "chatbot-arena": {
        "canonical_name": "LMSYS Chatbot Arena Conversations",
        "primary_authors": "Chiang et al.",
        "year": 2023,
        "paper_title": "Chatbot Arena: An Open Platform for Evaluating LLMs by Human Preference",
        "total_pairs": 33000,
        "label_type": "Crowdsourced blind pairwise comparison (Model A vs. Model B)",
        "annotator_details": "Live user evaluations with win/loss/tie votes.",
        "notes": "Dominant public benchmark for pairwise LLM judging with N > 30,000.",
    },
    "hh-rlhf": {
        "canonical_name": "Anthropic HH-RLHF",
        "primary_authors": "Bai et al.",
        "year": 2022,
        "paper_title": "Training a Helpful and Harmless Assistant with Reinforcement Learning from Human Feedback",
        "total_pairs": 160000,
        "label_type": "Binary chosen vs. rejected pairs",
        "annotator_details": "Single aggregate preference label per pair; individual annotator vote breakdown is not available.",
        "notes": "Large-scale RLHF dataset. Does not contain raw annotator agreement rates.",
    },
    "ultrafeedback": {
        "canonical_name": "UltraFeedback",
        "primary_authors": "Cui et al.",
        "year": 2023,
        "paper_title": "UltraFeedback: Boosting Language Models with High-quality Feedback",
        "total_pairs": 64000,
        "label_type": "Multi-aspect scoring and preference ranking across 4 dimensions",
        "annotator_details": "Fine-grained ratings with algorithmic and human preference annotations.",
        "notes": "High-volume alignment dataset suitable for large sample sizes (N >= 5,000).",
    },
}


def get_dataset_grounding_context() -> str:
    """Trả về chuỗi context đặc tả quy mô dataset chuẩn để đưa vào System Prompt."""
    lines = ["GROUND-TRUTH BENCHMARK DATASET SPECIFICATIONS (DO NOT HALLUCINATE SIZES OR LABELS):"]
    for key, info in KNOWN_DATASETS.items():
        subsets_str = f", subsets: {info['subsets']}" if "subsets" in info else ""
        lines.append(
            f"- {info['canonical_name']} ({info['primary_authors']}, {info['year']}): "
            f"Total available instances = ~{info['total_pairs']:,}{subsets_str}. "
            f"Label format: {info['label_type']}. Annotator notes: {info['annotator_details']}"
        )
    return "\n".join(lines)
