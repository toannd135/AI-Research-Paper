from app.agent.format_sanitizer import (
    sanitize_academic_markdown,
    sanitize_author_placeholders,
    sanitize_code_and_algorithm_blocks,
    sanitize_display_captions,
    sanitize_latex_math,
    sanitize_mermaid_block,
)


def test_sanitize_mermaid_unquoted_labels_and_newlines():
    raw_mermaid = """graph TD
    subgraph Phase1_Sensitivity[Phase 1: Sensitivity Estimation (One-shot)]
        M[Pre-trained Model\\n(e.g., DeBERTa-v3-small)]
        Sens[Compute S_l = Mean(||G_l||_F^2)]
        Ranks[Integer Rank Config {r_l}]
    end
    M --> Sens
"""
    cleaned = sanitize_mermaid_block(raw_mermaid)
    assert 'subgraph Phase1_Sensitivity ["Phase 1: Sensitivity Estimation (One-shot)"]' in cleaned
    assert 'M["Pre-trained Model<br/>(e.g., DeBERTa-v3-small)"]' in cleaned
    assert 'Sens["Compute S_l = Mean(‖G_l‖_F^2)"]' in cleaned
    assert 'Ranks["Integer Rank Config (r_l)"]' in cleaned


def test_sanitize_mermaid_already_quoted_stays_valid():
    raw_mermaid = """graph TD
    A["Already Quoted\\nLine"] -->|"Label"| B["Second Quoted"]
"""
    cleaned = sanitize_mermaid_block(raw_mermaid)
    assert 'A["Already Quoted<br/>Line"]' in cleaned
    assert '-->|"Label"|' in cleaned
    assert 'B["Second Quoted"]' in cleaned


def test_mermaid_math_labels_keep_latex_commands_and_braces():
    formula = r"$\frac{x_{i}}{\sqrt{n}} + \nabla L$"
    diagram = f'graph TD\nA["Estimate {formula}"] -->|"{formula}"| B["Result"]'
    cleaned = sanitize_mermaid_block(diagram)
    assert cleaned.count(formula) == 2
    assert "<br/>abla" not in cleaned


def test_sanitize_latex_math_isolation():
    raw_text = """Bắt đầu công thức:
$$P(r) = 4d \\sum r_l$$
Tiếp tục bài viết:
$$\\begin{aligned}
x = 1
\\end{aligned}$$
Kết thúc.
"""
    cleaned = sanitize_latex_math(raw_text)
    assert "$$\nP(r) = 4d \\sum r_l\n$$" in cleaned
    assert "$$\n\\begin{aligned}" in cleaned
    assert "\\end{aligned}\n$$" in cleaned


def test_sanitize_algorithm_code_blocks():
    raw_text = """**Algorithm 1: SARA-LoRA Rank Allocation**
```text
Input: Pre-trained Model M
1: Do something
```
"""
    cleaned = sanitize_code_and_algorithm_blocks(raw_text)
    assert "```python\nInput: Pre-trained Model M" in cleaned


def test_sanitize_author_placeholders():
    raw_text = "**Authors:** [Author Names] | **Affiliations:** [Institutional Affiliation]"
    assert sanitize_author_placeholders(raw_text + "\n\n## Abstract") == "\n## Abstract"
    legacy = "# T\n\n**Authors:** PaperAI Automated Research Protocol | **Affiliations:** Open-Source Automated Science Initiative\n\n## Abstract"
    assert "PaperAI" not in sanitize_author_placeholders(legacy) and "Science Initiative" not in sanitize_author_placeholders(legacy)
    real = "**Authors:** Jane Doe | **Affiliations:** Hanoi University\n"
    assert sanitize_author_placeholders(real) == real


def test_sanitize_display_captions_drops_duplicate_figure_caption():
    text = (
        "Para.\n\n**Figure 4: Segmentation result [1].**\n\n"
        '```image\n{"ref": "F1", "caption": "Triple cascaded framework [1]."}\n```\n\n'
        "**Figure 5: Effect of fusion [1].**\n\n"
        '```chart\n{"type": "bar", "labels": ["ET"], "series": []}\n```\n\n'
        "**Figure 6: Pipeline**\n\n```mermaid\ngraph TD\nA-->B\n```\n"
    )
    out = sanitize_display_captions(text)
    assert "**Figure 4" not in out and '"caption": "Triple cascaded framework [1]."' in out
    assert "**Figure 5" not in out and '"caption": "Effect of fusion [1]."' in out
    assert "**Figure 6: Pipeline**" in out  # mermaid không có caption riêng: giữ


