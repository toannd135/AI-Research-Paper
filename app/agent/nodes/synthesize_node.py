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

from app.agent.evidence.citation_cleaner import _local_catalog, clean_and_deduplicate_citations_ex
from app.agent.evidence.claim_scan import find_leaked_claims, soften_leaked_claims
from app.agent.evidence.coverage import coverage_target, full_coverage_applies
from app.agent.evidence.dataset_catalog import get_dataset_grounding_context
from app.agent.evidence.quality_gate import merge_structure_issues, trace_text_records
from app.agent.evidence.redact import redact_untraced_cells
from app.agent.evidence.repair import (
    add_uncited_corpus,
    drop_duplicate_charts,
    ensure_methodology_disclosure,
    redact_untraced_chart_points,
    repair_chart_regions,
    repair_ledger_claims,
    soften_novelty_claims,
    soften_promotional_claims,
)
from app.agent.evidence.report_structure import (
    finalize_structure_report,
    source_diversity_warning,
    strip_dangling_citations,
)
from app.agent.evidence.rq_sync import canonical_rqs, dedupe_rq_definitions, enforce_rqs, rq_block, section_rqs
from app.agent.format_sanitizer import sanitize_academic_markdown
from app.agent.language import language_name
from app.agent.profiles import adaptation_rules, audience_profile, field_profile, missing_end_sections
from app.agent.report_postprocess import postprocess_report, reference_years
from app.agent.research_model import contribution_guidance, model_brief
from app.agent.state import ResearchState
from app.ai.llm_gateway.base import LLMGateway, Message
from app.ai.llm_gateway.default import get_default_agent_gateway
from app.core.config import get_settings
from app.core.scope import external_search_allowed
from app.pipeline.figures import load_figures

logger = logging.getLogger(__name__)

# Catalog dataset chỉ có giá trị cho đề tài LLM-as-a-judge → chỉ chèn khi câu hỏi thật sự liên quan.
_JUDGE_TOPIC_RE = re.compile(r"llm[- ]as[- ]a[- ]judge|pairwise|position bias|swap rate|llmbar|chatbot arena|mt-bench", re.I)

_TABLE_BLOCK_RULE = """   - QUANTITATIVE COMPARISON TABLES (results with numbers) MUST be written as a ```table fenced block containing JSON instead of a Markdown table, e.g.
     ```table
     {"caption": "Main results on dataset X [n]", "header_groups": [{"label": "", "span": 2}, {"label": "Dataset A", "span": 2}], "columns": ["Category", "Method", "F1", "AUC"], "rows": [["Supervised", "TabNet [2]", "97.4", "95.1"], ["", "CNN [2]", "93.0", "90.2"], ["Hybrid", "**Best**", "**98.1**", "**96.0**"]], "bold_rows": []}
     ```
     header_groups is optional (sum of spans = number of columns); an empty first-column cell merges with the cell above (method families); add "highlight_best": "max" (or "min", or {"Latency (ms)": "min", "F1": "max"}) to shade the best value of each numeric column. Every cell is a string. Only use numbers that appear in the draft/references with their [n]; use "–" if unavailable. Descriptive tables (taxonomy, configuration, qualitative cases) stay as Markdown tables.
     NOT REPORTED: the Quantitative Evidence Ledger is the only source of numbers; where it says NR (Not Reported) or has no row, write "NR" and never estimate, convert or fill the value. Never state that method A outperforms method B unless both values share dataset version, split, region, metric and unit; otherwise say the results are not directly comparable. If a DOI or other metadata is unknown, leave it out rather than guess.
"""

_CHART_BLOCK_RULE = """   - FIGURES: visualize quantitative values that already appear in the draft/references with a ```chart fenced block containing JSON, e.g.
     {"type": "dot", "caption": "What is shown: metric, dataset/version, split, unit, sources [n], comparability limits", "labels": ["Method A [2]", "Method B [3]"], "series": [{"name": "F1 (%)", "values": [90.0, 84.1]}], "x_label": "F1 (%)"}
     CHART SELECTION POLICY — every figure must answer a distinct research question and show something an existing table or figure cannot show more clearly. Choose the type from the QUESTION, not from the data shape:
       * How do methods differ (methods x metrics/regions, same protocol)? -> "dot" (labels = methods, one series per metric/region).
       * How do two paired conditions of the same study differ (validation vs test, with vs without a module, full vs missing input, before vs after)? -> "dumbbell" (labels = rows, exactly two series = the two conditions; the gap is drawn).
       * How do many configurations affect a result (e.g. input subsets x regions, 2D sensitivity)? -> {"type": "heatmap", "x_labels": [...], "y_labels": [...], "matrix": [[...]], "c_label": "Δ score"}; use null for a cell that is not reported (shown as NR), never 0.
       * Does a result change over a real ordered sequence (epochs, years, parameter values)? -> {"type": "xyline", "x_label": "Epoch", "y_label": "Loss", "series": [{"name": "Train", "x": [1, 2, 3], "y": [0.9, 0.5, 0.3]}]} (optional "x_scale"/"y_scale": "log").
       * Trade-off between two measured quantities (accuracy vs parameters/latency): {"type": "scatter", "series": [{"name": "...", "x": [...], "y": [...]}]}.
       * Distributions: {"type": "histogram" | "boxplot", "series": [{"name": "...", "samples": [...]}]}; latency: {"type": "cdf", "series": [...], "percentiles": [95, 99]}.
       * "bar"/"barh" only for a single metric over a few categories, or with error bars ("errors": [..] per series, SD or 95% CI only if the source reports them; the caption then states the error type and the unit of replication). At most two bar charts in the whole manuscript.
     MANDATORY: (1) no figure that only repeats a table — a table already shows exact values; (2) never put results from different datasets, versions, splits, metrics or units in one panel — make separate figures or skip; (3) a missing value is null (NR), never 0, never estimated; (4) never add a figure just to raise the figure count; (5) the caption is self-explanatory: metric, dataset/version, split, unit, sources [n] and any comparability limit.
     LAYOUT (two-column PDF): figures sit in ONE column by default. Add "layout": "wide" only when labels would be unreadable in one column (e.g. a heatmap with more than 5 columns or a diagram with many horizontal nodes); never to make a figure bigger.
"""

_IMAGE_BLOCK_RULE = """   - REAL FIGURES: to show a real image from the AVAILABLE FIGURES list, write a ```image fenced block containing JSON:
     {"ref": "F2", "caption": "What the image shows and why it matters ([n])"}
     Use only refs from the list, at most once each, placed where the text discusses them; describe only what the original caption supports. Never refer to images that are not in the list.
     IMAGES ARE ILLUSTRATIONS, NOT DATA: you only see an image's caption, never its pixels or plotted values. Never read, estimate or quote numbers from an image (bar heights, curve points, Dice/IoU values) and never build a table or ```chart from one; numeric values come only from the text, tables and ledger of the sources, with [n].
"""

