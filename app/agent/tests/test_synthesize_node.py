"""Unit tests for the Hierarchical Section-by-Section Synthesis Pipeline."""

import pytest
from app.agent.nodes.synthesize_node import (
    _extract_last_paragraphs,
    _format_references_prompt,
    synthesize_node,
)
from app.ai.llm_gateway.base import LLMGateway, LLMResponse, Message
from app.core.schemas import Citation


def test_extract_last_paragraphs():
    text = """# Heading 1
This is the first paragraph.

| Table | Col |
|---|---|
| 1 | 2 |

This is the second paragraph.

This is the final concluding paragraph of this section.
"""
    extracted = _extract_last_paragraphs(text, num_paras=2)
    assert "This is the second paragraph." in extracted
    assert "This is the final concluding paragraph" in extracted
    assert "# Heading 1" not in extracted
    assert "| Table |" not in extracted


def test_format_references_prompt():
    citations = [
        Citation(chunk_id="c1", paper_id="attention_is_all_you_need", page=3, section="Method", text_snippet="Transformer architecture"),
        Citation(chunk_id="c2", paper_id="lora_low_rank", page=1, text_snippet="Low-rank adaptation"),
    ]
    formatted = _format_references_prompt(citations)
    assert "[1] attention_is_all_you_need, Page: 3, Section: Method" in formatted
    assert "[2] lora_low_rank, Page: 1" in formatted


class _MultiStageFakeGateway(LLMGateway):
    """Simulates a multi-stage LLM generation where each stage returns rich section content."""

    def __init__(self):
        self.call_count = 0

    def generate(self, messages: list[Message], model_name: str | None = None) -> LLMResponse:
        self.call_count += 1
        system = messages[0].content
        if "Chặng 0" in system or "Bản Thiết Kế" in system:
            return LLMResponse(
                text=(
                    "### 1. TITLE & ACRONYM: SEAL (Selective Eviction via Attention and Loss)\n"
                    "### 2. NOTATIONS: $T$ context length, $K_{ret}$ budget, $M_{total}$ cache size.\n"
                    "### 3. BENCHMARKS: HotpotQA, MuSiQue.\n"
                    "### 4. BASELINES: StreamingLLM, H2O.\n"
                ),
                model="test-fake",
            )
        if "Chặng 1" in system or "INTRODUCTION" in system:
            return LLMResponse(
                text=(
                    "# SEAL: Selective Eviction via Attention and Loss\n\n"
                    "**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n"
                    "## Abstract\n"
                    "Selective eviction achieves massive memory compression.\n\n"
                    "**Keywords:** LLM, KV-Cache, Eviction\n\n"
                    "## 1. Introduction\n"
                    "### 1.1 Motivation & Background\n"
                    "Modern LLMs suffer from high memory.\n\n"
                    "### 1.2 Limitations of Existing Baselines\n"
                    "Existing eviction suffers from error accumulation [1].\n\n"
                    "### 1.3 Core Contributions\n"
                    "- Contribution 1: Architectural Innovation\n"
                    "- Contribution 2: Theoretical Bounds\n\n"
                    "### 1.4 Paper Organization\n"
                    "We structure our paper accordingly.\n"
                ),
                model="test-fake",
            )
        if "Chặng 2" in system or "RELATED WORK" in system:
            return LLMResponse(
                text=(
                    "## 2. Related Work\n"
                    "### 2.1 Multi-Dimensional Taxonomy of Paradigms\n"
                    "**Table 1: Taxonomy and Comparative Overview**\n"
                    "| Method | Type | Metric |\n"
                    "|---|---|---|\n"
                    "| H2O [1] | Heavy | 85.0 |\n\n"
                    "### 2.2 Deep Comparative Analysis\n"
                    "Analysis shows latency tradeoffs.\n"
                ),
                model="test-fake",
            )
        if "Chặng 3" in system or "PROPOSED METHODOLOGY" in system:
            return LLMResponse(
                text=(
                    "## 3. Proposed Methodology\n"
                    "### 3.1 Formal Problem Formulation & Mathematical Foundations\n"
                    "Let $T$ denote context length, $K_{ret}$ be the retention budget.\n\n"
                    "$$\n"
                    "M_{total} = T \\times 32 \\text{ KiB}\n"
                    "$$\n\n"
                    "### 3.2 High-Level Architectural Pipeline\n"
                    "```mermaid\n"
                    "graph TD\n"
                    '    A["Input Query"] --> B["Attention Filter"]\n'
                    "```\n\n"
                    "### 3.3 Algorithmic Execution Protocol\n"
                    "**Algorithm 1: SEAL Execution**\n"
                    "```python\n"
                    "# Algorithm logic\n"
                    "```\n"
                ),
                model="test-fake",
            )
        if "Chặng 4" in system or "EXPERIMENTS" in system:
            return LLMResponse(
                text=(
                    "## 4. Experiments and Results\n"
                    "### 4.1 Benchmark Datasets\n"
                    "Evaluated on HotpotQA [1].\n\n"
                    "### 4.2 Quantitative Benchmark Comparison\n"
                    "**Table 2: Main Empirical Benchmark Evaluation**\n"
                    "| Baseline | F1 |\n"
                    "|---|---|\n"
                    "| Standard [1] | 80.0 |\n"
                    "| SEAL | **88.5** |\n"
                ),
                model="test-fake",
            )
        # Chặng 5 / Discussion
        return LLMResponse(
            text=(
                "## 5. Discussion\n"
                "### 5.1 Technical Analysis & Trade-Offs\n"
                "We discuss memory vs accuracy.\n\n"
                "## 6. Conclusion\n"
                "In conclusion, SEAL advances long-context inference.\n"
            ),
            model="test-fake",
        )


def test_synthesize_node_hierarchical_execution():
    state = {
        "question": "How to optimize KV cache eviction for long-context LLMs?",
        "draft": "SEAL combines attention scores and loss sensitivity [1].",
        "citations": [Citation(chunk_id="c_h2o", paper_id="h2o_paper", page=2, text_snippet="Heavy hitter oracle")],
        "research_mode": "novel_research",
    }
    gateway = _MultiStageFakeGateway()
    result = synthesize_node(state, llm=gateway)

    assert "report" in result
    report = result["report"]

    # Verify that all sections are properly synthesized and stitched
    assert "# SEAL: Selective Eviction via Attention and Loss" in report
    assert "## Abstract" in report
    assert "## 1. Introduction" in report
    assert "## 2. Related Work" in report
    assert "## 3. Proposed Methodology" in report
    assert "## 4. Experiments and Results" in report
    assert "## 5. Discussion" in report
    assert "## 6. Conclusion" in report
    assert "## References" in report
    assert "h2o_paper" in report

    # Verify that all 6 stages were invoked
    assert gateway.call_count == 6
