"""Paper đa lĩnh vực / đa đối tượng: profile, lọc miền, khối ảnh thật, chú thích mermaid."""

import importlib
import json

import pytest

from app.agent.nodes.plan_node import plan_node
from app.agent.nodes.search_node import is_domain_relevant
from app.agent.profiles import (
    AUDIENCE_PROFILES,
    FIELD_PROFILES,
    adaptation_rules,
    detect_field,
    normalize_audience,
    normalize_field,
)
from app.agent.report_postprocess import postprocess_report, scrub_image_spec
from app.ai.llm_gateway.base import LLMResponse
from app.core.schemas import Chunk
from app.pipeline import figures as figures_mod
from app.pipeline.export import pdf_renderer, typst_renderer

# app.agent.nodes.__init__ export hàm synthesize_node trùng tên module → lấy module qua importlib
sn = importlib.import_module("app.agent.nodes.synthesize_node")


@pytest.mark.parametrize(
    "question,field",
    [
        ("Khử nhiễu ảnh y tế bằng diffusion model và siêu phân giải", "computer_vision"),
        ("Ô nhiễm PM2.5 tại Hà Nội giai đoạn 2015-2024", "environment"),
        ("Tác động của lạm phát tới GDP Việt Nam", "economics"),
        ("Đánh giá các phương pháp RAG cho hỏi đáp", "computing"),
    ],
)
def test_detect_field(question, field):
    assert detect_field(question) == field


def test_normalize_profiles():
    assert normalize_field("Computer-Vision") == "computer_vision"
    assert normalize_field("astrology") is None
    assert normalize_audience(None) == "lecturer"
    assert normalize_audience("STUDENT") == "student"
    for p in FIELD_PROFILES.values():
        assert {"label", "role", "keywords", "metrics", "figures", "stage4", "off_domain"} <= p.keys()
    for p in AUDIENCE_PROFILES.values():
        assert {"label", "style", "front", "end"} <= p.keys()


def test_adaptation_rules_mention_field_and_audience():
    rules = adaptation_rules({"field": "environment", "audience": "professional"})
    assert "Environmental Science" in rules
    assert "decision makers" in rules


def test_off_domain_filter_depends_on_field():
    chunk = Chunk(paper_id="openalex_W1", text="Deep learning for wildfire detection from satellite imagery")
    assert not is_domain_relevant(chunk, "RAG for question answering", "computing")
    assert not is_domain_relevant(chunk, "RAG for question answering")  # mặc định giữ hành vi cũ cho CS
    assert is_domain_relevant(chunk, "Ô nhiễm không khí do cháy rừng", "environment")


class _Gateway:
    def __init__(self, text):
        self.text = text

    def generate(self, messages, model_name=None):
        return LLMResponse(text=self.text, model="fake")


def test_plan_node_sets_field_from_llm_and_keeps_explicit_field():
    llm = _Gateway('{"mode": "survey", "field": "medicine", "queries": ["q1"]}')
    assert plan_node({"question": "Chẩn đoán ung thư"}, llm=llm)["field"] == "medicine"
    assert plan_node({"question": "x", "field": "education"}, llm=llm)["field"] == "education"
    bad = _Gateway('{"mode": "survey", "field": "???", "queries": ["q1"]}')
    assert plan_node({"question": "Ô nhiễm PM2.5 và khí hậu"}, llm=bad)["field"] == "environment"


def test_stage_structure_adds_field_and_audience_sections():
    state = {"field": "computer_vision", "audience": "student"}
    _, stage4 = sn._stage_structure(state, "survey", "stage4")
    _, stage5 = sn._stage_structure(state, "survey", "stage5")
    assert "Qualitative Visual Comparison" in stage4
    assert "## Glossary" in stage5 and "## Key Takeaways" in stage5
    _, plain5 = sn._stage_structure({"audience": "lecturer"}, "survey", "stage5")
    assert "Glossary" not in plain5


