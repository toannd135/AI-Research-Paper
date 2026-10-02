import pytest
from app.agent.format_sanitizer import (
    sanitize_academic_markdown,
    sanitize_author_placeholders,
    sanitize_code_and_algorithm_blocks,
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
    cleaned = sanitize_author_placeholders(raw_text)
    assert "**Authors:** PaperAI Automated Research Protocol" in cleaned
    assert "**Affiliations:** Open-Source Automated Science Initiative" in cleaned


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
    assert "PaperAI Automated Research Protocol" in cleaned
    assert "$$\nx = y + z\n$$" in cleaned
    assert "```python\nx = 1" in cleaned
    assert 'A["Test<br/>Node"]' in cleaned
    assert 'B{"Decide (x)"}' in cleaned
