"""Hierarchical Section-by-Section Synthesis Pipeline for Top-Tier Academic Papers.

Pipeline 6 chặng (blueprint → 1 Intro → 2 Related/Taxonomy → 3 Methodology → 4 Experiments → 5-6 Discussion/Conclusion),
độc lập với chủ đề: nội dung chỉ được lấy từ draft đã kiểm chứng + danh sách trích dẫn của từng câu hỏi nghiên cứu.

Enforces:
1. Strict Single-Language Lock: one manuscript language (the user's language) across all sections.
2. Zero Pipeline Leakage: Strips meta-commentary, stage labels, and internal scaffolding.
3. Evidence Discipline: every claim/number traces to the draft or a cited [n]; nothing invented.
4. Cross-section Consistency: notation, numbers and terminology fixed by the blueprint.
5. Canonical Citations: Deduplicates papers, removes raw search dumps, formats clean IEEE references.
6. Two modes: 'survey' (taxonomy + benchmark matrix) and 'novel_research' (proposed method + experimental protocol).
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any

from app.agent.evidence.citation_cleaner import clean_and_deduplicate_citations
from app.agent.evidence.dataset_catalog import get_dataset_grounding_context
from app.agent.evidence.report_structure import finalize_structure, source_diversity_warning, strip_dangling_citations
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.agent.language import language_name
from app.agent.profiles import adaptation_rules, audience_profile, field_profile, missing_end_sections
from app.agent.report_postprocess import postprocess_report
from app.agent.state import ResearchState
from app.pipeline.figures import load_figures
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway

logger = logging.getLogger(__name__)

# Catalog dataset chỉ có giá trị cho đề tài LLM-as-a-judge → chỉ chèn khi câu hỏi thật sự liên quan.
_JUDGE_TOPIC_RE = re.compile(r"llm[- ]as[- ]a[- ]judge|pairwise|position bias|swap rate|llmbar|chatbot arena|mt-bench", re.I)

_TABLE_BLOCK_RULE = """   - QUANTITATIVE COMPARISON TABLES (results with numbers) MUST be written as a ```table fenced block containing JSON instead of a Markdown table, e.g.
     ```table
     {"caption": "Main results on dataset X [n]", "header_groups": [{"label": "", "span": 2}, {"label": "Dataset A", "span": 2}], "columns": ["Category", "Method", "F1", "AUC"], "rows": [["Supervised", "TabNet [2]", "97.4", "95.1"], ["", "CNN [2]", "93.0", "90.2"], ["Hybrid", "**Best**", "**98.1**", "**96.0**"]], "bold_rows": []}
     ```
     header_groups is optional (sum of spans = number of columns); an empty first-column cell merges with the cell above (method families); add "highlight_best": "max" (or "min", or {"Latency (ms)": "min", "F1": "max"}) to shade the best value of each numeric column. Every cell is a string. Only use numbers that appear in the draft/references with their [n]; use "–" if unavailable. Descriptive tables (taxonomy, configuration, qualitative cases) stay as Markdown tables.
"""

_CHART_BLOCK_RULE = """   - FIGURES: visualize quantitative values that already appear in the draft/references with a ```chart fenced block containing JSON:
     {"type": "bar", "caption": "What is shown (source [n])", "labels": ["A", "B"], "series": [{"name": "F1 (%)", "values": [90.0, 84.1]}], "y_label": "%"}
     type is one of bar | barh | line | stacked_barh (parts of a whole per row, e.g. win / tie / loss %). Each series has exactly one value per label; use null (never 0) for a missing value. Optional "errors": [..] per series (same length as values; SD or 95% CI, only if the source reports it) draws error bars.
     Pick the figure that matches the evidence (use only numbers reported in the draft/references; never invent values or samples; if there is not enough real data, omit the chart):
       * Performance comparison (proposed vs baselines, per dataset/metric) and ablation (full model vs "w/o module"): grouped bar, with errors when multiple runs are reported.
       * Training/convergence, 1D parameter sensitivity, scalability: {"type": "xyline", "x_label": "Epoch", "y_label": "Loss", "series": [{"name": "Train", "x": [1, 2, 3], "y": [0.9, 0.5, 0.3], "errors": [0.05, 0.04, 0.02]}]} (optional "x_scale"/"y_scale": "log").
       * 2D sensitivity (two hyperparameters): {"type": "heatmap", "x_labels": [...], "y_labels": [...], "matrix": [[...]], "c_label": "F1"}.
       * Feature space (PCA/t-SNE/UMAP points) : {"type": "scatter", "series": [{"name": "Class A", "x": [...], "y": [...]}]}.
       * Distributions: {"type": "histogram" | "boxplot", "series": [{"name": "...", "samples": [...]}]}; latency/response time: {"type": "cdf", "series": [{"name": "...", "samples": [...]}], "percentiles": [95, 99]}.