def _fake_figure(tmp_path, fid="F1"):
    img = tmp_path / "figures" / "p1" / "fig_1.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    return {
        "id": fid, "cite": 2, "paper_id": "p1", "page": 4, "caption": "Figure 3: Denoised CT slices",
        "path": str(img), "source_title": "denoise.pdf",
    }


def test_global_standards_lists_available_figures(tmp_path):
    rules = sn._global_standards({"figures": [_fake_figure(tmp_path)]}, "survey")
    assert "[F1] from [2], page 4: Figure 3: Denoised CT slices" in rules
    assert "```image" in rules
    assert "```image" not in sn._global_standards({}, "survey")


def test_collect_figures_follows_citation_order(monkeypatch):
    store = {"pB": [{"page": 1, "caption": "Fig. 1: b", "path": "/b.png"}], "pA": [{"page": 2, "caption": "Fig. 2: a", "path": "/a.png"}]}
    monkeypatch.setattr(sn, "load_figures", lambda pid: store.get(pid, []))
    citations = [{"paper_id": "pA"}, {"paper_id": "openalex_W9"}, {"paper_id": "pB"}, {"paper_id": "pA"}]
    figs = sn._collect_figures(citations)
    assert [(f["id"], f["cite"], f["caption"]) for f in figs] == [("F1", 1, "Fig. 2: a"), ("F2", 3, "Fig. 1: b")]


def test_scrub_image_spec_only_accepts_known_refs(tmp_path):
    fig = _fake_figure(tmp_path)
    ok = json.loads(scrub_image_spec('{"ref": "F1", "caption": "CT slices [2]", "path": "/etc/passwd"}', [fig]))
    assert ok["path"] == fig["path"]  # đường dẫn lấy từ metadata, không từ LLM
    assert ok["source"] == "denoise.pdf, p. 4"
    assert scrub_image_spec('{"ref": "F9"}', [fig]) is None
    assert scrub_image_spec("not json", [fig]) is None


def test_postprocess_drops_unknown_and_duplicate_images(tmp_path):
    fig = _fake_figure(tmp_path)
    report = (
        '```image\n{"ref": "F1", "caption": "a"}\n```\n\n'
        '```image\n{"ref": "F1", "caption": "again"}\n```\n\n'
        '```image\n{"ref": "F7", "caption": "ghost"}\n```\n'
    )
    out = postprocess_report(report, "", None, None, "en", [fig])
    assert out.count("```image") == 1 and '"caption": "a"' in out


def _real_png(tmp_path):
    import pymupdf

    root = tmp_path / "figures"
    img = root / "p1" / "fig_1.png"
    img.parent.mkdir(parents=True)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20), False)
    pix.clear_with(200)
    pix.save(img)
    return root, img


def test_typst_renders_image_block_with_source(tmp_path, monkeypatch):
    root, img = _real_png(tmp_path)
    monkeypatch.setattr(figures_mod, "figures_root", lambda: root)
    spec = {"ref": "F1", "caption": "Denoised CT slices [2]", "path": str(img), "source": "denoise.pdf, p. 4"}
    outside = {"ref": "F2", "caption": "x", "path": str(tmp_path / "evil.png")}
    md = (
        "# T\n\n## Abstract\nA.\n\n## 1. Intro\n\n"
        f"```image\n{json.dumps(spec)}\n```\n\n```image\n{json.dumps(outside)}\n```\n"
    )
    work = tmp_path / "work"
    work.mkdir()
    typ = typst_renderer.markdown_to_typst(md, work_dir=work)
    assert 'image("img_1.png"' in typ and "Source: denoise.pdf, p. 4" in typ
    assert "img_2.png" not in typ and (work / "img_1.png").is_file()


def test_typst_mermaid_caption_comes_from_figure_line(tmp_path, monkeypatch):
    monkeypatch.setattr(typst_renderer, "render_mermaid_to_svg", lambda code, path: path.write_text("<svg/>"))
    md = (
        "# T\n\n## Abstract\nA.\n\n## 2. Method\n\n**Figure 1: Air-quality monitoring workflow**\n\n"
        '```mermaid\ngraph LR\nA["Sensor"] --> B["Model"]\n```\n'
    )
    typ = typst_renderer.markdown_to_typst(md, work_dir=tmp_path)
    assert "Air-quality monitoring workflow" in typ
    assert "System Architectural and Evaluation Pipeline Overview" not in typ


