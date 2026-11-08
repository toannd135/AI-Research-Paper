from types import SimpleNamespace

import pytest

from app.agent.evidence import coverage
from app.agent.evidence.quality_gate import run_quality_gate
from app.agent.tools import ensure_coverage
from app.core.schemas import Chunk, Citation, ScoredChunk


def _sc(pid, cid):
    return ScoredChunk(chunk=Chunk(id=cid, paper_id=pid, text="t", chunk_index=0, page=1), score=0.5)


@pytest.fixture
def limit(monkeypatch):
    monkeypatch.setattr(coverage, "get_settings", lambda: SimpleNamespace(full_corpus_coverage_limit=80))


def test_target_is_all_for_small_corpus_and_capped_for_large(limit, monkeypatch):
    assert coverage.coverage_target(55) == 55
    assert coverage.coverage_target(200) == coverage.MIN_CITED_PAPERS
    monkeypatch.setattr(coverage, "get_settings", lambda: SimpleNamespace(full_corpus_coverage_limit=0))
    assert coverage.coverage_target(55) == coverage.MIN_CITED_PAPERS  # 0 = tắt


def test_uncited_papers_counts_any_citation_number_of_the_paper(limit):
    cits = [Citation(paper_id="a", chunk_id="1"), Citation(paper_id="a", chunk_id="2"), Citation(paper_id="b", chunk_id="3"), Citation(paper_id="c", chunk_id="4")]
    assert coverage.uncited_papers(cits, "x [2] y [3]") == ["c"]


def test_ensure_coverage_adds_one_chunk_for_each_missing_paper(limit, monkeypatch):
    monkeypatch.setattr(ensure_coverage, "full_coverage_applies", lambda n: True)
    monkeypatch.setattr("app.agent.tools.ensure_coverage.list_paper_ids", lambda: {"a", "b", "c"})
    monkeypatch.setattr(ensure_coverage, "get_allowed_paper_ids", lambda: None)
    monkeypatch.setattr(ensure_coverage, "search_hybrid", lambda q, top_k, paper_id: [_sc(paper_id, f"x-{paper_id}")])
    out = ensure_coverage.ensure_corpus_coverage([_sc("a", "a1")], "q")
    assert sorted({s.chunk.paper_id for s in out}) == ["a", "b", "c"] and len(out) == 3


def test_ensure_coverage_respects_owner_scope_and_limit(limit, monkeypatch):
    monkeypatch.setattr("app.agent.tools.ensure_coverage.list_paper_ids", lambda: {"a", "b", "c"})
    monkeypatch.setattr(ensure_coverage, "get_allowed_paper_ids", lambda: {"a", "b"})
    monkeypatch.setattr(ensure_coverage, "search_hybrid", lambda q, top_k, paper_id: [_sc(paper_id, f"x-{paper_id}")])
    out = ensure_coverage.ensure_corpus_coverage([], "q")
    assert sorted(s.chunk.paper_id for s in out) == ["a", "b"]  # không lộ paper của người khác
    monkeypatch.setattr(ensure_coverage, "full_coverage_applies", lambda n: False)
    assert ensure_coverage.ensure_corpus_coverage([], "q") == []  # kho quá lớn: giữ hành vi cũ


def test_gate_warns_about_papers_in_corpus_but_not_cited(limit):
    cits = [Citation(paper_id="a", chunk_id="1"), Citation(paper_id="b", chunk_id="2"), Citation(paper_id="c", chunk_id="3")]
    cat = {"c": {"title": "Paper C title"}}
    rep = run_quality_gate({"citations": cits, "evidence": []}, "Intro [1] and [2].", catalog=cat)
    assert any("độ phủ kho: 1/3" in w and "Paper C title" in w for w in rep["warnings"])
    full = run_quality_gate({"citations": cits, "evidence": []}, "[1] [2] [3]", catalog=cat)
    assert not any("độ phủ kho" in w for w in full["warnings"])