"""

_IMAGE_BLOCK_RULE = """   - REAL FIGURES: to show a real image from the AVAILABLE FIGURES list, write a ```image fenced block containing JSON:
     {"ref": "F2", "caption": "What the image shows and why it matters ([n])"}
     Use only refs from the list, at most once each, placed where the text discusses them; describe only what the original caption supports. Never refer to images that are not in the list.
"""

# Số hình thật tối đa đưa vào prompt (tránh prompt quá dài với model free).
MAX_PROMPT_FIGURES = 8

_MERMAID_BLOCK_RULE = """   - MERMAID SYNTAX: start with `graph TD` or `graph LR`; give every node a short ASCII id (A, B1, ...) and wrap each label in double quotes, e.g. A["Retriever [3]"] --> B["Reranker"]; no parentheses, brackets, semicolons, pipes or Unicode math symbols inside labels; no `direction` lines; close every `subgraph` with `end`; labels in the manuscript language; at most ~12 nodes. Put a '**Figure N: Caption**' line directly above the block.
"""


def _lang_label(state: ResearchState) -> str:
    return language_name(state.get("language"))


def _global_standards(state: ResearchState, mode: str) -> str:
    """Tiêu chuẩn học thuật chung cho mọi chặng (độc lập chủ đề)."""
    rules = f"""
STRICT PEER-REVIEW PUBLICATION STANDARDS (MANDATORY ACROSS ALL SECTIONS):
1. STRICT SINGLE-LANGUAGE CONSTRAINT:
   - MANUSCRIPT LANGUAGE: {_lang_label(state)}. Write the ENTIRE manuscript (title, abstract, body, figure/table captions, diagram labels, chart captions) in this one language, in formal academic register, even if the draft or references are in another language.
   - Keep unchanged: proper names, method/model names and acronyms, dataset names, citations [n], numbers, LaTeX and code. The structural markers '## Abstract', '**Keywords:**', '**Table N:**', '**Figure N:**' and '## References' keep their English tokens (the renderer parses them), but the text after them is in the manuscript language.
   - NEVER mix languages inside a paragraph, a caption or a diagram label.
   - HEADINGS: use only '## N. Title' and '### N.M Title' (never '####'); for finer divisions use a bold run-in lead such as '**Metric definitions.**'. Do not add a 'Paper Organization' subsection or front-matter lines such as Manuscript Type / Protocol Version.
2. ZERO META-PIPELINE LEAKAGE:
   - NEVER output internal pipeline terminology such as 'Blueprint', 'Stage Summary', 'Chặng', or meta-instructions.
   - Refer to previous parts naturally using standard academic conventions (e.g., 'as formalized in Section 3').
3. QUANTITATIVE DENSITY (EVIDENCE-BACKED NUMBERS):
   - The Draft Basis ends with a 'Quantitative Evidence Ledger'. Build tables, charts and claims from it: every relevant value in the ledger should appear somewhere in the paper with its [n].
   - Prefer ONE dense comparison table (rows = methods/models/studies, columns = datasets/metrics, '–' for missing cells, add an 'Average' column only if all its inputs exist) over several sparse ones; set "highlight_best" so the best value of each column is highlighted.
   - Support key claims in the text with the specific numbers (e.g. 'F1 of 0.884 on Banking77 [3]') rather than vague words like 'significantly better'.
   - Do NOT copy the ledger itself into the paper as a raw list.
4. EVIDENCE DISCIPLINE (NO FABRICATION):
   - Every factual claim, number, dataset, metric value and method name must come from the Draft Basis or the Available Citations, with the supporting [n]. Do not add outside facts or new citations.
   - NEVER invent statistics, dataset sizes, benchmark scores, author names, institutions, costs, or experimental results. If a value is not in the evidence, describe it qualitatively or write '–'.
   - Do not force-map a method to a citation that is not its original or a direct survey of it. State only what the cited source actually supports.
   - Use ONLY citation numbers listed in Available Citations. Never attribute a number to [n] unless that value appears in the evidence for [n]; if the paper has no experiments of its own, do not call any section 'empirical' or 'experimental results' — present it as a synthesis of reported evidence.
   - Today is {date.today().isoformat()}. Never hard-code a year range for a research agenda or outlook (e.g. '2024-2025'); use relative wording or years that appear in the evidence.
   - Present each comparison table ONCE. Do not restate the same matrix under another caption, and do not repeat Discussion points in the Conclusion.
5. CROSS-SECTION CONSISTENCY:
   - Use exactly the title, acronym, notation, terminology and numbers fixed in the ESTABLISHED DESIGN PLAN. A number or symbol appearing in two sections must be identical.
   - Every mathematical symbol must be defined where it first appears. Only introduce formulas that are necessary and correct.
6. ACADEMIC MODESTY & HONESTY:
   - Avoid hype ('first', 'novel breakthrough', 'proves') unless supported by the evidence. Prefer 'we propose', 'we hypothesize', 'the evidence suggests'.
   - Acknowledge limitations, heterogeneity of the evidence and threats to validity candidly.
7. FORMATTING RULES:
   - Use hyphen '- ' for unordered lists. Never put two list items on one line.
   - Display math $$...$$ MUST be on its own line with empty lines before and after.
   - Every table MUST have a clear caption above it: '**Table N: Caption**'.
   - Mermaid diagrams: every node label in double quotes (NodeId["Label"]), '<br/>' for line breaks, edge labels as -->|"label"|.
{_TABLE_BLOCK_RULE}{_CHART_BLOCK_RULE}{_MERMAID_BLOCK_RULE}"""
    if mode == "novel_research":
        rules += (
            "8. REGISTERED-REPORT RULE (novel research):\n"
            "   - Results of the proposed method that have not been run must be marked '*Not Exp.*'; never fill in assumed numbers for it.\n"
            "   - Baseline numbers may be reported only if they are published in the cited source [n].\n"
        )
    if _JUDGE_TOPIC_RE.search(f"{state.get('question', '')} {state.get('draft', '')}"):
        rules += f"9. BENCHMARK DATASET GROUNDING:\n{get_dataset_grounding_context()}\n"
    rules += adaptation_rules(state)
    figures = state.get("figures") or []
    if figures:
        listing = "\n".join(
            f"   - [{f['id']}] from [{f['cite']}], page {f['page']}: {f['caption']}" for f in figures
        )
        rules += f"AVAILABLE FIGURES (real images extracted from the cited papers):\n{listing}\n{_IMAGE_BLOCK_RULE}"
    return rules


def _collect_figures(citations: list[Any]) -> list[dict]:
    """Hình thật của các paper nội bộ được trích dẫn, theo thứ tự trích dẫn; id F1..Fn, cite = số [n] đầu tiên."""
    first_cite: dict[str, int] = {}
    for i, c in enumerate(citations, start=1):
        pid = getattr(c, "paper_id", "") or (c.get("paper_id") if isinstance(c, dict) else "")
        if pid and pid not in first_cite:
            first_cite[pid] = i
    figures: list[dict] = []
    for pid, cite in first_cite.items():
        for fig in load_figures(pid):
            if len(figures) >= MAX_PROMPT_FIGURES:
                return figures
            figures.append({**fig, "id": f"F{len(figures) + 1}", "cite": cite})
    return figures


# Cấu trúc từng chặng theo chế độ. Tiêu đề viết HOA là marker ổn định cho từng chặng.
_STAGE_STRUCTURES: dict[str, dict[str, str]] = {
    "survey": {
        "stage2": (
            "Section 2 (RELATED WORK AND TAXONOMY)",
            "## 2. Taxonomy & Conceptual Framework\n"
            "### 2.1 Multi-Dimensional Classification\n"
            "- Classify the surveyed approaches along 3-4 orthogonal dimensions. Include a Markdown taxonomy table with caption '**Table 1: Taxonomy of ...**'.\n"
            "### 2.2 Architectural Pipeline\n"
            "- Include one ```mermaid flowchart (graph TD or LR) showing the typical end-to-end pipeline or the taxonomy tree, with citations [n] in labels where relevant.\n"
            "### 2.3 Gaps in Existing Surveys & Literature\n"
            "- State precisely which gaps this survey addresses.",
        ),
        "stage3": (
            "Section 3 (IN-DEPTH TECHNICAL METHODOLOGIES)",
            "## 3. In-Depth Technical Methodologies\n"
            "- Use 3 subsections (### 3.1 - 3.3), one per major paradigm / mechanism family of the taxonomy.\n"
            "- For each: core mechanism, representative works [n], what problem it solves, assumptions, strengths and weaknesses. Compare families against each other.\n"
            "- Include formulas or short pseudocode only when the cited sources give them.",
        ),
        "stage4": (
            "Section 4 (COMPARATIVE EVIDENCE SYNTHESIS)",
            "## 4. Comparative Evidence Synthesis\n"
            "### 4.1 Standard Benchmark Datasets & Metrics\n"
            "- Only datasets and metrics that appear in the evidence; explain why each metric is (in)appropriate.\n"
            "### 4.2 Comprehensive Benchmark Comparison Table\n"
            "- One quantitative comparison table as a ```table JSON block (method [n], paradigm, dataset, metrics) using results reported in the cited sources; group methods by paradigm with header_groups/merged first column when helpful.\n"
            "### 4.3 Quantitative Findings & Trade-off Analysis\n"
            "- Interpret the table; include 1-2 ```chart blocks built only from reported numbers; discuss trade-offs (accuracy vs. latency/cost/interpretability, etc.) and the heterogeneity of the reported evidence.",
        ),
        "stage5": (
            "Sections 5 and 6 (DISCUSSION AND CONCLUSION)",
            "## 5. Discussion & Open Research Challenges\n"
            "### 5.1 Technical Barriers & Trade-offs\n"
            "### 5.2 Scalability, Robustness & Deployment Concerns\n"
            "### 5.3 Open Research Directions\n"
            "- At least 4 concrete, distinct directions grounded in the evidence.\n\n"
            "## 6. Conclusion\n"
            "- Synthesize the overall picture and the outlook; no new claims.",
        ),
    },
    "novel_research": {
        "stage2": (
            "Section 2 (RELATED WORK)",
            "## 2. Related Work\n"
            "### 2.1 Multi-Dimensional Taxonomy of Paradigms\n"
            "- Include a Markdown table comparing prior approaches with caption '**Table 1: Taxonomy and Comparative Overview of Existing Paradigms**'.\n"
            "### 2.2 Deep Comparative Analysis of Existing Mechanisms\n"
            "- Mechanistic critique of prior studies [n]; cite each work only for what it actually shows.\n"
            "### 2.3 Theoretical & Practical Gaps in Current Literature\n"
            "- State the specific gaps that the proposed work addresses.",
        ),
        "stage3": (
            "Section 3 (PROPOSED METHODOLOGY)",
            "## 3. Proposed Methodology\n"
            "### 3.1 Problem Formulation & Foundations\n"
            "- Define inputs, outputs, objective and all notation from the design plan.\n"
            "### 3.2 System Architecture\n"
            "- Describe the end-to-end flow and include one ```mermaid flowchart.\n"
            "### 3.3 Core Components\n"
            "- Each component: purpose, mechanism, how it addresses a gap from Section 2; formulas only where they are well-defined. State clearly which parts are hypotheses.\n"
            "### 3.4 Algorithmic Execution\n"
            "- '**Algorithm 1: ...**' as numbered pseudocode in a ```text block (Input / Output / steps).\n"
            "### 3.5 Complexity & Resource Analysis\n"
            "- Qualitative or analytical complexity; numeric costs only if derivable from stated parameters.",
        ),
        "stage4": (
            "Section 4 (EXPERIMENTS AND RESULTS)",
            "## 4. Experiments and Results\n"
            "### 4.1 Benchmark Datasets, Metrics & Evaluation Protocol\n"
            "- Only datasets and metrics present in the evidence.\n"
            "### 4.2 Baselines & Experimental Setup\n"
            "- Baselines [n] and the configuration as a Markdown table.\n"
            "### 4.3 Quantitative Benchmark Comparison\n"
            "- A ```table JSON block comparing published baseline results [n] with the proposed method (marked '*Not Exp.*' unless supported); optionally one ```chart of real baseline numbers.\n"
            "### 4.4 Ablation Study Design\n"
            "- Ablation variants and what each tests (a ```table block with '*Not Exp.*' for unrun results).\n"
            "### 4.5 Qualitative Analysis\n"
            "- Expected failure modes and case-study protocol, labelled as planned if not executed.",
        ),
        "stage5": (
            "Sections 5 and 6 (DISCUSSION AND CONCLUSION)",
            "## 5. Discussion\n"
            "### 5.1 In-Depth Analysis & Trade-Offs\n"
            "### 5.2 Limitations & Threats to Validity\n"
            "- Construct, internal, external and statistical validity; what has not been tested.\n"
            "### 5.3 Future Directions\n"
            "- 4 distinct, concrete directions.\n\n"
            "## 6. Conclusion and Future Work\n"
            "- Summarize the contributions and final remarks; no new claims.",
        ),
    },
}