def test_sanitize_academic_markdown_full():
    full_text = """# Paper Title
**Authors:** [Author Names]

$$x = y + z$$

**Algorithm 1: Test**
```text
x = 1
```

```mermaid
graph TD
    A[Test\\nNode] --> B{Decide {x}}
```
"""
    cleaned = sanitize_academic_markdown(full_text)
    assert "PaperAI Automated Research Protocol" not in cleaned and "[Author Names]" not in cleaned
    assert "$$\nx = y + z\n$$" in cleaned
    assert "```python\nx = 1" in cleaned
    assert 'A["Test<br/>Node"]' in cleaned
    assert 'B{"Decide (x)"}' in cleaned


def test_sanitize_restores_missing_title_heading():
    from app.agent.format_sanitizer import sanitize_academic_markdown

    md = "Foundation Models: A Survey  \n\n**Authors:** PaperAI | **Affiliations:** X\n\n## Abstract\nText."
    assert sanitize_academic_markdown(md).startswith("# Foundation Models: A Survey\n")


def test_sanitize_keeps_existing_title_heading():
    from app.agent.format_sanitizer import sanitize_academic_markdown

    md = "# Title\n\n**Authors:** PaperAI\n\n## Abstract\nText."
    assert sanitize_academic_markdown(md).startswith("# Title\n")


def test_raw_snippet_references_become_ieee_lines():
    from app.agent.format_sanitizer import sanitize_raw_references

    text = (
        "Body\n\n## References\n\n"
        '[1] Foo bar, Page: 1, Section: Abstract — "Title: Deep Nets Authors: Ann Lee, Bo Chan et al. (2024) DOI: 10.1/x"\n'
        '[2] Baz, Page: 1, Section: Abstract — "Title: Baz Authors: Cy Do, Ed Fu... "\n'
        '[3] Already, "Formatted," *Venue*, 2020.\n'
    )
    out = sanitize_raw_references(text)
    assert '[1] Ann Lee' in out and '"Deep Nets,"' in out and "2024, DOI: 10.1/x." in out
    assert "Page:" not in out and "..." not in out
    assert '[2] Cy Do et al., "Baz," *arXiv preprint*, n.d.' in out
    assert '[3] Already, "Formatted," *Venue*, 2020.' in out


def test_duplicate_references_are_merged_and_citations_remapped():
    from app.agent.format_sanitizer import dedupe_references

    text = (
        'Intro [1] and [4]; also [2, 4] and [3]–[4].\n\n```table\n{"rows": [["x [4]", 4]], "v": [4, 1]}\n```\n\n'
        '## References\n\n[1] A, "Same Paper," *V*, 2020.\n[2] B, "Other," *V*, 2021.\n'
        '[3] C, "Third," *V*, 2022.\n[4] A, "Same paper," *V*, 2020.\n'
    )
    out = dedupe_references(text)
    assert "[4] A" not in out and out.count("Same") == 1
    assert "Intro [1] and [1]; also [1, 2] and [3]–[1]." in out
    assert '"x [1]"' in out and '"v": [4, 1]' in out  # số thường trong JSON không bị đụng
    assert dedupe_references("no refs") == "no refs"


def test_sanitize_display_captions_keeps_pipe_table_and_following_sections():
    # hồi quy task c7567a51: caption của bảng pipe không được nuốt sang khối fence ở mục sau
    text = (
        "### 4.5 Critical Comparative Analysis\n\n"
        "**Table 4: Critical comparison of strategies**\n\n"
        "| Strategy | Weakness |\n|---|---|\n| Early fusion | NR |\n\n"
        "## 5. Comparative Evidence Synthesis\n\n### 5.1 Datasets\n\nBraTS 2019 [1].\n\n"
        "### 5.3 Qualitative Visual Comparison\n\n"
        "**Figure 3: Segmentation overlay**\n"
        '```image\n{"ref": "F1", "caption": "Overlay from [1]"}\n```\n'
    )
    out = sanitize_display_captions(text)
    assert "**Table 4: Critical comparison of strategies**" in out
    assert "## 5. Comparative Evidence Synthesis" in out
    assert "### 5.3 Qualitative Visual Comparison" in out
    assert "**Figure 3: Segmentation overlay**" not in out  # caption trùng ngay trên khối vẫn bị bỏ
