"""Kho deepfake không nhận chỉ dẫn MRI (BraTS/Dice/WT-TC-ET/missing-modality) trong prompt, và chỉ thấy paper của kho."""

import importlib
import re

import pytest

from app.agent import domains
from app.core.scope import filter_chunks

sn = importlib.import_module("app.agent.nodes.synthesize_node")  # package `nodes` che tên module bằng hàm cùng tên

_MRI_RE = re.compile(r"brats|glioma|tumou?r|\bdice\b|hd95|\bWT\b|\bTC\b|\bET\b|flair|t1ce|missing[- ]modality|\bMRI\b", re.I)


@pytest.fixture
def deepfake():
    domains.set_domain("deepfake")
    yield
    domains.set_domain("general")


@pytest.mark.parametrize("mode", ["survey", "novel_research"])
def test_deepfake_prompts_have_no_mri_terms(deepfake, mode):
    state = {"question": "How do CLIP-based detectors generalize across deepfake datasets?", "citations": [],
             "contribution_type": "comparison", "language": "en"}
    texts = [sn._global_standards(state, mode)]
    for stage in ("stage2", "stage3", "stage4", "stage5"):
        texts.extend(sn._stage_structure(state, mode, stage))
    leaks = sorted({m.group(0) for t in texts for m in _MRI_RE.finditer(t)})
    assert leaks == []


def test_workspace_scope_never_widens():
    class C:
        def __init__(self, pid):
            self.paper_id = pid

    chunks = [C("df1"), C("brain1")]
    assert [c.paper_id for c in filter_chunks(chunks, {"df1"})] == ["df1"]
    assert filter_chunks(chunks, set()) == []  # kho rỗng: không rơi về toàn bộ vector
