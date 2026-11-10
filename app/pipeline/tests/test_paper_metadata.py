"""Metadata đọc từ PDF tải lên: chỉ lấy điều có trong file, thiếu thì để trống."""

import pymupdf

from app.pipeline.paper_metadata import extract_paper_metadata


def _pdf(path, big="A Study of Hybrid Retrieval Models", body="", meta=None):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 80), big, fontsize=22)
    page.insert_text((50, 500), body or "Plain body text.", fontsize=10)
    if meta:
        doc.set_metadata(meta)
    doc.save(path)
    doc.close()
    return str(path)


def test_title_from_layout_and_nothing_guessed(tmp_path):
    meta = extract_paper_metadata(_pdf(tmp_path / "a.pdf"), "a.pdf")
    assert meta == {"title": "A Study of Hybrid Retrieval Models", "authors": "", "year": "", "venue": "", "doi": ""}


def test_embedded_metadata_doi_and_explicit_year(tmp_path):
    path = _pdf(tmp_path / "b.pdf", body="doi: 10.1000/xyz.123. Copyright 2021 ACM.", meta={"title": "Embedded Paper Title", "author": "Jane Doe, John Roe"})
    meta = extract_paper_metadata(path, "b.pdf")
    assert meta["title"] == "Embedded Paper Title"
    assert meta["authors"] == "Jane Doe, John Roe"
    assert meta["doi"] == "10.1000/xyz.123"
    assert meta["year"] == "2021"


def test_junk_embedded_values_are_ignored(tmp_path):
    path = _pdf(tmp_path / "c.pdf", meta={"title": "Microsoft Word - draft final v2.docx", "author": "admin"})
    meta = extract_paper_metadata(path, "c.pdf")
    assert meta["title"] == "A Study of Hybrid Retrieval Models"
    assert meta["authors"] == ""


def test_unreadable_file_falls_back_to_filename(tmp_path):
    path = tmp_path / "my_paper.pdf"
    path.write_bytes(b"not a pdf")
    assert extract_paper_metadata(str(path), "my_paper.pdf")["title"] == "my paper"
