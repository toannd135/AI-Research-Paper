"""Prompt riêng deepfake: áp đúng chặng, không đổi prompt gốc, luồng chính không dùng tới."""

import json
from importlib import import_module, util
from pathlib import Path

import pytest

from app.agent.evidence import extractor
from app.agent.nodes import analyze_node as _analyze  # noqa: F401 - đảm bảo module đã nạp
from app.agent.overlays.deepfake import OVERLAYS, OverlayGateway, classify_stage, with_overlay
from app.ai.llm_gateway.base import LLMGateway, LLMResponse, Message

plan = import_module("app.agent.nodes.plan_node")
analyze = import_module("app.agent.nodes.analyze_node")
synth = import_module("app.agent.nodes.synthesize_node")


_spec = util.spec_from_file_location("run_deepfake", Path(__file__).resolve().parents[3] / "scripts" / "run_deepfake.py")
run_deepfake = util.module_from_spec(_spec)
_spec.loader.exec_module(run_deepfake)


class _Capture(LLMGateway):
    def __init__(self):
        self.calls = []

    def generate(self, messages, model_name):
        self.calls.append((messages, model_name))
        return LLMResponse(text="ok", model=model_name or "fake")


@pytest.mark.parametrize(
    ("prompt", "stage"),
    [
        (plan._SYSTEM_PROMPT, "plan"),
        (analyze._SURVEY_ANALYZE_PROMPT, "analyze"),
        (analyze._NOVEL_ANALYZE_PROMPT, "analyze"),
        (extractor._PROMPT, "extract"),
        ("You repair Mermaid diagram syntax.", None),
    ],
)
def test_real_prompts_are_classified(prompt, stage):
    assert classify_stage(prompt) == stage


def test_synthesis_prompts_are_classified():
    state = {"question": "q", "draft": "", "citations": []}
    llm = _Capture()
    synth._generate_stage_0_blueprint(state, "", "survey", llm, "m")
    synth._generate_stage_1_front_matter_and_intro("b", state, "", "survey", llm, "m")
    assert [classify_stage(call[0][0].content) for call in llm.calls] == ["blueprint", "section"]


def test_overlay_appends_without_mutating_original():
    original = [Message("system", plan._SYSTEM_PROMPT), Message("user", "q")]
    final, stage = with_overlay(original)
    assert stage == "plan"
    assert final[0].content.startswith(plan._SYSTEM_PROMPT) and OVERLAYS["plan"] in final[0].content
    assert original[0].content == plan._SYSTEM_PROMPT
    assert final[1] is original[1]


def test_unknown_call_is_unchanged():
    messages = [Message("system", "You repair Mermaid diagram syntax."), Message("user", "x")]
    assert with_overlay(messages) == (messages, None)


def test_gateway_uses_real_model_and_logs(tmp_path):
    inner = _Capture()
    log = tmp_path / "prompts.jsonl"
    OverlayGateway(inner, "real-model", log).generate([Message("system", plan._SYSTEM_PROMPT)], "default")
    assert inner.calls[0][1] == "real-model"
    entry = json.loads(log.read_text(encoding="utf-8"))
    assert entry["stage"] == "plan" and OVERLAYS["plan"] in entry["system"]


def test_main_flow_never_imports_overlay():
    app_dir = Path(__file__).resolve().parents[2]
    users = [p for p in app_dir.rglob("*.py") if "overlays.deepfake" in p.read_text(encoding="utf-8") and "tests" not in p.parts]
    assert users == []


def test_manifest_fills_metadata_by_file_content(tmp_path):
    (tmp_path / "Real_Name.pdf").write_bytes(b"same")
    uid = "00000000-0000-4000-8000-000000000001"
    (tmp_path / f"{uid}.pdf").write_bytes(b"same")
    (tmp_path / "_manifest.json").write_text(json.dumps([{"file": "Real_Name.pdf", "title": "Real Title", "year": 2021, "doi": "https://doi.org/10.1/x"}]))
    papers = run_deepfake.paper_ids(tmp_path)
    assert list(papers) == [uid]
    catalog = {uid: {"title": uid, "authors": "", "year": "", "venue": "", "doi": ""}}
    run_deepfake.apply_manifest(catalog, papers, tmp_path)
    assert catalog[uid] == {"title": "Real Title", "authors": "", "year": "2021", "venue": "", "doi": "10.1/x"}


def test_manifest_arxiv_id_is_not_stored_as_doi(tmp_path):
    (tmp_path / "Real_Name.pdf").write_bytes(b"same")
    uid = "00000000-0000-4000-8000-000000000002"
    (tmp_path / f"{uid}.pdf").write_bytes(b"same")
    (tmp_path / "_manifest.json").write_text(json.dumps([{"file": "Real_Name.pdf", "title": "T", "year": 2026, "doi": "arXiv:2604.25889v1"}]))
    catalog = {uid: {"title": uid, "authors": "", "year": "", "venue": "", "doi": ""}}
    run_deepfake.apply_manifest(catalog, run_deepfake.paper_ids(tmp_path), tmp_path)
    assert catalog[uid]["doi"] == "" and catalog[uid]["venue"] == "arXiv:2604.25889v1"


def test_select_papers_mixes_most_cited_and_newest(tmp_path):
    rows = [("a", 2018, 900), ("b", 2019, 800), ("c", 2020, 10), ("d", 2025, 5), ("e", 2026, 1)]
    papers, manifest = {}, []
    for i, (name, year, cited) in enumerate(rows):
        uid = f"00000000-0000-4000-8000-00000000001{i}"
        (tmp_path / f"{name}.pdf").write_bytes(name.encode())
        (tmp_path / f"{uid}.pdf").write_bytes(name.encode())
        papers[name] = uid
        manifest.append({"file": f"{name}.pdf", "title": name, "year": year, "cited": cited})
    (tmp_path / "_manifest.json").write_text(json.dumps(manifest))
    found = run_deepfake.paper_ids(tmp_path)
    assert set(run_deepfake.select_papers(found, tmp_path, 4)) == {papers[n] for n in "abde"}
    assert run_deepfake.select_papers(found, tmp_path, 0) == found

