"""Reference của paper upload (không có trong catalog.json), catalog theo kho, và bảng quá nhiều cột khi xuất LaTeX."""

import pymupdf

from app.agent.evidence import citation_cleaner
from app.agent.evidence.pdf_metadata import pdf_citation_metadata
from app.core.scope import set_allowed_paper_ids
from app.pipeline.export.latex_renderer import _fit_columns, _section_ref_tokens, _table_env

UPLOADED = "7ed144d5-ec09-44ee-8f87-cafbab80bba0"


def _make_pdf(path, title="Deepfake Detection With CLIP Adapters", authors="Alice Nguyen, Bob Tran and Carol Le"):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 90), title, fontsize=20)
    page.insert_text((72, 125), authors, fontsize=11)
    page.insert_text((72, 160), "Abstract. We study generalization. arXiv:2403.14974v1", fontsize=9)
    doc.save(path)


def test_pdf_metadata_reads_title_authors_year(tmp_path):
    pdf = tmp_path / "a.pdf"
    _make_pdf(pdf)
    meta = pdf_citation_metadata(str(pdf), "x.pdf")
    assert meta["title"] == "Deepfake Detection With CLIP Adapters"
    assert meta["authors"] == "Alice Nguyen, Bob Tran, Carol Le"
    assert meta["year"] == "2024" and meta["venue"] == "arXiv:2403.14974"


def test_pdf_metadata_falls_back_to_filename(tmp_path):
    meta = pdf_citation_metadata(str(tmp_path / "missing.pdf"), "Audio_Deepfake_Detection_A_Survey.pdf")
    assert meta["title"] == "Audio Deepfake Detection A Survey"
    assert pdf_citation_metadata("", f"{UPLOADED}.pdf")["title"] == ""  # tên UUID không phải tiêu đề


def test_uploaded_paper_reference_uses_pdf_metadata_not_uuid(monkeypatch):
    monkeypatch.setattr(citation_cleaner, "_local_catalog", lambda: {"brain1": {"title": "BraTS"}})
    monkeypatch.setitem(
        citation_cleaner._DB_META, UPLOADED,
        {"title": "Real Title", "authors": "A One, B Two, C Three", "year": "2024", "venue": "", "doi": ""},
    )
    meta = citation_cleaner._extract_citation_metadata(UPLOADED)
    assert meta["title"] == "Real Title" and meta["authors"] == "A One et al."
    assert meta["venue"] and meta["venue"] != "arXiv preprint"

    set_allowed_paper_ids({UPLOADED})
    try:
        assert set(citation_cleaner.corpus_catalog()) == {UPLOADED}  # không lẫn catalog của kho khác
    finally:
        set_allowed_paper_ids(None)
    assert set(citation_cleaner.corpus_catalog()) == {"brain1"}


def test_wide_table_drops_empty_columns_and_splits():
    cols = ["Paradigm", "Method [ref]", "Backbone"] + [f"M{i}" for i in range(14)]
    rows = [
        ["Visual", "DFDT [1]", "ViT"] + ["99.4", "NR"] + ["NR"] * 4 + ["81.3"] + ["NR"] * 3 + ["0.9", "NR", "NR", "NR"],
        ["", "CLIP [2]", "CLIP"] + ["NR", "97.8"] + ["NR"] * 4 + ["NR"] * 4 + ["NR", "NR", "5.2", "NR"],
        ["Audio", "W2V [3]", "wav2vec"] + ["NR"] * 6 + ["NR"] * 4 + ["NR", "NR", "NR", "88.0"],
    ]
    parts = _fit_columns(cols, rows)
    kept = [c for p in parts for c in p[0][3:]]
    assert kept == ["M0", "M1", "M6", "M10", "M12", "M13"]  # cột toàn NR bị bỏ
    assert all(len(p[0]) <= 9 for p in parts)

    many = ["Method"] + [f"V{i}" for i in range(16)]
    full = [[f"m{r}"] + [str(r + i) for i in range(16)] for r in range(3)]
    parts = _fit_columns(many, full)
    assert len(parts) == 2 and all(p[0][0] == "Method" and len(p[0]) <= 9 for p in parts)
    tex = _table_env(many, full, "Wide results")
    assert tex.count(r"\begin{table") == 2 and "(continued)" in tex


def test_split_keeps_group_label_when_leader_row_filtered():
    cols = ["Paradigm", "Method"] + [f"V{i}" for i in range(12)]
    rows = [
        ["Visual", "A"] + ["1"] * 6 + ["NR"] * 6,
        ["", "B"] + ["NR"] * 6 + ["2"] * 6,
    ]
    second = _fit_columns(cols, rows)[1]
    assert second[1] == [["Visual", "B"] + ["2"] * 5]  # 2 cột định danh + 7 cột/khối → khối 2 có V7..V11


def test_section_range_converts_both_ends():
    out = _section_ref_tokens("see Section 4.2–4.4 and Section 9", {"4.2", "4.4"})
    assert out == "see SectionPAISECREF4.2END–PAIREF4.4END and Section 9"


def test_manifest_overrides_title_year_doi(monkeypatch):
    monkeypatch.setattr(
        citation_cleaner, "_manifest_index",
        lambda: {"Real.pdf": {"file": "Real.pdf", "title": "Canonical Title", "year": 2021, "doi": "https://doi.org/10.1/x"}},
    )
    meta = citation_cleaner._apply_manifest({"title": "guess", "authors": "A B", "year": "2019", "venue": "", "doi": ""}, "Real.pdf")
    assert (meta["title"], meta["year"], meta["doi"], meta["authors"]) == ("Canonical Title", "2021", "10.1/x", "A B")


def test_renumber_sections_maps_both_ends_of_a_range():
    from app.agent.evidence.report_structure import renumber_sections

    md = "## 1. Intro\n\nSee Section 4.2–4.4 and Sections 4.2 and 4.3.\n\n## 4. Results\n\n### 4.2 A\n\n### 4.3 B\n\n### 4.4 C\n"
    out = renumber_sections(md)
    assert "Section 2.1–2.3" in out and "Sections 2.1 and 2.2" in out
