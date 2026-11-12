"""Chạy trọn synthesize_node (viết 6 chặng + quality gate + hậu xử lý) cho 3 chế độ với LLM giả viết đúng heading được yêu cầu.

Bảo đảm: không lỗi, khung bài đúng chế độ, không lọt thuật ngữ của chế độ khác, không in 'None' vào bảng/biểu đồ.
"""

import re
from types import SimpleNamespace

import pytest

from app.agent import domains
from app.agent.evidence.extractor import records_to_dicts
from app.agent.evidence.quant_check import ResultRecord
from app.agent.nodes.synthesize_node import synthesize_node
from app.ai.llm_gateway.base import LLMGateway, LLMResponse
from app.core.schemas import Citation


class _HeadingGateway(LLMGateway):
    def generate(self, messages, model_name=None):
        m = re.search(r"REQUIRED STRUCTURE:\n(.*)$", messages[0].content, re.S)
        if not m:
            return LLMResponse(text="# A Survey\n\n## Abstract\nWe review the evidence [1].\n\n**Keywords:** a, b\n\n## 1. Introduction\nText [1].", model="f")
        lines = [f"{h}\n\nThe cited study reports relevant evidence [1] and a complementary view [2].\n"
                 for h in m.group(1).splitlines() if re.match(r"^#{2,3} ", h)]
        return LLMResponse(text="\n".join(lines) or "Text [1].", model="f")


def _records(domain):
    def rec(**k):
        return ResultRecord(**{"dataset_version": None, "region": None, "unit": "percent", "source_page": 2, **k})

    out = []
    for i, (m, p) in enumerate([("A", "p1"), ("B", "p2"), ("C", "p3")]):
        if domain == domains.MRI_BRAIN:
            out += [rec(paper_id=p, model=m, dataset="BraTS", dataset_version="2021", split="validation", region=r, metric="Dice", value=v - i)
                    for r, v in (("WT", 90), ("TC", 85), ("ET", 80))]
        elif domain == domains.DEEPFAKE:
            out += [rec(paper_id=p, model=m, dataset="FF++", split="in-domain", metric="AUC", value=99 - i),
                    rec(paper_id=p, model=m, dataset="Celeb-DF", split="cross-dataset", metric="AUC", value=70 + i)]
        else:
            out.append(rec(paper_id=p, model=m, dataset="GLUE", split="test", metric="Accuracy", value=88 - i))
    return records_to_dicts(out)


_EXPECTED = {
    domains.GENERAL: [],
    domains.MRI_BRAIN: ["Missing-Modality Robustness", "Clinical/Deployment Concerns"],
    domains.DEEPFAKE: ["Cross-Dataset & Cross-Generator Generalization", "Robustness to Compression & Perturbation"],
}
_FORBIDDEN = {
    domains.GENERAL: ["tumor", "brats", "deepfake", "cross-generator", "missing-modality", "clinical"],
    domains.MRI_BRAIN: ["deepfake", "cross-generator", "celeb-df"],
    domains.DEEPFAKE: ["tumor", "dice", "brats", "modality", "clinical"],
}


@pytest.mark.parametrize("mode", ["survey", "novel_research"])
@pytest.mark.parametrize("domain", domains.DOMAINS)
def test_full_synthesis_per_domain(domain, mode):
    domains.set_domain(domain)
    ev = [SimpleNamespace(chunk=SimpleNamespace(paper_id=f"p{i}", page=2, text="We train on FF++ and test on Celeb-DF. Code is at github.com/x."))
          for i in (1, 2, 3)]
    state = {
        "question": "q", "draft": "draft [1]", "research_mode": mode, "audience": "lecturer",
        "citations": [Citation(chunk_id=f"c{i}", paper_id=f"p{i}", page=2, text_snippet="evidence text") for i in (1, 2, 3)],
        "field": domains.domain_field() or "computing", "results": _records(domain), "evidence": ev, "figures": [],
    }
    report = synthesize_node(state, llm=_HeadingGateway())["report"]
    low = report.lower()
    assert "## References" in report
    assert "None" not in report
    assert not [w for w in _FORBIDDEN[domain] if re.search(rf"\b{w}\b", low)]
    if mode == "survey":
        heads = re.findall(r"^###\s+(\d+)\.(\d+)\s+(.*)$", report, re.M)
        for want in _EXPECTED[domain]:
            assert any(want in h[2] for h in heads), want
        subs = [int(s) for top, s, _ in heads if top == "5"]
        assert subs == list(range(1, len(subs) + 1))  # mục 5.x đánh số liên tục, không trùng
    if domain == domains.DEEPFAKE:  # bài deepfake phải có kết quả thực nghiệm (bảng in-domain vs cross-dataset, số nguyên văn)
        assert "Celeb-DF (cross-dataset" in report and "FF++ (in-domain" in report
        assert re.search(r"\b99\b", report) and re.search(r"\b70\b", report)
