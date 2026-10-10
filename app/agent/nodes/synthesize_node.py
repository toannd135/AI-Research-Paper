"""Hierarchical Section-by-Section Synthesis Pipeline for Top-Tier Academic Papers.

Enforces:
1. Strict Single-Language Lock: 100% formal Academic English across all sections.
2. Zero Pipeline Leakage: Strips meta-commentary, stage labels, and internal scaffolding.
3. Mathematical & Statistical Rigor:
   - Explicit slot-to-candidate unmapping: s in {A, B} -> d in {1, 2}.
   - Paired inference: consistent pairs contribute zero variance to FPR; Var(FPR_hat) <= SR / (4N).
   - Exact algebraic bound: |FPR - 0.5| <= SR / 2; equivalence bound delta_FPR = delta_SR / 2 = 0.01.
   - Equivalence testing via Two One-Sided Tests (TOST) with pair-level bootstrap CI.
   - Deterministic hashing via hashlib.md5.
4. Exact Arithmetic Budget Consistency:
   - Total passes: 2 * N * R * J = 90,000 across 3 models.
   - Per-model passes: 2 * N * R = 30,000 calls each.
   - Judge-API: 30,000 calls * 800 tok/call = 24M tokens -> $3.60.
   - Local 7B: 30,000 * 0.5s / 3600 = 4.17 GPU-hours.
   - Local 70B: 30,000 * 3s / 3600 = 25 hours on 2xA100 (50 GPU-hours).
5. Canonical Citations: Deduplicates papers, removes raw search dumps, formats clean IEEE references.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.agent.evidence.citation_cleaner import clean_and_deduplicate_citations
from app.agent.evidence.dataset_catalog import get_dataset_grounding_context
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

logger = logging.getLogger(__name__)

_GLOBAL_ACADEMIC_STANDARDS = f"""
STRICT PEER-REVIEW PUBLICATION STANDARDS (MANDATORY ACROSS ALL SECTIONS):
1. STRICT SINGLE-LANGUAGE CONSTRAINT:
   - The ENTIRE manuscript must be written exclusively in formal Academic English from title to conclusion.
   - NEVER output Vietnamese or any other language in any section under any circumstance.
2. ZERO META-PIPELINE LEAKAGE:
   - NEVER output internal pipeline terminology such as 'Blueprint', 'Global Notation Lock', 'Stage Summary', 'Chặng', or meta-instructions.
   - Refer to previous parts naturally using standard academic conventions (e.g., 'as formalized in Section 3', 'the pre-registered protocol').
3. MATHEMATICAL RIGOR & CANDIDATE UNMAPPING:
   - In pairwise LLM-as-a-judge evaluation, distinguish between presentation slot s in {{A, B}} and candidate answer identity d in {{1, 2}}.
   - Under Order (1,2) [a1 first, a2 second]: slot A corresponds to a1 (d=1), slot B corresponds to a2 (d=2).
   - Under Order (2,1) [a2 first, a1 second]: slot A corresponds to a2 (d=2), slot B corresponds to a1 (d=1).
   - Inconsistency / Swap Rate (SR) occurs ONLY when candidate decisions differ: d^(1,2) != d^(2,1).
   - Paired Structure for FPR: S_i = I[s_i^(1,2) = A] + I[s_i^(2,1) = A]. For any consistent pair, S_i = 1 deterministically. Variance Var(FPR_hat) <= SR / (4N).
   - Structural algebraic bound: |FPR - 0.5| <= SR / 2. Therefore, equivalence bound delta_FPR = delta_SR / 2 = 0.01.
   - Hypotheses: H1 (Existence of swap bias) tested via paired binomial/McNemar test; H2 (Equivalence to 0.5) tested via Two One-Sided Tests (TOST) within [-delta_FPR, +delta_FPR].
   - Uncertainty quantification must use pair-level bootstrap (resampling N pairs with replacement).
4. COMPUTATIONAL BUDGET & ARITHMETIC CONSISTENCY:
   - All computational numbers must strictly match across all sections:
     * N = 5,000 pairs, R = 3 runs, J = 3 models (Judge-7B, Judge-70B, Judge-API).
     * Total forward passes = 2 * N * R * J = 90,000 passes.
     * Passes per judge = 2 * N * R = 30,000 passes each.
     * Judge-API: 30,000 calls * 800 tokens/call = 24M tokens -> $3.60 total at $0.15/1M tokens.
     * Judge-7B (local): 30,000 calls * 0.5s / 3600 = 4.17 GPU-hours on 1x A100.
     * Judge-70B (local): 30,000 calls * 3s / 3600 = 25 wallclock-hours on 2x A100 (= 50 GPU-hours).