# Số hình thật tối đa đưa vào prompt (tránh prompt quá dài với model free).
MAX_PROMPT_FIGURES = 4

_MERMAID_BLOCK_RULE = """   - MERMAID SYNTAX: start with `graph TD` or `graph LR`; give every node a short ASCII id (A, B1, ...) and wrap each label in double quotes, e.g. A["Retriever [3]"] --> B["Reranker"]; no parentheses, brackets, semicolons, pipes or Unicode math symbols inside labels; no `direction` lines; close every `subgraph` with `end`; labels in the manuscript language; at most ~12 nodes. Put a '**Figure N: Caption**' line directly above the block.
"""


# Chuẩn nội bộ PaperAI về Figure/Table (không phải quy định xuất bản bắt buộc): số lượng chỉ là mục tiêu, không được bịa dữ liệu để cho đủ.
_DISPLAY_ITEMS_RULE = """7b. FIGURES & TABLES POLICY (PaperAI internal quality standard):
   - TARGETS: {targets} These are targets, NOT quotas: NEVER create a figure or table only to reach a count, and NEVER invent Dice, Accuracy, Loss, F1 or any comparison value to fill one. Every result figure/table must come from the Draft Basis, the cited sources or USER-PROVIDED RESULTS, with its [n]. If the evidence is insufficient, use fewer items and say so in the text.
   - Distinguish Figure (diagram, plot, image) from Table (data). Number them in order of appearance (Figure 1, Figure 2, ... / Table 1, ...); give every one a caption that says what it shows; mention every one in the body text ('as shown in Figure 2'); do not show the same data both as a table and as a figure.
   - Plots need axis names, units and a legend when there is more than one series; never use scales or crops that mislead. An image taken from another study must name its source [n].
   - PRIORITY OF FIGURES (use those the evidence supports): (1) research framework / pipeline overview; (2) dataset or input illustration (only a real image from AVAILABLE FIGURES); (3) model/system architecture; (4) training/validation curves (only with reported per-epoch values); (5) qualitative results (real images only); (6) performance comparison of proposed vs. baselines; (7) ablation (only when a component-level improvement is proposed); (8) error analysis.
   - PRIORITY OF TABLES: dataset characteristics; experimental configuration; comparison with baselines; ablation results; quantitative evaluation. Keep descriptive tables (dataset, configuration) as Markdown tables and numeric ones as ```table blocks.
   - REQUIRED CONTENT: research methodology, quantitative evaluation, qualitative evaluation (mandatory for image segmentation/medical imaging when real example images exist; otherwise describe the visual findings reported in the sources), ablation study (when a method is proposed or improved), references sufficient to support the claims.
   - HONESTY ABOUT SCOPE: a literature-based paper cannot prove that a new model reaches any performance. Without USER-PROVIDED RESULTS, present the proposed method's experiments as a PLANNED protocol: planned figures/tables list their design and use '*Not Exp.*' / '–' for unrun values, and published baseline numbers are cited with [n].
"""


def _display_items_rule(state: ResearchState, mode: str) -> str:
    """Mục tiêu số Figure/Table theo loại bài; kết quả của chính đề xuất chỉ có khi người dùng cung cấp số liệu."""
    if mode == "novel_research":
        targets = "6-8 figures and 3-5 tables for a complete experimental paper (AI/ML on images: 5-10 figures); a theoretical paper needs only 1-3 figures."
    else:
        targets = "5-6 figures (taxonomy/framework, pipeline or method comparison, 1-2 quantitative plots restricted to comparable settings, 1 qualitative image) and at least 4 tables (taxonomy, datasets and metrics, quantitative comparison of published results, strengths/limitations/open challenges) for a survey/review; each table must answer one research question."
    return _DISPLAY_ITEMS_RULE.format(targets=targets)


