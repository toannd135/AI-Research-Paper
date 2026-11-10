"""Research trên PDF tải lên: reference không bịa metadata, số bài và giới hạn chunk đúng phạm vi."""

from importlib import import_module
from types import SimpleNamespace

import pytest

from app.agent.evidence import citation_cleaner as cc
from app.agent.evidence.coverage import local_chunks_per_paper
from app.core.scope import set_local_only, set_run_catalog

sn = import_module("app.agent.nodes.synthesize_node")
CATALOG = {"p1": {"title": "Uploaded Paper Title", "authors": "", "year": "", "venue": "", "doi": ""}}


@pytest.fixture(autouse=True)
def _reset_scope():
    yield
    set_run_catalog(None)
    set_local_only(False)


def _cite(pid):
    return SimpleNamespace(paper_id=pid, page=1, section="Intro", text_snippet="Some evidence.")


def test_run_catalog_overrides_file_catalog():
    set_run_catalog(CATALOG)
    assert cc._local_catalog() == CATALOG


def test_reference_marks_missing_metadata_instead_of_guessing():
    set_run_catalog(CATALOG)
    _, refs, _ = cc.clean_and_deduplicate_citations_ex([_cite("p1")], "Claim [1].")
    assert refs == ['[1] Unknown authors, "Uploaded Paper Title," n.d.']
    assert "2024" not in refs[0] and "arXiv" not in refs[0] and "p1" not in refs[0]


@pytest.mark.parametrize(("papers", "cap"), [(0, 2), (1, 12), (4, 10), (10, 4), (30, 2), (100, 2)])
def test_chunk_cap_scales_with_corpus(papers, cap):
    assert local_chunks_per_paper(papers) == cap


def test_review_facts_use_run_scope_when_local_only():
    set_run_catalog(CATALOG)
    set_local_only(True)
    facts = sn._review_facts({"citations": [_cite("p1")], "search_queries": ["q"]}, "survey")
    assert "Corpus size: 1 papers" in facts
    assert "internal PDF repository only" in facts
    assert "at most 12 chunks per paper" in facts


def test_review_facts_do_not_claim_local_process_with_openalex(monkeypatch):
    monkeypatch.setattr(sn, "external_search_allowed", lambda: True)
    set_run_catalog(CATALOG)
    facts = sn._review_facts({"citations": [_cite("p1")], "search_queries": ["q"]}, "survey")
    assert "OpenAlex" in facts
    assert "Corpus size" not in facts
    assert "chunks per paper" not in facts
    assert "the repository or the external index" in facts