def _structure(mode: str, stage: str) -> tuple[str, str]:
    return _STAGE_STRUCTURES["novel_research" if mode == "novel_research" else "survey"][stage]


def _stage_structure(state: ResearchState, mode: str, stage: str) -> tuple[str, str]:
    """Cấu trúc chặng + mục bổ sung theo lĩnh vực (Section 4) và đối tượng đọc (cuối bài)."""
    title, structure = _structure(mode, stage)
    if stage == "stage4" and field_profile(state)["stage4"]:
        structure += "\n" + field_profile(state)["stage4"]
    if stage == "stage5" and audience_profile(state)["end"]:
        structure += "\n\nAFTER THE CONCLUSION, add these unnumbered sections:\n" + audience_profile(state)["end"]
    return title, structure


def _mode_label(mode: str) -> str:
    return "Novel Research Paper" if mode == "novel_research" else "Literature Survey"


def _generate(
    system_prompt: str,
    user_prompt: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    response = gateway.generate(
        messages=[
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        model_name=model_name,
    )
    return response.text.strip()


def _user_prompt(state: ResearchState, instruction: str) -> str:
    return (
        f"Research Question: {state['question']}\n\n"
        f"Manuscript language: {_lang_label(state)}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        f"{instruction}"
    )


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
    """Stage 0: Global architecture, fixed terminology/notation and plan (Bản Thiết Kế Nghiên Cứu Toàn Bài)."""
    system_prompt = (
        "You are a Principal Scientist designing a concise, publication-grade Research Blueprint (Bản Thiết Kế Nghiên Cứu Toàn Bài) "
        f"for a {_mode_label(mode)}.\n"
        "Its purpose is to fix the title, terminology, notation and scope ONCE so that every later section stays consistent. "
        "Use only what is supported by the draft and the citations.\n\n"
        f"{_global_standards(state, mode)}\n\n"
        "Generate the Blueprint in the manuscript language with these parts:\n"
        "1. TITLE & ACRONYM: an academic title specific to the research question"
        + (" (survey form: '[Topic]: A Comprehensive Survey and Taxonomy on ...')" if mode != "novel_research" else " and a concise acronym for the proposed method")
        + ".\n"
        "2. SCOPE & KEY TERMS: definitions of the 5-8 central terms and the boundaries (time span, domains) of the work.\n"
        "3. NOTATION: only symbols that will really be needed (leave empty for a purely descriptive survey).\n"
        + (
            "4. TAXONOMY DIMENSIONS: the 3-4 orthogonal dimensions and their categories used to classify the literature.\n"
            "5. EVIDENCE MAP: which citation numbers [n] support which topic, and which quantitative results are available for the benchmark table.\n"
            if mode != "novel_research"
            else "4. PROPOSED METHOD OUTLINE: components, the gap each one addresses, and the evaluation protocol (datasets, metrics, baselines available in the evidence).\n"
            "5. EVIDENCE MAP: which citation numbers [n] support which baseline or claim.\n"
        )
        + "6. CORE CONTRIBUTIONS: 3-4 distinct, verifiable contributions."
    )
    user_prompt = (
        f"Research Mode: {_mode_label(mode)}\n"
        f"Research Question: {state['question']}\n\n"
        f"Baseline Draft:\n{state.get('draft', '')}\n\n"
        f"Available Citations:\n{references}"
    )
    return _generate(system_prompt, user_prompt, gateway, model_name)


def _generate_stage_1_front_matter_and_intro(
    blueprint: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 1: Front Matter + Section 1 (Title, Abstract, Introduction & Contributions)."""
    contributions = (
        "(Exactly 3-4 itemized contributions using hyphen '- ', each one concrete: e.g. a unified taxonomy, a quantitative comparison, an analysis of trade-offs, a roadmap of open problems.)"
        if mode != "novel_research"
        else "(Exactly 3-4 itemized contributions using hyphen '- ': the proposed architecture/method, its formulation, and the evaluation protocol; no overclaiming.)"
    )
    system_prompt = (
        "You are writing Front Matter and Section 1 (INTRODUCTION) for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent academic prose in the manuscript language (~1,200 - 1,500 words).\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        "REQUIRED STRUCTURE FOR SECTION 1:\n"
        "# [Title from the design plan: at most 15 words, one line of concept + method; no subtitle after a dash]\n\n"
        "**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n"
        "## Abstract\n"
        "(ONE self-contained paragraph of 150-220 words, no bold sub-labels, no bullet list: context & motivation, gap in existing work, approach/scope, key findings or highlights supported by the evidence, implications. No citations [n] and no display math in the abstract.)\n\n"
        "**Keywords:** k1, k2, k3, k4, k5\n\n"
        + (audience_profile(state)["front"] + "\n\n" if audience_profile(state)["front"] else "")
        + "## 1. Introduction\n"
        "### 1.1 Motivation & Background\n"
        "(3-4 full paragraphs on the problem's importance and context, using the evidence [n].)\n"
        "### 1.2 Limitations of Existing Work\n"
        "(3-4 paragraphs on concrete deficiencies of prior work, with [n].)\n"
        "### 1.3 Core Contributions\n"
        f"{contributions}\n"
        "### 1.4 Paper Organization\n"
        "(Outline strictly Sections 2 through 6. Do NOT reference unwritten sections or phantom appendices.)"
    )
    user_prompt = _user_prompt(state, "Write the front matter and Section 1 in the manuscript language with high academic depth.")
    return _generate(system_prompt, user_prompt, gateway, model_name)


def _generate_stage_2_related_work(
    blueprint: str,
    sec1_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 2: Section 2 (Related Work / Taxonomy & Conceptual Framework)."""
    title, structure = _stage_structure(state, mode, "stage2")
    system_prompt = (
        f"You are writing {title} for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent academic prose in the manuscript language (~1,400 - 1,600 words).\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 1:\n{sec1_transition}\n\n"
        f"AVAILABLE CITATIONS:\n{references}\n\n"
        f"REQUIRED STRUCTURE:\n{structure}"
    )
    user_prompt = _user_prompt(state, "Write this section with comprehensive scholarly literature mapping in the manuscript language.")
    return _generate(system_prompt, user_prompt, gateway, model_name)


def _generate_stage_3_methodology(
    blueprint: str,
    sec2_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 3: Section 3 (Proposed Methodology / In-Depth Technical Methodologies)."""
    title, structure = _stage_structure(state, mode, "stage3")
    system_prompt = (
        f"You are writing {title} for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent academic prose in the manuscript language (~2,000 - 2,500 words).\n"
        "DO NOT output any stage summary or meta-commentary at the end.\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 2:\n{sec2_transition}\n\n"
        f"AVAILABLE CITATIONS:\n{references}\n\n"
        f"REQUIRED STRUCTURE:\n{structure}"
    )
    user_prompt = _user_prompt(state, "Write this section with technical completeness and consistent terminology/notation in the manuscript language.")
    return _generate(system_prompt, user_prompt, gateway, model_name)


def _generate_stage_4_experiments(
    blueprint: str,
    sec3_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 4: Section 4 (Experiments & Results / Comparative Evidence Synthesis)."""
    title, structure = _stage_structure(state, mode, "stage4")
    system_prompt = (
        f"You are writing {title} for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent academic prose in the manuscript language (~1,800 - 2,300 words).\n"
        "DO NOT output any stage summary or meta-commentary at the end.\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 3:\n{sec3_transition}\n\n"
        f"AVAILABLE CITATIONS:\n{references}\n\n"
        f"REQUIRED STRUCTURE:\n{structure}"
    )
    user_prompt = _user_prompt(state, "Write this section with a rigorous empirical structure; every number must come from the evidence with its [n].")
    return _generate(system_prompt, user_prompt, gateway, model_name)


def _generate_stage_5_discussion_and_conclusion(
    blueprint: str,
    sec4_transition: str,
    state: ResearchState,
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Stage 5: Section 5 (Discussion, Limitations) and Section 6 (Conclusion)."""
    title, structure = _stage_structure(state, mode, "stage5")
    system_prompt = (
        f"You are writing {title} for a top-tier peer-reviewed academic paper.\n"
        "Write in rigorous, fluent academic prose in the manuscript language (~1,200 - 1,500 words).\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"ESTABLISHED DESIGN PLAN:\n{blueprint}\n\n"
        f"TRANSITION CONTEXT FROM SECTION 4:\n{sec4_transition}\n\n"
        f"AVAILABLE CITATIONS:\n{references}\n\n"
        f"REQUIRED STRUCTURE:\n{structure}\n\n"
        "APPENDIX (after the last required section, only when the draft contains such details):\n"
        "## Appendix A. Implementation and Evaluation Details\n"
        "(150-400 words: dataset/benchmark descriptions, metric definitions, hyper-parameters, evaluation protocol and any extra table the main text refers to. "
        "Use only facts already in the draft or references, with [n]; use bold run-in leads such as '**Datasets.**' instead of '###' headings. "
        "Omit the whole appendix if the draft has no such details; never invent settings.)"
    )
    user_prompt = _user_prompt(state, "Write Sections 5 and 6 in the manuscript language with candid academic honesty.")
    return _generate(system_prompt, user_prompt, gateway, model_name)


# Phần thân đưa vào lời gọi bổ sung; đủ để rút ý chính và thuật ngữ mà không vượt ngữ cảnh model nhỏ.
MAX_APPENDIX_CONTEXT_CHARS = 24000


def _generate_audience_appendix(
    state: ResearchState,
    body: str,
    missing: list[str],
    references: str,
    mode: str,
    gateway: LLMGateway,
    model_name: str | None,
) -> str:
    """Viết riêng các mục cuối bài theo đối tượng đọc mà Stage 5 bỏ sót (Key Takeaways, Glossary, Practical Implications)."""
    wanted = [part for part in audience_profile(state)["end"].split("\n\n") if any(h in part for h in missing)]
    system_prompt = (
        "You are finishing a peer-reviewed paper. Write ONLY the unnumbered sections listed below, in the manuscript language, "
        "based strictly on the paper text provided (use its claims, numbers and [n] citations; never add new facts).\n\n"
        f"{_global_standards(state, mode)}\n\n"
        f"AVAILABLE CITATIONS:\n{references}\n\n"
        "SECTIONS TO WRITE (keep these exact '## ' headings, in this order, and output nothing else):\n" + "\n\n".join(wanted)
    )
    user_prompt = f"Research Question: {state['question']}\n\nPaper text:\n{body[:MAX_APPENDIX_CONTEXT_CHARS]}"
    return _generate(system_prompt, user_prompt, gateway, model_name)


class InsufficientEvidenceError(ValueError):
    """Không có nguồn thật nào cho paper; chặn xuất bản thay vì để LLM tự gán [1]."""


def synthesize_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    """Entrypoint for the Hierarchical Section-by-Section Synthesis Pipeline."""
    citations = state.get("citations", [])
    if not citations:
        raise InsufficientEvidenceError("Không có nguồn nào để trích dẫn: không tạo paper khi References rỗng")
    references_prompt = _format_references_prompt(citations)
    state = {**state, "figures": _collect_figures(citations)}
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

    missing = missing_end_sections(state, raw_stitched)
    if missing:
        logger.warning("Stage 5 bỏ sót mục theo đối tượng %s: %s — gọi bổ sung", state.get("audience"), missing)
        appendix = _generate_audience_appendix(state, raw_stitched, missing, references_prompt, mode, gateway, model_name)
        if appendix and not missing_end_sections(state, raw_stitched + "\n\n" + appendix) == missing:
            raw_stitched += "\n\n" + appendix
        else:
            logger.warning("Lời gọi bổ sung không tạo được mục %s", missing)

    # Deduplicate citations, remap numbers, and generate clean IEEE references
    updated_text, clean_references = clean_and_deduplicate_citations(citations, raw_stitched)
    updated_text = postprocess_report(
        updated_text, state.get("draft", ""), gateway, model_name, state.get("language", "en"), state["figures"],
        evidence_text=" ".join(str(getattr(c, "text_snippet", "") or "") for c in citations),
    )
    updated_text, dangling = strip_dangling_citations(updated_text, len(clean_references))
    if dangling:
        logger.warning("Đã xóa %d marker trích dẫn không có trong References: %s", len(dangling), sorted(set(dangling)))
    warning = source_diversity_warning(updated_text, len(clean_references))
    if warning:
        logger.warning("Chất lượng nguồn: %s", warning)
    updated_text = finalize_structure(updated_text)
    final_text_with_refs = updated_text
    if clean_references:
        final_text_with_refs += "\n\n## References\n\n" + "\n".join(clean_references)

    clean_report = sanitize_academic_markdown(final_text_with_refs)
    logger.info(f"Synthesized comprehensive 10-page paper: {len(clean_report):,} chars")
    return {**state, "report": clean_report}