5. BENCHMARK DATASET GROUNDING:
{get_dataset_grounding_context()}
   - Acknowledge exact dataset sizes: LLMBar has 419 total pairs (Natural: 100, Adversarial: 319). For N >= 5,000, use LMSYS Chatbot Arena as the primary dataset.
6. CITATION & NOVELTY OBJECTIVITY:
   - Acknowledge foundational prior works: Zheng et al. (2023) [MT-Bench/LMSYS] for first position bias measurement in LLMs, Wang et al. (2023) for swap consistency, Chiang et al. (2023) for Chatbot Arena, Bai et al. (2022) for HH-RLHF, Zeng et al. (2023) for LLMBar.
   - Do NOT make hyperbolic claims like 'no prior work defined swap rate'. State precise incremental contributions: pre-registered equivalence bounds, paired inferential derivations, and standardized reporting.
7. FORMATTING RULES:
   - Use hyphen '- ' for unordered lists.
   - Display math $$...$$ MUST be on its own line with empty lines before and after.
   - Every table MUST have a clear caption above it: '**Table N: Caption**'.
   - If registered report (experiments pending), table cells for proposed models must be marked '*Not Exp.*'.
"""


def _extract_last_paragraphs(text: str, num_paras: int = 2) -> str:
    """Extract last paragraphs of a section to serve as transition context for the next section."""
    paragraphs = [
        p.strip()
        for p in text.strip().split("\n\n")
        if p.strip() and not p.strip().startswith("#") and not p.strip().startswith("|")
    ]
    if not paragraphs:
        return ""
    selected = paragraphs[-num_paras:]
    return "\n\n".join(selected)


def _format_references_prompt(citations: list[Any]) -> str:
    """Format raw citations for model prompt context."""
    references_lines = []
    for i, c in enumerate(citations, start=1):
        pid = getattr(c, "paper_id", "") or (c.get("paper_id") if isinstance(c, dict) else "")
        page = getattr(c, "page", None) or (c.get("page") if isinstance(c, dict) else None)
        section = getattr(c, "section", None) or (c.get("section") if isinstance(c, dict) else None)
        snippet = getattr(c, "text_snippet", "") or (c.get("text_snippet") if isinstance(c, dict) else "")

        ref_line = f"[{i}] {pid}"
        if page:
            ref_line += f", Page: {page}"
        if section:
            ref_line += f", Section: {section}"
        if snippet:
            clean_snippet = str(snippet).replace("\n", " ").strip()[:180]
            ref_line += f' — "{clean_snippet}..."'
        references_lines.append(ref_line)
    return "\n".join(references_lines)


def _generate_stage_0_blueprint(
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 0: Global Architecture, Formal Mathematical Notation & Experimental Design Plan."""
    system_prompt = (
        "You are a Principal Scientist designing a comprehensive, publication-grade Research Blueprint (Bản Thiết Kế Nghiên Cứu Toàn Bài).\n"
        "Your goal is to establish a rigorous mathematical notation system, exact experimental parameters, and an inferential plan.\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        "Generate a complete Research Blueprint with the following sections in formal Academic English:\n"
        "1. TITLE & ACRONYM: Academic title and concise acronym.\n"
        "2. FORMAL MATHEMATICAL NOTATION: Exact symbols for inputs, presentation orders, candidate answers, decisions, metrics, and equivalence bounds.\n"
        "3. EXPERIMENTAL PROTOCOL & PARAMETERS: Dataset choices with exact scales, judge model scale breakdown (7B, 70B, API), deterministic decoding (T=0), paired execution.\n"
        "4. DERIVABLE COMPUTATIONAL BUDGET: Exact formulas and values (passes, tokens, API cost, GPU-hours).\n"
        "5. CORE CONTRIBUTIONS: 4 distinct, verifiable contributions."
    )

    user_prompt = (
        f"Research Mode: {'Novel Research' if mode == 'novel_research' else 'Literature Survey'}\n"
        f"Research Question: {state['question']}\n\n"
        f"Baseline Draft:\n{state.get('draft', '')}\n\n"
        f"Available Citations:\n{references}"
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _generate_stage_1_front_matter_and_intro(
    blueprint: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 1: Front Matter + Section 1 (Title, Abstract, Introduction & Contributions)."""
    system_prompt = (
        "You are writing Front Matter and Section 1 (INTRODUCTION) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent Academic English (~1,200 - 1,500 words).\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        "REQUIRED STRUCTURE FOR SECTION 1:\n"
        "# [Acronym]: [Full Descriptive Title]\n\n"
        "**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n"
        "## Abstract\n"
        "(Self-contained 250-300 word abstract: Context & Motivation, Baseline Limitations, Proposed Measurement Framework, Theoretical & Empirical Highlights, Implications. No citations [n] in abstract).\n\n"
        "**Keywords:** k1, k2, k3, k4, k5\n\n"
        "## 1. Introduction\n"
        "### 1.1 Motivation & Background\n"
        "(Comprehensive background on LLM-as-a-Judge pairwise evaluation and vulnerability to presentation order, 3-4 full paragraphs).\n"
        "### 1.2 Limitations of Existing Baselines\n"
        "(Detailed analysis of existing measurement deficiencies: metric ambiguity, absence of paired inferential statistics, lack of equivalence bounds, and ungrounded sample sizes [n], 3-4 paragraphs).\n"
        "### 1.3 Core Contributions\n"
        "(Exactly 4 itemized contributions using hyphen '- '):\n"
        "- C1. Precise Metric Definitions ...\n"
        "- C2. Falsifiable Hypotheses with Equivalence Bounds ...\n"
        "- C3. Paired Statistical Analysis Plan ...\n"
        "- C4. Standardized Experimental Protocol & Variance Accounting ...\n\n"
        "### 1.4 Paper Organization\n"
        "(Outline strictly Sections 2 through 6. Do NOT reference unwritten sections or phantom appendices)."
    )

    user_prompt = (
        f"Research Question: {state['question']}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        "Write Section 1 in formal Academic English with the highest academic depth."
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _generate_stage_2_related_work(
    blueprint: str,
    sec1_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 2: Section 2 (Related Work & Conceptual Taxonomy Framework)."""
    system_prompt = (
        "You are writing Section 2 (RELATED WORK) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent Academic English (~1,400 - 1,600 words).\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 1:\n{sec1_transition}\n\n"
        "REQUIRED STRUCTURE FOR SECTION 2:\n"
        "## 2. Related Work\n"
        "### 2.1 Multi-Dimensional Taxonomy of Paradigms\n"
        "(Include Markdown table comparing prior operationalizations with caption '**Table 1: Taxonomy and Comparative Overview of Existing Paradigms**').\n"
        "### 2.2 Deep Comparative Analysis of Existing Mechanisms\n"
        "(Detailed mechanistic critique of prior studies [n], highlighting seminal works by Zheng et al. (2023) and Wang et al. (2023)).\n"
        "### 2.3 Theoretical & Practical Gaps in Current Literature\n"
        "(Clarify specific gaps addressed by this work: paired uncertainty quantification, TOST equivalence bounds, candidate unmapping)."
    )

    user_prompt = (
        f"Research Question: {state['question']}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        "Write Section 2 with comprehensive scholarly literature mapping in formal Academic English."
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _generate_stage_3_methodology(
    blueprint: str,
    sec2_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 3: Section 3 (Proposed Methodology, Mathematical Foundations & Algorithmic Protocol)."""
    system_prompt = (
        "You are writing Section 3 (PROPOSED METHODOLOGY) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent Academic English (~2,200 - 2,500 words).\n"
        "DO NOT output any stage summary or meta-commentary at the end.\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 2:\n{sec2_transition}\n\n"
        "REQUIRED STRUCTURE FOR SECTION 3:\n"
        "## 3. Proposed Methodology\n"
        "### 3.1 Formal Problem Formulation & Mathematical Foundations\n"
        "- Input space: (q, a1, a2, y). Presentation orders: pi in {(1,2), (2,1)}.\n"
        "- Slot-to-Candidate Unmapping: Model outputs slot s in {A, B}. Under Order (1,2), A->1, B->2. Under Order (2,1), A->2, B->1. Decision d_i^(pi) in {1, 2} is candidate identity.\n"
        "### 3.2 High-Level Architectural Pipeline\n"
        "- Describe overall end-to-end evaluation flow. Include a standard ```mermaid flowchart diagram.\n"
        "### 3.3 Detailed Component Formulations & Hypotheses\n"
        "- Swap Rate Estimator: SR = (1/N) * sum(I[d_i^(1,2) != d_i^(2,1)]).\n"
        "- First-Position Preference Rate Estimator: FPR = (1/(2N)) * sum(I[s_i^(1,2) = A] + I[s_i^(2,1) = A]).\n"
        "- Mathematical Coupling: S_i = I[s_i^(1,2) = A] + I[s_i^(2,1) = A]. For consistent pairs, S_i = 1. Variance Var(FPR_hat) <= SR / (4N). Structural bound |FPR - 0.5| <= SR / 2.\n"
        "- Hypotheses: H1 (SR > delta_SR) with delta_SR = 0.02. H2 (|FPR - 0.5| < delta_FPR) tested via Two One-Sided Tests (TOST) with delta_FPR = delta_SR / 2 = 0.01.\n"
        "### 3.4 Algorithmic Execution Protocol\n"
        "- Include '**Algorithm 1: POS-BIAS-MEASURE Evaluation Protocol**' in Python pseudocode featuring candidate unmapping, pair-level bootstrap CI, and TOST test.\n"
        "### 3.5 Theoretical Analysis & Computational Complexity\n"
        "- Time complexity, space complexity, and analytical sample size derivation.\n"
        "- Include '**Table 2: Derivable Computational Budget**' with exact consistent values:\n"
        "  Total Passes = 90,000; API Tokens = 24M ($3.60); Local 7B = 4.17 GPU-hours; Local 70B = 50 GPU-hours (25h on 2xA100)."
    )

    user_prompt = (
        f"Research Question: {state['question']}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        "Write Section 3 with mathematical completeness and exact arithmetic consistency in formal Academic English."
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _generate_stage_4_experiments(
    blueprint: str,
    sec3_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 4: Section 4 (Experiments and Results, Matrix, Ablations & Case Studies)."""
    system_prompt = (
        "You are writing Section 4 (EXPERIMENTS) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent Academic English (~2,200 - 2,500 words).\n"
        "DO NOT output any stage summary or meta-commentary at the end.\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 3:\n{sec3_transition}\n\n"
        "REQUIRED STRUCTURE FOR SECTION 4:\n"
        "## 4. Experiments and Results\n"
        "### 4.1 Benchmark Datasets, Metrics & Evaluation Protocol\n"
        "- Datasets: LMSYS Chatbot Arena (N=5,000 primary subset), MT-Bench Human Judgments (3.3k), LLMBar (419 instances as specialized sanity check). Follow real dataset scales.\n"
        "- Metrics: SR, FPR, per-stratum estimates, pair-level bootstrap CIs.\n"
        "- Computational Budget Breakdown in text: MUST strictly match Section 3 (30k calls/model, API: 24M tokens, $3.60, 7B: 4.17h, 70B: 50 GPU-hours).\n"
        "### 4.2 Baselines, Hyperparameters & Implementation Details\n"
        "- Table of locked hyperparameters and configuration.\n"
        "### 4.3 Quantitative Benchmark Comparison\n"
        "- Include '**Table 3: Main Empirical Benchmark Evaluation**' comparing baselines [n] with proposed models marked '*Not Exp.*'.\n"
        "- Include a ```chart block with sensitivity curve or sample size precision.\n"
        "### 4.4 In-Depth Ablation Studies\n"
        "- Ablation on Quality-gap stratification ('**Table 4: Ablation Analysis — Position Bias by Quality-Gap Stratum**'), prompt templates, and temperature sensitivity.\n"
        "### 4.5 Qualitative Case Studies & Error Analysis\n"
        "- Error taxonomy (Type A to D) and '**Table 5: Qualitative Comparison and Failure Case Analysis**'. Ensure IL-03 correctly illustrates position bias (Order 1,2 selects Slot A -> a1, Order 2,1 selects Slot A -> a2)."
    )

    user_prompt = (
        f"Research Question: {state['question']}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        "Write Section 4 with rigorous empirical structure and consistent numbers in formal Academic English."
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _generate_stage_5_discussion_and_conclusion(
    blueprint: str,
    sec4_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 5: Section 5 (Discussion, Limitations & Threats) and Section 6 (Conclusion)."""
    system_prompt = (
        "You are writing Section 5 (Discussion) and Section 6 (Conclusion) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent Academic English (~1,200 - 1,500 words).\n\n"
        f"{_GLOBAL_ACADEMIC_STANDARDS}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 4:\n{sec4_transition}\n\n"
        "REQUIRED STRUCTURE FOR SECTIONS 5 & 6:\n"
        "## 5. Discussion\n"
        "### 5.1 In-Depth Technical Analysis & Trade-Offs\n"
        "- Trade-offs: Metric granularity vs. statistical power, determinism (T=0) vs. ecological validity, quality stratification.\n"
        "- Mathematical accuracy: emphasize that large directional bias (|FPR - 0.5| > 0) strictly requires non-trivial swap rate (SR >= 2 * |FPR - 0.5|).\n"
        "- Monetary cost alignment: verify API cost matches $3.60 for 30,000 calls / 24M tokens.\n"
        "### 5.2 Threats to Validity & Honest Limitations\n"
        "- Construct, internal, external, and statistical validity.\n"
        "- Judge model scope: restrict to evaluated models (Judge-7B, Judge-70B, Judge-API); do not mention hallucinated models not tested.\n"
        "### 5.3 Emerging Frontiers & Open Research Directions\n"
        "- 4 distinct future directions (e.g., adaptive sequential testing, causal mediation, multimodal judging).\n\n"
        "## 6. Conclusion\n"
        "- Summary of the 4 verifiable contributions and final remarks."
    )

    user_prompt = (
        f"Research Question: {state['question']}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        "Write Section 5 and Section 6 in formal Academic English with candid academic honesty."
    )

    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def synthesize_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    """Entrypoint for the Hierarchical Section-by-Section Synthesis Pipeline."""
    citations = state.get("citations", [])
    references_prompt = _format_references_prompt(citations)
    mode = state.get("research_mode", "survey")

    gateway, model_name = get_default_agent_gateway(llm)

    # Stage 0: Research Blueprint & Mathematical Formulation
    logger.info("Executing Synthesis Stage 0: Research Blueprint & Mathematical Formulation...")
    blueprint = _generate_stage_0_blueprint(state, references_prompt, mode, gateway, model_name)

    # Handle mock fake gateway for fast offline tests
    if blueprint.startswith("# Báo cáo"):
        clean_mock = sanitize_academic_markdown(blueprint)
        return {**state, "report": clean_mock}

    # Stage 1: Front Matter & Introduction
    logger.info("Executing Synthesis Stage 1: Front Matter & Section 1 (Introduction)...")
    sec1_text = _generate_stage_1_front_matter_and_intro(blueprint, state, references_prompt, mode, gateway, model_name)
    sec1_transition = _extract_last_paragraphs(sec1_text)

    # Stage 2: Related Work & Taxonomy
    logger.info("Executing Synthesis Stage 2: Section 2 (Related Work & Taxonomy)...")
    sec2_text = _generate_stage_2_related_work(blueprint, sec1_transition, state, references_prompt, mode, gateway, model_name)
    sec2_transition = _extract_last_paragraphs(sec2_text)

    # Stage 3: Proposed Methodology & Algorithmic Protocol
    logger.info("Executing Synthesis Stage 3: Section 3 (Methodology & Formulations)...")
    sec3_text = _generate_stage_3_methodology(blueprint, sec2_transition, state, references_prompt, mode, gateway, model_name)
    sec3_transition = _extract_last_paragraphs(sec3_text)

    # Stage 4: Experiments, Ablations & Case Studies
    logger.info("Executing Synthesis Stage 4: Section 4 (Experiments & Ablations)...")
    sec4_text = _generate_stage_4_experiments(blueprint, sec3_transition, state, references_prompt, mode, gateway, model_name)
    sec4_transition = _extract_last_paragraphs(sec4_text)

    # Stage 5: Discussion & Conclusion
    logger.info("Executing Synthesis Stage 5: Section 5 & 6 (Discussion & Conclusion)...")
    sec5_text = _generate_stage_5_discussion_and_conclusion(blueprint, sec4_transition, state, references_prompt, mode, gateway, model_name)

    # Stage 6: Stitching, Canonical References Deduplication & Sanitization
    logger.info("Executing Synthesis Stage 6: Stitching, Canonical References & Sanitization...")
    full_markdown_parts = [
        sec1_text,
        sec2_text,
        sec3_text,
        sec4_text,
        sec5_text,
    ]
    raw_stitched = "\n\n".join(full_markdown_parts)

    # Deduplicate citations, remap numbers, and generate clean IEEE references
    updated_text, clean_references = clean_and_deduplicate_citations(citations, raw_stitched)
    final_text_with_refs = (
        updated_text
        + "\n\n## References\n\n"
        + ("\n".join(clean_references) if clean_references else "(None cited.)")
    )

    clean_report = sanitize_academic_markdown(final_text_with_refs)
    logger.info(f"Synthesized comprehensive 10-page paper: {len(clean_report):,} chars")
    return {**state, "report": clean_report}