def _source_coverage_rule(state: ResearchState) -> str:
    """Yêu cầu bài cite đủ nhiều paper khác nhau trong danh sách Available Citations (kho nhỏ: cite hết)."""
    available = {getattr(c, "paper_id", None) for c in state.get("citations", [])} - {None}
    target = coverage_target(len(available))
    if target < 2:
        return ""
    scope = "EVERY one of them" if full_coverage_applies(len(available)) else f"at least {target} of them"
    return (
        f"7c. SOURCE COVERAGE: Available Citations hold {len(available)} distinct papers. The manuscript as a whole MUST cite {scope} "
        f"({target} distinct papers), spread across sections (taxonomy, methodology families, benchmark discussion, recent directions); cite a paper only for what it supports, "
        "never add a citation just to reach the count; if a paper truly does not fit any section, mention it in one neutral sentence of the Related Work.\n"
    )


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
   - TAXONOMY AXES: state the number of taxonomy axes ONCE and identically in the Abstract, the Contributions and the taxonomy section, and list exactly those axes. An evaluation-coverage attribute that is not a method-classification axis is a separate 'evaluation dimension', not an extra axis.
   - SCOPE OF EVIDENCE: a result reported by ONE study (e.g. one paper's all-subset table) supports a conclusion only for that study's setting; never present it as the best paradigm of the field. Do not draw a general conclusion about a method family from a value whose configuration is unknown/NR. State whether a table cell is NR because the source does not report it or because the retrieved passages did not contain it. When averaging Dice over the number of available modalities, also give the min/max or per-subset values.
   - TAXONOMY ASSIGNMENT: classify only methods/models, not challenges, datasets or general-purpose backbones; keep segmentation, missing-modality-learning and synthesis-only methods in clearly separated groups; give an assignment rationale (or 'Unclear'/'NR' when the retrieved evidence does not decide) instead of forcing a label.
   - LEDGER CLAIMS: describe the structured numeric records exactly as the EVIDENCE LIMITS state them (which settings they cover, which papers contributed). Never say the records carry a missing-modality configuration unless the EVIDENCE LIMITS report missing-modality groups; the Abstract, tables and Limitations must agree.
6. ACADEMIC MODESTY & HONESTY:
   - Avoid hype ('first', 'novel breakthrough', 'proves') unless supported by the evidence. Never claim 'the first comprehensive' survey/mapping; the corpus is a fixed PDF collection, so state the contribution with its exact scope (e.g. 'a corpus-based synthesis of N studies'). Name prior surveys in the Introduction only if they are in Available Citations and compare them in Related Work. Prefer 'we propose', 'we hypothesize', 'the evidence suggests'.
   - Acknowledge limitations, heterogeneity of the evidence and threats to validity candidly.
   - HEDGING: do not write absolute statements ('necessary', 'always', 'never', 'guarantees', 'solves', 'zero robustness loss') about methods or the field. Scope every general claim to the reviewed corpus or to a cited study ('in the reviewed corpus', 'as reported in [n]') and use 'may', 'suggests' or 'is associated with'.
7. FORMATTING RULES:
   - Use hyphen '- ' for unordered lists. Never put two list items on one line.
   - Display math $$...$$ MUST be on its own line with empty lines before and after.
   - Every table MUST have a clear caption above it: '**Table N: Caption**'.
   - Mermaid diagrams: every node label in double quotes (NodeId["Label"]), '<br/>' for line breaks, edge labels as -->|"label"|.
{_TABLE_BLOCK_RULE}{_CHART_BLOCK_RULE}{_MERMAID_BLOCK_RULE}"""
    rules += _display_items_rule(state, mode)
    rules += _source_coverage_rule(state)
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


_FIG_WORD_RE = re.compile(r"[a-z][a-z0-9+]{2,}")
_FIG_STOP = frozenset(
    {
        "the", "and", "for", "with", "from", "that", "this", "these", "those", "their", "into", "over", "under", "between",
        "across", "using", "based", "via", "than", "are", "was", "were", "how", "what", "which", "when", "where", "why",
        "does", "can", "its", "our", "your", "study", "studies", "method", "methods", "approach", "approaches", "model",
        "models", "result", "results", "figure", "fig", "comparison", "compared", "proposed", "different", "various", "example",
        "examples", "show", "shows", "shown", "network", "networks", "performance", "analysis", "evaluation", "trade", "offs",
        "terms", "effectively", "maintain",
    }
)
MIN_FIGURE_TOPIC_OVERLAP = 2  # caption phải chung ≥2 từ nội dung với câu hỏi (1 từ chung như 'segmentation' chưa đủ)


_SURVEY_WORDS = frozenset({"survey", "surveys", "review", "reviews", "overview", "tutorial", "comprehensive", "systematic"})


def _topic_words(text: str) -> set[str]:
    return {w for w in _FIG_WORD_RE.findall(text.lower()) if w not in _FIG_STOP}


MIN_POOL_FOR_ANCHOR = 6  # pool hình nhỏ hơn mức này thì thống kê độ hiếm không đáng tin → không neo miền
ANCHOR_MAX_DF = 0.3  # từ của câu hỏi xuất hiện ở <30% caption trong pool = từ đặc trưng miền (vd. brain, glioma, BraTS)
_GENERIC_FIG_RE = re.compile(r"\b(?:architecture|overview|framework|pipeline|overall|workflow|schematic|diagram)\b", re.I)


def _domain_anchors(topic_words: set[str], captions: list[str]) -> set[str]:
    """Từ của câu hỏi hiếm trong caption của pool (IDF cao): dùng để loại hình của miền khác dù caption chung 'segmentation/MRI'."""
    if len(captions) < MIN_POOL_FOR_ANCHOR:
        return set()
    word_sets = [_topic_words(c) for c in captions]
    anchors = set()
    for w in topic_words:
        df = sum(1 for s in word_sets if w in s) / len(word_sets)
        if 0 < df <= ANCHOR_MAX_DF:
            anchors.add(w)
    return anchors


def _collect_figures(citations: list[Any], topic: str = "") -> list[dict]:
    """Hình thật của các paper nội bộ được trích dẫn, theo thứ tự trích dẫn; id F1..Fn, cite = số [n] đầu tiên.

    Có `topic` (câu hỏi nghiên cứu) thì chỉ giữ hình có caption liên quan: tránh đưa hình của bài toán khác (vd. phân đoạn tế bào/gan
    trong survey u não) vào bài chỉ vì paper chứa nó được trích dẫn. Ngoài trùng ≥2 từ, hình kết quả/định tính còn phải chứa
    ít nhất một từ đặc trưng miền của câu hỏi (hình kiến trúc/tổng quan được miễn).
    """
    topic_words = _topic_words(topic)
    first_cite: dict[str, int] = {}
    for i, c in enumerate(citations, start=1):
        pid = getattr(c, "paper_id", "") or (c.get("paper_id") if isinstance(c, dict) else "")
        if pid and pid not in first_cite:
            first_cite[pid] = i
    pool = [(pid, cite, fig) for pid, cite in first_cite.items() for fig in load_figures(pid)]
    anchors = _domain_anchors(topic_words, [str(f.get("caption", "")) for _, _, f in pool]) if topic_words else set()
    figures: list[dict] = []
    dropped = 0
    for _pid, cite, fig in pool:
        if len(figures) >= MAX_PROMPT_FIGURES:
            break
        caption = str(fig.get("caption", ""))
        words = _topic_words(caption)
        if topic_words and len(words & topic_words) < MIN_FIGURE_TOPIC_OVERLAP:
            dropped += 1
            continue
        if anchors and not (words & anchors) and not _GENERIC_FIG_RE.search(caption):
            dropped += 1
            continue
        figures.append({**fig, "id": f"F{len(figures) + 1}", "cite": cite})
    if dropped:
        logger.info("Bỏ %d hình có chú thích không liên quan tới câu hỏi nghiên cứu", dropped)
    return figures


# Cấu trúc từng chặng theo chế độ. Tiêu đề viết HOA là marker ổn định cho từng chặng.
_STAGE_STRUCTURES: dict[str, dict[str, str]] = {
    "survey": {
        "stage2": (
            "Sections 2 and 3 (REVIEW METHODOLOGY AND TAXONOMY)",
            "## 2. Review Methodology\n"
            "- Describe ONLY the process that was really carried out. If the REVIEW FACTS contain a USER-DECLARED REVIEW PROTOCOL, describe exactly that protocol "
            "(databases, search strings and dates, criteria, flow counts, number of reviewers, quality assessment) with every number unchanged and nothing added. "
            "Otherwise use the REVIEW FACTS as they are: the corpus is a curated repository of PDFs, retrieval is hybrid search over it with the listed queries, the papers cited are those "
            "the retrieval returned (retrieval coverage, not screening); never invent databases (IEEE Xplore, PubMed, Scopus...), search dates, hit counts, screening numbers or a PRISMA flow that did not happen; "
            "say plainly that this is a narrative review of a curated corpus, not a systematic review, and state this as a limitation.\n"
            "### 2.1 Review Scope\n"
            "- Do NOT list the research questions again (they are stated once, in Section 1.3). In running prose, say that the review addresses RQ1...RQn of Section 1.3 and which later section answers each one; never start a line with 'RQ'.\n"
            "### 2.2 Corpus, Search Strategy and Selection Criteria\n"
            "- The REVIEW FACTS (corpus size, queries, number of papers retrieved/cited, search date); the inclusion rule and quality assessment EXACTLY as given in the REVIEW FACTS (do not add criteria, screening stages or a reviewer count that are not listed there), plus the retrieval configuration.\n"
            "### 2.3 Data Extraction and Quality Assessment\n"
            "- The fields extracted from each paper (architecture, dataset and version, input modalities, metrics, reported values, stated limitations) and how evidence quality is judged (peer-reviewed vs preprint, benchmark vs private data, reported variance). Include a small Markdown table '**Table 1: Data extraction scheme**' only if it adds information.\n"
            "### 2.4 Comparison with Existing Surveys\n"
            "- Compare with earlier surveys ONLY when they are listed under PRIOR SURVEYS IN THE CORPUS and present in AVAILABLE CITATIONS: a Markdown table '**Table N: Positioning against prior surveys**' "
            "with columns Survey [n] | Year | Scope covered | Not covered (gap) | What this review adds, filled only from the cited surveys. Then state, in one paragraph, which insight the analytical framework of this review "
            "yields that the prior classifications did not (a concrete finding, not a renamed taxonomy). If no prior survey is available, say that novelty relative to earlier surveys could not be "
            "established from the corpus, name this as a limitation, and do not claim to be the first or the most comprehensive survey. Never invent surveys.\n\n"
            "## 3. Taxonomy & Conceptual Framework\n"
            "### 3.1 Multi-Dimensional Classification\n"
            "- Present a multi-axis ANALYTICAL FRAMEWORK of 3-4 axes (never claim the axes are 'orthogonal' or 'unified'). Each method appears under exactly ONE primary category per axis (e.g. a hybrid CNN-Transformer is not listed again as a pure Transformer). Method-design axes (how inputs are fused, which architecture, how absent inputs are handled) are distinct from evaluation attributes (dataset version, split, metric), which are analysis attributes, not method classes; say so. Include a Markdown taxonomy table with caption '**Table 2: Taxonomy of ...**' whose citation cells list the actual sources [n] of each row (never a range of the whole corpus).\n"
            "- Then state what this framework reveals that a flat list does not: which axis combinations are well studied, which are empty in the corpus, and which questions about interactions between axes (e.g. does one fusion level degrade less when a given input is absent?) the evidence can or cannot answer.\n"
            "### 3.2 Architectural Pipeline\n"
            "- Include one ```mermaid flowchart showing the typical end-to-end pipeline or the taxonomy tree, with citations [n] in labels where relevant. A taxonomy tree with more than 6 leaves "
            "uses `graph LR` (leaves stacked vertically, readable) and at most 6 leaves per axis; keep node labels under 40 characters.\n"
            "- If at least 4 cited methods can be placed in time, add ONE ```chart timeline of method families: "
            '{"type": "timeline", "caption": "Evolution of method families in the corpus [n...]", "events": [{"year": 2018, "label": "Method A [12]", "group": "Family 1"}]}. '
            "Each label names ONE method with exactly ONE citation [n] and its year MUST be the publication year printed in that reference (events whose year does not match are removed); "
            "group = the method family of the taxonomy (at most 6 groups). It shows how the families emerged over time, not performance.\n"
            "### 3.3 Gaps in Existing Work\n"
            "- State precisely which gaps this survey addresses and how the taxonomy helps close them.",
        ),
        "stage3": (
            "Section 4 (IN-DEPTH TECHNICAL METHODOLOGIES)",
            "## 4. In-Depth Technical Methodologies\n"
            "- Use 3-4 subsections (### 4.1 - 4.4), one per major paradigm / mechanism family of the taxonomy.\n"
            "- For each: core mechanism, representative works [n], what problem it solves, assumptions, strengths and weaknesses. Compare families against each other.\n"
            "- Include formulas or short pseudocode only when the cited sources give them.\n"
            "- End with '### 4.5 Critical Comparative Analysis': a Markdown table '**Table N: Critical comparison of strategies**' (N = the next table number) with columns Strategy | When it helps (evidence [n]) | Main weakness | Open question, "
            "followed by a paragraph that draws cross-paper conclusions (where sources agree, disagree, and why), not a per-paper description. Every cell is grounded in a cited source or says 'not reported'.",
        ),
        "stage4": (
            "Section 5 (COMPARATIVE EVIDENCE SYNTHESIS)",
            "## 5. Comparative Evidence Synthesis\n"
            "### 5.1 Standard Benchmark Datasets & Metrics\n"
            "- Only datasets and metrics that appear in the evidence, with dataset VERSION/year, split and what each metric measures; give them as a Markdown table '**Table 3: Datasets and evaluation metrics**'.\n"
            "### 5.2 Quantitative Comparison of Published Results\n"
            "- One ```table JSON block (method [n], paradigm, dataset+version, sub-region/class, metric, value) with results reported in the cited sources; group methods by paradigm. "
            "UNIT RULE: one metric scale per column — never put ratios (0-1) and percentages (0-100) of the same metric in one column; use separate columns or tables and name the unit in the header; copy values exactly as reported (no conversion, no rounding). "
            "Do not add a second results table that repeats values already shown in another table of the manuscript; write 'NR' (not reported) for missing cells, never '-', '—' or blank. "
            "COMPARABILITY RULE: values are directly comparable only under the same dataset version, split, sub-region/class (e.g. whole tumor, tumor core and enhancing tumor are three different quantities) and metric definition; keep such quantities in separate columns or tables, never average or rank across them, and mark rows from a different setting. Where conditions differ, say the results are not directly comparable.\n"
            "### 5.3 Qualitative Visual Comparison\n"
            "- At most one or two real images from AVAILABLE FIGURES. Each caption must be SPECIFIC (what is shown: method, dataset, case, what the colours/panels mean) and name the source [n], noting it is reproduced from that paper (reuse is subject to the original licence); never reuse a generic caption such as 'Qualitative Visual Comparison'. "
            "Follow the images with ONE analytic paragraph that discusses all of them together (what they show about boundary quality, small structures or failure cases, with [n]); do not describe them one by one without comparing them.\n"
            "### 5.4 Performance Trade-offs\n"
            "- Accuracy vs. latency/cost/interpretability and similar trade-offs, from reported evidence only; aim for 3 ```chart blocks of 3 DIFFERENT chart types WHEN the evidence has enough real, comparable numbers (otherwise include fewer; never invent or pad data just to reach a count), chosen from bar | barh | line/xyline | heatmap | stacked_barh | scatter | boxplot (e.g. one barh ranking of a single metric, one grouped bar across regions, one heatmap of methods x regions, or a line over the number of available modalities when the sources report it), each restricted to ONE comparable setting (same dataset version, same region, same metric) and each plotting only numbers that appear in the evidence with their [n]. Split the evidence into separate charts, e.g. Dice for whole tumor, Dice for tumor core, Dice for enhancing tumor on the same dataset version, or HD95 on its own; one chart per region/metric. Never plot values from incomparable settings on one axis, never mix Dice with HD95 or with parameter counts, never use null, \"relative\"/normalized/estimated values or numbers read from an image; a method with no reported value for that setting is simply left out of that chart (each chart needs >=3 methods).\n"
            "### 5.5 Cross-study Evidence Analysis\n"
            "- Where studies agree or disagree, and why (data, preprocessing, protocol); state how strong the evidence is for each conclusion.",
        ),
        "stage5": (
            "Sections 6 and 7 (DISCUSSION AND CONCLUSION)",
            "## 6. Discussion & Open Research Challenges\n"
            "### 6.1 Technical Barriers & Trade-offs\n"
            "- Include a Markdown table '**Table 4: Strengths, limitations and unresolved challenges**' per method family.\n"
            "### 6.2 Generalization, Robustness & Clinical/Deployment Concerns\n"
            "- Go beyond accuracy: treat clinical reliability as separate dimensions — external / multi-centre validation, scanner or protocol shift, uncertainty estimation and calibration, "
            "failure / out-of-distribution detection, robustness to absent or corrupted inputs, computational cost, and reproducibility (code availability). For EACH dimension give the evidence "
            "with [n] and the source counts from EVIDENCE LIMITS, or state that it was not found in the retrieved evidence (not found ≠ not done). Conclude which dimensions the field has not yet evidenced.\n"
            "### 6.3 Limitations of this Review\n"
            "- Corpus-based narrative review, not exhaustive; possible selection bias; no independent re-run of the published methods. Also state every item listed under EVIDENCE LIMITS as a concrete limitation, using the same wording levels it gives (e.g. which per-input ablations exist versus which complete or cross-study matrices cannot be built), and say which comparisons it prevents. Never contradict a table or figure of the manuscript.\n"
            "### 6.4 Open Research Directions\n"
            "- Before the directions, ONE ```mermaid `graph LR` research roadmap: one chain per direction, Gap → Direction → Evaluation protocol, e.g. "
            'G1["Gap: no external validation [4]"] --> D1["Direction: multi-site training"] --> E1["Evaluate: held-out sites, same metric"]; '
            "at most 6 chains, each gap stated earlier in the manuscript with its [n]; labels under 45 characters; give it a caption line '**Figure N: Research roadmap ...**' above the block.\n"
            "- At least 4 concrete, distinct directions grounded in the evidence. For EACH give, in 2-4 sentences: the research gap (with [n]); why current methods do not solve it; a concrete approach AND how it should be evaluated (protocol, data, metrics); and which research question (RQ) it follows from. No generic directions.\n\n"
            "## 7. Conclusion\n"
            "- Answer EVERY canonical research question (RQ1, RQ2, ...) in one or two sentences each, in order and labelled with its RQ number, then give the outlook; no new claims.",
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
            "- Describe the end-to-end flow and include one ```mermaid flowchart as the research framework (Figure 1) and, when the model has distinct modules, a second ```mermaid architecture diagram.\n"
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
            "- Only datasets and metrics present in the evidence; summarise them in a Markdown table (dataset characteristics) and, if real images are available, one ```image block illustrating the input data.\n"
            "### 4.2 Baselines & Experimental Setup\n"
            "- Baselines [n] and the experimental configuration (hyper-parameters, hardware, splits) as a Markdown table.\n"
            "### 4.3 Quantitative Benchmark Comparison\n"
            "- A ```table JSON block comparing published baseline results [n] with the proposed method (marked '*Not Exp.*' unless supported); 1-2 ```chart blocks of real baseline numbers (different metrics or settings).\n"
            "### 4.4 Ablation Study Design\n"
            "- Ablation variants and what each tests (a ```table block with '*Not Exp.*' for unrun results).\n"
            "### 4.5 Qualitative Analysis\n"
            "- Qualitative results (real ```image blocks if available) and error analysis; otherwise expected failure modes and case-study protocol, labelled as planned if not executed.",
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
    if stage in ("stage3", "stage4") and contribution_guidance(state):
        structure += "\n" + contribution_guidance(state)
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


_SURVEY_TITLE_RE = re.compile(r"\b(?:survey|review|overview|state of the art|state-of-the-art|tutorial)\b", re.IGNORECASE)


def _prior_surveys_fact(state: ResearchState, catalog: dict[str, dict[str, Any]]) -> str:
    """Survey/review có thật trong kho (theo tiêu đề catalog) và số [n] nếu đã được truy xuất — căn cứ duy nhất để so novelty."""
    numbers: dict[str, int] = {}
    for n, c in enumerate(state.get("citations", []), start=1):
        numbers.setdefault(str(getattr(c, "paper_id", "")), n)
    found = [(pid, meta) for pid, meta in catalog.items() if _SURVEY_TITLE_RE.search(str((meta or {}).get("title", "")))]
    # Bảng so sánh survey chỉ được gồm survey CÙNG chủ đề: tiêu đề chung ≥2 từ nội dung với câu hỏi (bỏ chính từ survey/review)
    topic = _topic_words(str(state.get("question", ""))) - _SURVEY_WORDS
    off_topic = 0
    if topic:
        on_topic = [(pid, meta) for pid, meta in found if len(_topic_words(str(meta.get("title", ""))) & topic) >= MIN_FIGURE_TOPIC_OVERLAP]
        off_topic, found = len(found) - len(on_topic), on_topic
    if not found:
        return "PRIOR SURVEYS IN THE CORPUS: none on this topic. Novelty relative to earlier surveys cannot be established; do not claim it.\n\n"
    lines = [
        f"- {'[' + str(numbers[pid]) + ']' if pid in numbers else '(not retrieved, cannot be cited)'} {meta.get('title')} ({meta.get('year', 'n.d.')})"
        for pid, meta in found[:12]
    ]
    note = (
        f"\n- {off_topic} other survey(s) in the corpus cover a different topic: do NOT list them in any survey-comparison table."
        if off_topic else ""
    )
    return "PRIOR SURVEYS IN THE CORPUS ON THIS TOPIC (title-based; compare against these only):\n" + "\n".join(lines) + note + "\n\n"


# Chỉ số [n] trong evidence đánh theo đoạn trích (nhiều đoạn/paper); LLM từng suy "73 papers" từ [73] trong khi kho có 40 paper.
def _year_range_fact(catalog: dict, cited: set) -> str:
    """Dải năm xuất bản thật của các paper được cite (từ catalog); rỗng nếu catalog không có năm."""
    years = [int(y) for pid in cited if (y := str((catalog.get(str(pid)) or {}).get("year", ""))).isdigit()]
    if not years:
        return ""
    return (
        f"- Publication years of the cited papers: {min(years)}-{max(years)}. State this as the publication range; a dataset's own "
        "year range (e.g. a challenge's editions) is a different scope and must be labelled as such.\n"
    )


_CITATION_COUNT_RULE = (
    "- Citation markers [n] index retrieved passages (several per paper), NOT papers: never derive a paper or study count "
    "from the largest [n]. The only paper counts you may state are the ones given above.\n"
)


def _review_facts(state: ResearchState, mode: str) -> str:
    """Số liệu thật về quy trình thu thập nguồn, để chương Review Methodology không bịa cơ sở dữ liệu/số lượng sàng lọc."""
    if mode == "novel_research":
        return ""
    settings = get_settings()
    cited = {getattr(c, "paper_id", None) for c in state.get("citations", [])} - {None}
    queries = "; ".join(f'"{q}"' for q in (state.get("search_queries") or [])[:8]) or "(not recorded)"
    catalog = _local_catalog()
    corpus = len(catalog) or "unknown"
    not_retrieved = len(set(catalog) - {str(c) for c in cited}) if catalog else None
    surveys = _prior_surveys_fact(state, catalog)
    from app.agent.evidence.review_protocol import load_protocol, protocol_facts, validate_protocol

    protocol = load_protocol()
    if protocol and not validate_protocol(protocol, len(catalog) or None):
        # Giao thức thật do người dùng khai báo; RAG chỉ là công cụ trích xuất bằng chứng từ các nghiên cứu đã đưa vào
        return surveys + protocol_facts(protocol) + (
            f"- Evidence extraction support: hybrid retrieval over the {corpus} included full texts (embedding {settings.embedding_model}, "
            f"reranker {settings.reranker_model}); {len(cited)} of them were retrieved as evidence for this manuscript"
            + (f" and {not_retrieved} were not retrieved by any query (state this as a coverage limitation)" if not_retrieved else "")
            + ". Every extracted value is checked to appear verbatim in the cited PDF passage.\n"
            + _CITATION_COUNT_RULE
        )
    scope = "the curated internal PDF repository only" if not external_search_allowed() else "the internal repository plus an external scholarly index (OpenAlex)"
    return surveys + (
        "REVIEW FACTS (the only facts about the search process you may state in Section 2; do not add others):\n"
        f"- Sources searched: {scope}.\n"
        f"- Corpus size: {corpus} papers in the repository catalog; {len(cited)} distinct papers were retrieved as evidence for this manuscript.\n"
        + _CITATION_COUNT_RULE
        + _year_range_fact(catalog, cited)
        + (
            f"- {not_retrieved} catalog papers were not returned by any query and are therefore not discussed. They were not excluded by a screening decision "
            "with recorded reasons; state this plainly as a retrieval limitation (relevant work may have been missed).\n"
            if not_retrieved
            else ""
        )
        +
        f"- Search queries used (hybrid dense+sparse retrieval with reranking): {queries}.\n"
        f"- Search date: {date.today().isoformat()}.\n"
        f"- Retrieval configuration: embedding model {settings.embedding_model}, reranker {settings.reranker_model}, hybrid score weights "
        f"dense {settings.hybrid_alpha} / sparse {settings.hybrid_beta}, at most {settings.local_max_chunks_per_paper} chunks per paper kept as evidence.\n"
        "- Inclusion rule actually applied: a paper is included if it is in the repository and was returned by the retrieval for at least one query. "
        "No other inclusion or exclusion criterion, and no manual screening, was applied; do not state any other criterion.\n"
        "- Quality assessment actually applied: automatic checks only (each reported value must appear verbatim in the cited PDF passage; comparability of "
        "dataset version, split, region and metric). No per-study risk-of-bias score, no GRADE certainty-of-evidence rating and no independent second reviewer; "
        "state all three plainly in Section 2.\n"
        "- No independent title/abstract screening or PRISMA flow was performed beyond retrieval relevance. "
        "Never call this a systematic review and never mention PRISMA except to say that it was not applied.\n"
    )


def _evidence_limits_text(state: ResearchState) -> str:
    """Giới hạn thật của số liệu đã trích (ma trận missing-modality, độ biến thiên); rỗng khi chưa chạy bước trích xuất."""
    if state.get("results") is None or state.get("research_mode", "survey") == "novel_research":
        return ""
    from app.agent.evidence.extractor import records_from_dicts
    from app.agent.evidence.quant_analysis import evidence_limits

    citations = state.get("citations", [])
    paper_to_n: dict[str, int] = {}
    for n, cit in enumerate(citations, start=1):
        paper_to_n.setdefault(cit.paper_id, n)
    from app.agent.evidence.evidence_tiers import classify_evidence, tiers_fact
    from app.agent.evidence.study_profile import study_attributes

    attrs = study_attributes(state.get("evidence", []))
    records = records_from_dicts(state["results"])
    tiers = tiers_fact(classify_evidence(records, paper_to_n, state.get("question", "")), paper_to_n)
    return evidence_limits(records, paper_to_n, len(paper_to_n), attrs) + ("\n" + tiers if tiers else "")


def _research_context(state: ResearchState) -> str:
    """Research Knowledge Model, kết quả người dùng cung cấp và venue đích, đưa vào prompt của mọi chặng."""
    parts = [model_brief(state.get("research_model")), _review_facts(state, state.get("research_mode", "survey")), _evidence_limits_text(state)]
    if state.get("user_results"):
        parts.append(
            "USER-PROVIDED EXPERIMENT RESULTS (the only measured results of the proposed work; report them faithfully, do not alter or extend them):\n"
            f"{state['user_results']}"
        )
    if state.get("target_venue"):
        parts.append(f"TARGET VENUE: {state['target_venue']} — follow its usual conventions for structure and length.")
    return "".join(f"{p}\n\n" for p in parts if p)


def _user_prompt(state: ResearchState, instruction: str) -> str:
    return (
        f"Research Question: {state['question']}\n\n"
        f"Manuscript language: {_lang_label(state)}\n\n"
        f"Draft Basis:\n{state.get('draft', '')}\n\n"
        f"{_research_context(state)}"
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

        local = _local_catalog().get(str(pid))
        ref_line = f"[{i}] {pid}" if not local else f"[{i}] {local.get('title')} ({local.get('year')})"
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
            "4. TAXONOMY AXES: the 3-4 analysis axes (a multi-axis framework, not claimed orthogonal) and their categories; each method gets one primary category per axis.\n"
            "5. EVIDENCE MAP: which citation numbers [n] support which topic, and which quantitative results are available for the benchmark table.\n"
            if mode != "novel_research"
            else "4. PROPOSED METHOD OUTLINE: components, the gap each one addresses, and the evaluation protocol (datasets, metrics, baselines available in the evidence).\n"
            "5. EVIDENCE MAP: which citation numbers [n] support which baseline or claim.\n"
        )
        + "6. CORE CONTRIBUTIONS: 3-4 distinct, verifiable contributions."
        + (
            "\n7. RESEARCH QUESTIONS: 3-4 numbered questions, each on its own line written exactly as 'RQ1. <question>?', 'RQ2. <question>?' ... "
            "They are the ONLY research questions of the manuscript: the Introduction lists them verbatim (once, nowhere else) and the Conclusion will answer each one. "
            "Each question must be answerable from the evidence: if EVIDENCE LIMITS show that the numbers a question would need (e.g. latency/FLOPs, results for every subset of inputs, variance) were not extracted, "
            "phrase it as 'How do existing methods formulate and evaluate X, and what evidence gaps remain?' instead of asking for a quantity the corpus cannot provide."
            if mode != "novel_research"
            else ""
        )
    )
    user_prompt = (
        f"Research Mode: {_mode_label(mode)}\n"
        f"Research Question: {state['question']}\n\n"
        f"Baseline Draft:\n{state.get('draft', '')}\n\n"
        f"{_research_context(state)}"
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
        "(Exactly 3-4 itemized contributions using hyphen '- ', each one concrete and checkable: what is synthesised, from how many sources, and what it reveals (e.g. which evaluation settings are never reported). "
        "Do not present a renamed taxonomy as a contribution by itself; do not claim 'first', 'unified' or 'comprehensive' unless PRIOR SURVEYS IN THE CORPUS supports it.)"
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
        "## Abstract\n"
        "(ONE self-contained paragraph of 150-220 words, no bold sub-labels, no bullet list: context & motivation, gap in existing work, approach/scope, key findings or highlights supported by the evidence, implications. No citations [n] and no display math in the abstract.)\n\n"
        "**Keywords:** k1, k2, k3, k4, k5\n\n"
        + (audience_profile(state)["front"] + "\n\n" if audience_profile(state)["front"] else "")
        + "## 1. Introduction\n"
        "### 1.1 Motivation & Background\n"
        "(3-4 full paragraphs on the problem's importance and context, using the evidence [n].)\n"
        + (
            "### 1.2 Limitations of Existing Surveys\n"
            "(2-3 paragraphs on what earlier surveys cover and miss, ONLY from surveys present in the citations; if none is available, say the coverage of earlier surveys was not systematically compared. Never invent surveys.)\n"
            "### 1.3 Research Gaps and Research Questions\n"
            "(The specific gaps, then the CANONICAL RESEARCH QUESTIONS from the design plan VERBATIM, one per line as '**RQ1.** ...'; if the design plan lists none, write 3-4 numbered questions RQ1... They are answered in Section 7.)\n"
            "### 1.4 Core Contributions\n"
            f"{contributions}\n"
            "### 1.5 Paper Organization\n"
            "(Outline strictly Sections 2 through 7. Do NOT reference unwritten sections or phantom appendices.)"
            if mode != "novel_research"
            else "### 1.2 Limitations of Existing Work\n"
            "(3-4 paragraphs on concrete deficiencies of prior work, with [n].)\n"
            "### 1.3 Core Contributions\n"
            f"{contributions}\n"
            "### 1.4 Paper Organization\n"
            "(Outline strictly Sections 2 through 6. Do NOT reference unwritten sections or phantom appendices.)"
        )
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


def _run_quality_gate(state: ResearchState, text: str, numbered_citations: list | None = None) -> dict | None:
    from app.agent.evidence.quality_gate import run_quality_gate

    try:
        report = run_quality_gate(state, text, numbered_citations=numbered_citations)
    except (KeyError, ValueError, TypeError, AttributeError, OSError):
        logger.exception("Quality Gate lỗi, bỏ qua validation_report")
        return None
    logger.info("Quality Gate: passed=%s, %d lỗi chặn, %d cảnh báo", report["passed"], len(report["blocking"]), len(report["warnings"]))
    return report


def _verify_final_report(
    state: ResearchState,
    report: str,
    numbered_citations: list,
    draft_gate: dict | None,
    structure_blocking: list[str],
    structure_warnings: list[str],
) -> tuple[str, dict | None]:
    """Kiểm chứng và sửa trên ĐÚNG chuỗi sẽ xuất ra (gate lần 1 chạy trên bản thô, trước khi chèn bảng/đánh số lại [n]).

    1. gỡ ô số không truy vết được khỏi bảng (thay bằng NR); 2. chạy lại gate với ánh xạ [n] mới → paper;
    3. `validation_report` mô tả bản cuối, kèm `draft_gate` (số lỗi của bản thô) và `redacted_cells`.
    Lỗi bất ngờ ở bước này không làm sập graph: giữ báo cáo + gate của bản thô.
    """
    try:
        records = trace_text_records(state, report, numbered_citations)
        report, redacted = redact_untraced_cells(report, records)
    except (KeyError, ValueError, TypeError, AttributeError, OSError):
        logger.exception("Gỡ ô số không truy vết được lỗi, giữ nguyên báo cáo")
        redacted = []
    try:
        # đếm lại khối trên bản đã gỡ bảng (số khối không đổi) rồi gỡ điểm biểu đồ
        report, redacted_points = redact_untraced_chart_points(report, trace_text_records(state, report, numbered_citations))
        redacted = redacted + redacted_points
    except (KeyError, ValueError, TypeError, AttributeError, OSError):
        logger.exception("Gỡ điểm biểu đồ không truy vết được lỗi, giữ nguyên báo cáo")
    final_gate = _run_quality_gate(state, report, numbered_citations)
    if final_gate is None:
        return report, merge_structure_issues(draft_gate, structure_blocking, structure_warnings)
    final_gate = merge_structure_issues(final_gate, structure_blocking, structure_warnings)
    summary = (
        {"passed": draft_gate["passed"], "blocking": len(draft_gate["blocking"]), "warnings": len(draft_gate["warnings"])}
        if draft_gate
        else None
    )
    return report, {**final_gate, "draft_gate": summary, "redacted_cells": redacted}


class InsufficientEvidenceError(ValueError):
    """Không có nguồn thật nào cho paper; chặn xuất bản thay vì để LLM tự gán [1]."""


def synthesize_node(state: ResearchState, llm: LLMGateway | None = None) -> ResearchState:
    """Entrypoint for the Hierarchical Section-by-Section Synthesis Pipeline."""
    citations = state.get("citations", [])
    if not citations:
        raise InsufficientEvidenceError("Không có nguồn nào để trích dẫn: không tạo paper khi References rỗng")
    references_prompt = _format_references_prompt(citations)
    state = {**state, "figures": _collect_figures(citations, str(state.get("question", "")))}
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

    # RQ chuẩn: ưu tiên blueprint; nếu blueprint không có thì lấy bộ RQ ở Introduction làm nguồn duy nhất cho các chặng sau
    canon_rqs = canonical_rqs(blueprint) if mode != "novel_research" else []
    if mode != "novel_research" and not canon_rqs:
        intro_rqs = next(iter(section_rqs(sec1_text).values()), [])
        canon_rqs = canonical_rqs("\n".join(f"RQ{n}. {body}" for n, body in intro_rqs))
    if canon_rqs:
        blueprint = f"{blueprint}\n\n{rq_block(canon_rqs)}"
    else:
        logger.warning("Không đọc được RQ chuẩn từ blueprint hay Introduction; Quality Gate sẽ kiểm tra lệch RQ")

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
    raw_stitched = enforce_rqs("\n\n".join(full_markdown_parts), canon_rqs)
    raw_stitched, rq_dupes = dedupe_rq_definitions(raw_stitched)
    if rq_dupes:
        logger.warning("Gỡ danh sách RQ lặp ở mục %s (chỉ giữ định nghĩa đầu tiên)", rq_dupes)

    missing = missing_end_sections(state, raw_stitched)
    if missing:
        logger.warning("Stage 5 bỏ sót mục theo đối tượng %s: %s — gọi bổ sung", state.get("audience"), missing)
        appendix = _generate_audience_appendix(state, raw_stitched, missing, references_prompt, mode, gateway, model_name)
        if appendix and not missing_end_sections(state, raw_stitched + "\n\n" + appendix) == missing:
            raw_stitched += "\n\n" + appendix
        else:
            logger.warning("Lời gọi bổ sung không tạo được mục %s", missing)

    # Quality Gate trên văn bản chưa đánh số lại [n]: không sửa gì, chỉ ghi validation_report; lỗi gate không làm sập graph
    validation_report = _run_quality_gate(state, raw_stitched)

    # Sơ đồ luồng PRISMA từ đúng số người dùng khai báo (review_protocol.json hợp lệ); không có tệp → không có sơ đồ
    has_protocol = False
    disclosure_counts: tuple[int, int, int] | None = None  # (số bài cite, số record, số bài có record) — chỉ khi không có protocol
    if mode != "novel_research":
        from app.agent.evidence.review_protocol import inject_prisma, load_protocol, prisma_block, validate_protocol

        protocol = load_protocol()
        if protocol and not validate_protocol(protocol, len(_local_catalog()) or None):
            raw_stitched = inject_prisma(raw_stitched, prisma_block(protocol))
            has_protocol = True

    # Phase 4: bảng Δ/ablation và scatter đánh đổi từ bản ghi đã kiểm chứng; chèn TRƯỚC khi đánh số lại [n]
    if state.get("results"):
        from app.agent.evidence.extractor import records_from_dicts
        from app.agent.evidence.quant_analysis import build_quant_blocks, inject_quant_blocks

        paper_to_n: dict[str, int] = {}
        for n, cit in enumerate(citations, start=1):
            paper_to_n.setdefault(cit.paper_id, n)
        from app.agent.evidence.evidence_tiers import classify_evidence
        from app.agent.evidence.study_profile import study_attributes

        attrs = study_attributes(state.get("evidence", []))
        records = records_from_dicts(state["results"])
        tiers = classify_evidence(records, paper_to_n, state.get("question", ""))["tiers"]
        raw_stitched = inject_quant_blocks(raw_stitched, build_quant_blocks(records, paper_to_n, attrs, tiers))

    # Kho nhỏ phải cite hết: liệt kê paper chưa cite bằng chỉ số [k] thô, TRƯỚC khi đánh số lại
    try:
        raw_stitched, _ = add_uncited_corpus(raw_stitched, citations, _local_catalog())
    except (KeyError, ValueError, TypeError, AttributeError, OSError):
        logger.exception("Bổ sung paper chưa cite lỗi, giữ nguyên bài")

    # Deduplicate citations, remap numbers, and generate clean IEEE references
    updated_text, clean_references, numbered_citations = clean_and_deduplicate_citations_ex(citations, raw_stitched)
    if mode != "novel_research" and not has_protocol:
        # không có protocol người dùng khai báo → sơ đồ hình thành corpus trung thực từ số đếm của chính lần chạy (không phải PRISMA)
        from app.agent.evidence.corpus_flow import corpus_flow_block, inject_corpus_flow
        from app.core.scope import get_allowed_paper_ids

        allowed = get_allowed_paper_ids()
        retrieved = {getattr(getattr(sc, "chunk", sc), "paper_id", None) for sc in state.get("evidence", [])} - {None}
        with_results = {r.get("paper_id") for r in state.get("results") or []} & {c.get("paper_id") if isinstance(c, dict) else getattr(c, "paper_id", None) for c in numbered_citations}
        updated_text = inject_corpus_flow(
            updated_text, corpus_flow_block(len(allowed) if allowed else None, len(retrieved), len(clean_references), len(with_results))
        )
        disclosure_counts = (len(clean_references), len(state.get("results") or []), len(with_results))
    updated_text = postprocess_report(
        updated_text, state.get("draft", ""), gateway, model_name, state.get("language", "en"), state["figures"],
        evidence_text=" ".join(str(getattr(c, "text_snippet", "") or "") for c in citations),
        min_charts=3 if mode == "survey" else 1,
        ref_years=reference_years(clean_references),
    )
    updated_text, dangling = strip_dangling_citations(updated_text, len(clean_references))
    if dangling:
        logger.warning("Đã xóa %d marker trích dẫn không có trong References: %s", len(dangling), sorted(set(dangling)))
    warning = source_diversity_warning(updated_text, len(clean_references))
    if warning:
        logger.warning("Chất lượng nguồn: %s", warning)
    # Repair tất định cho lỗi chặn mà gate chỉ báo: biểu đồ trộn vùng, câu ledger missing-modality khi sổ cái không có
    try:
        updated_text, _ = repair_chart_regions(updated_text)
        updated_text, _ = drop_duplicate_charts(updated_text)
    except (KeyError, ValueError, TypeError, AttributeError):
        logger.exception("Sửa biểu đồ trộn vùng lỗi, giữ nguyên")
    try:
        from app.agent.evidence.quality_gate import _missing_modality_groups

        updated_text, _ = repair_ledger_claims(updated_text, _missing_modality_groups(state))
    except (KeyError, ValueError, TypeError, AttributeError):
        logger.exception("Sửa câu ledger missing-modality lỗi, giữ nguyên")
    updated_text, _ = soften_promotional_claims(updated_text)
    updated_text, _ = soften_novelty_claims(updated_text)
    if disclosure_counts:
        updated_text, _ = ensure_methodology_disclosure(updated_text, *disclosure_counts)
    updated_text, dangling_refs, low_confidence_refs = finalize_structure_report(updated_text)
    if low_confidence_refs:
        logger.warning("Tham chiếu bảng/hình gán theo vị trí (không khớp nội dung): %s", low_confidence_refs)
    structure_blocking = [f"tham chiếu tài liệu: {p}" for p in dangling_refs]
    structure_warnings = [f"tham chiếu bảng/hình gán theo vị trí gần nhất, cần kiểm tra: {r}" for r in low_confidence_refs]
    research_model = state.get("research_model")
    if research_model and research_model.get("claims"):
        leaks = find_leaked_claims(updated_text, research_model["claims"])
        if leaks:
            logger.warning("Báo cáo khẳng định %d câu cho claim chưa được chứng minh — hạ giọng", len(leaks))
            updated_text, unresolved = soften_leaked_claims(updated_text, leaks, gateway, model_name)
            validation = {**research_model.get("validation", {}), "leaked_claims": unresolved}
            state = {**state, "research_model": {**research_model, "validation": validation}}
    final_text_with_refs = updated_text
    if clean_references:
        final_text_with_refs += "\n\n## References\n\n" + "\n".join(clean_references)

    clean_report = sanitize_academic_markdown(final_text_with_refs)
    clean_report, validation_report = _verify_final_report(
        state, clean_report, numbered_citations, validation_report, structure_blocking, structure_warnings
    )
    logger.info(f"Synthesized comprehensive 10-page paper: {len(clean_report):,} chars")
    return {**state, "report": clean_report, "validation_report": validation_report}
