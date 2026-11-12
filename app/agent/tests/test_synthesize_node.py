"""Unit tests for the Hierarchical Section-by-Section Synthesis Pipeline."""

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


class _RqGateway(LLMGateway):
    """Fake: mỗi chặng ghi RQ KHÁC nhau như LLM thật; kiểm tra RQ chuẩn được tiêm vào prompt và ép vào bản cuối."""

    def __init__(self):
        self.prompts: list[str] = []

    def generate(self, messages: list[Message], model_name: str | None = None) -> LLMResponse:
        system = messages[0].content
        self.prompts.append(system)
        if "Research Blueprint" in system:
            return LLMResponse(
                text=(
                    "1. TITLE: Fusion Survey\n7. RESEARCH QUESTIONS\n"
                    "RQ1. Which backbone architectures dominate brain tumor segmentation today?\n"
                    "RQ2. At which stage are the four MRI modalities fused in published networks?\n"
                    "RQ3. How is robustness to missing modalities achieved in the literature?\n"
                ),
                model="fake",
            )
        if "Front Matter and Section 1" in system:
            return LLMResponse(
                text=(
                    "# Fusion Survey\n\n## Abstract\nText.\n\n**Keywords:** a, b\n\n## 1. Introduction\n"
                    "### 1.3 Research Gaps and Research Questions\n"
                    "**RQ1.** What are the dominant architectures used for glioma segmentation?\n"
                    "**RQ2.** Where do the modalities get fused according to published work?\n"
                    "**RQ3.** Which threats to validity affect the reported benchmark numbers?\n"
                ),
                model="fake",
            )
        if "REVIEW METHODOLOGY" in system:
            return LLMResponse(
                text=(
                    "## 2. Review Methodology\n### 2.1 Research Questions\n"
                    "**RQ1.** Which dominant backbone designs exist for tumour segmentation of glioma?\n"
                    "**RQ2.** Which stage of fusion do published works choose and why exactly?\n"
                    "**RQ3.** Which comparisons across the reported results are really valid today?\n"
                ),
                model="fake",
            )
        return LLMResponse(text="## 7. Conclusion\nWe answer RQ1, RQ2 and RQ3.\n" if "DISCUSSION AND CONCLUSION" in system else "Body [1].\n", model="fake")


def test_synthesize_uses_single_canonical_rq_set():
    from app.agent.evidence.rq_sync import check_rq_definitions, section_rqs

    llm = _RqGateway()
    state = {
        "question": "Fusion for brain tumor segmentation",
        "draft": "draft",
        "citations": [Citation(chunk_id="c1", paper_id="p1", page=1, text_snippet="x")],
        "research_mode": "survey",
    }
    out = synthesize_node(state, llm=llm)
    canon = [
        "Which backbone architectures dominate brain tumor segmentation today?",
        "At which stage are the four MRI modalities fused in published networks?",
        "How is robustness to missing modalities achieved in the literature?",
    ]
    assert all("CANONICAL RESEARCH QUESTIONS" in p for p in llm.prompts[1:]), "mọi chặng sau blueprint phải nhận RQ chuẩn"
    assert any("7. RESEARCH QUESTIONS" in p for p in llm.prompts[:1])
    secs = section_rqs(out["report"])
    assert len(secs) == 1 and all([b for _, b in v] == canon for v in secs.values()), "RQ chỉ được liệt kê một lần"
    assert check_rq_definitions(out["report"]) == []


def test_pad_corpus_citations_adds_unretrieved_scope_papers():
    """Paper trong phạm vi không có chunk được truy xuất vẫn được thêm (cuối danh sách) để có [k] và References."""
    from app.agent.evidence.repair import add_uncited_corpus
    from app.agent.nodes.synthesize_node import pad_corpus_citations
    from app.core.schemas import Citation

    cits = [Citation(paper_id="p1", chunk_id="c1", text_snippet="x"), Citation(paper_id="p2", chunk_id="c2", text_snippet="y")]
    catalog = {"p1": {"title": "A"}, "p2": {"title": "B"}, "p3": {"title": "Unretrieved Study"}}
    padded = pad_corpus_citations(cits, {"p1", "p2", "p3"}, catalog)
    assert [c.paper_id for c in padded] == ["p1", "p2", "p3"] and padded[2].text_snippet == ""
    assert padded[:2] == cits  # chỉ số [k] cũ giữ nguyên
    assert [c.paper_id for c in pad_corpus_citations(cits, None, catalog)] == ["p1", "p2", "p3"]  # None -> khóa catalog
    assert pad_corpus_citations(cits, {"p1", "p2"}, catalog) is cits
    text, missing = add_uncited_corpus("## 1. Intro\n\nUses [1] and [2].\n\n## References\n", padded, catalog)
    assert missing == ["p3"] and "*Unretrieved Study* [3]" in text


def test_pad_corpus_citations_skips_large_corpus(monkeypatch):
    from app.agent.evidence import coverage
    from app.agent.nodes.synthesize_node import pad_corpus_citations

    monkeypatch.setattr(coverage, "get_settings", lambda: type("S", (), {"full_corpus_coverage_limit": 2})())
    cits = [{"paper_id": "p1"}]
    assert pad_corpus_citations(cits, {"p1", "p2", "p3"}, {}) is cits