def test_html_image_block_embeds_png_and_rejects_outside(tmp_path, monkeypatch):
    root, img = _real_png(tmp_path)
    monkeypatch.setattr(figures_mod, "figures_root", lambda: root)
    html_ok = pdf_renderer._render_image_html(json.dumps({"path": str(img), "caption": "c", "source": "s.pdf, p. 1"}))
    assert "data:image/png;base64," in html_ok and "Source: s.pdf, p. 1" in html_ok
    assert pdf_renderer._render_image_html(json.dumps({"path": "/etc/passwd"})) == ""


def test_typst_keeps_executive_summary_before_section_one(tmp_path):
    md = (
        "# T\n\n## Abstract\nA.\n\n**Keywords:** k1\n\n"
        "## Executive Summary\n- Key point for practitioners.\n\n## 1. Introduction\nText.\n"
    )
    typ = typst_renderer.markdown_to_typst(md, work_dir=tmp_path)
    assert "Executive Summary" in typ and "Key point for practitioners" in typ


class _StageGateway:
    """LLM giả: mọi chặng trả thân bài có Conclusion; lời gọi bổ sung trả các mục theo đối tượng."""

    def __init__(self, include_end_sections: bool = False):
        self.include_end_sections = include_end_sections
        self.appendix_calls = 0

    def generate(self, messages, model_name=None):
        system = messages[0].content
        if "SECTIONS TO WRITE" in system:
            self.appendix_calls += 1
            return LLMResponse(
                text="## Key Takeaways\n- Inflation effects vary by regime [1].\n\n## Glossary\n\n| Term | Definition |\n|---|---|\n| Inflation | General price rise |",
                model="fake",
            )
        text = "## 6. Conclusion\nBody text of the section.\n"
        if self.include_end_sections:
            text += "\n## Key Takeaways\n- Already written.\n\n## Glossary\n\n| Term | Definition |\n|---|---|\n| GDP | Output |\n"
        return LLMResponse(text=text, model="fake")


def _student_state():
    return {"question": "Lạm phát và GDP", "audience": "student", "field": "economics", "draft": "d", "citations": [], "language": "en"}


def test_synthesize_adds_missing_student_sections_with_one_extra_call():
    gw = _StageGateway(include_end_sections=False)
    report = sn.synthesize_node(_student_state(), llm=gw)["report"]
    assert gw.appendix_calls == 1
    assert "## Key Takeaways" in report and "## Glossary" in report
    assert report.index("## Glossary") < report.index("## References")


def test_synthesize_skips_extra_call_when_sections_present():
    gw = _StageGateway(include_end_sections=True)
    report = sn.synthesize_node(_student_state(), llm=gw)["report"]
    assert gw.appendix_calls == 0
    assert report.count("## Glossary") >= 1


def test_scrub_table_drops_header_groups_that_do_not_match_columns():
    from app.agent.report_postprocess import scrub_table_spec

    spec = {
        "columns": ["Method", "Acc", "F1"],
        "header_groups": [{"label": "A", "span": 2}, {"label": "B", "span": 2}],
        "rows": [["x", "90.1", "88.0"]],
    }
    out = json.loads(scrub_table_spec(json.dumps(spec), "90.1 88.0"))
    assert "header_groups" not in out and out["rows"] == [["x", "90.1", "88.0"]]


def test_typst_ignores_mismatched_header_groups_instead_of_failing(tmp_path):
    spec = {
        "caption": "T", "columns": ["M", "A", "B"],
        "header_groups": [{"label": "G", "span": 5}],
        "rows": [["x", "1", "2"]],
    }
    md = "# T\n\n## Abstract\nA.\n\n## 1. Introduction\n\n```table\n" + json.dumps(spec) + "\n```\n"
    assert "table.cell(colspan: 5)" not in typst_renderer.markdown_to_typst(md, work_dir=tmp_path)
