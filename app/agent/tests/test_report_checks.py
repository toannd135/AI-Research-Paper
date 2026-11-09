"""Kiểm tra Abstract đủ thành phần, viết tắt, và xuất sổ cái CSV."""

import csv

from app.agent.evidence.consistency_check import check_acronyms, check_consistency
from app.agent.evidence.ledger_export import COLUMNS, export_ledger_csv


def test_abstract_missing_parts_are_flagged():
    text = "## Abstract\n\nDeepfakes are a concern for society.\n\n## 1. Introduction\n\nText."
    warns = " ".join(check_consistency(text))
    for part in ("phương pháp review", "số paper", "phát hiện định lượng", "đóng góp"):
        assert part in warns


def test_abstract_complete_has_no_content_warning():
    abstract = (
        "We review 50 papers from a curated corpus of foundation-model deepfake detectors and present a taxonomy. "
        "Reported cross-dataset AUC drops from 98.2 to 71.5 on unseen generators."
    )
    warns = " ".join(check_consistency(f"## Abstract\n\n{abstract}\n\n## 1. Introduction\n\nText."))
    assert "Abstract chưa nêu rõ" not in warns


def test_acronyms_undefined_and_missing_table():
    body = (
        "We use DFDC. DFDC again. DFDC data. Also CLIP (Contrastive Language-Image Pretraining (CLIP)) CLIP CLIP CLIP."
    )
    out = check_acronyms("## 1. Intro\n\n" + body)
    assert any("DFDC" in w for w in out)
    assert not any("viết tắt CLIP" in w for w in out)

    many = " ".join(f"AB{c} AB{c} AB{c}" for c in "DEFGHIJK")
    assert any("danh sách viết tắt" in w for w in check_acronyms("## 1. Intro\n\n" + many))
    assert not any("danh sách viết tắt" in w for w in check_acronyms("## Abbreviations\n\nx\n\n## 1. Intro\n\n" + many))


def test_export_ledger_csv_roundtrip(tmp_path):
    rows = [
        {
            "paper_id": "p1",
            "model": "M",
            "dataset": "FF++",
            "dataset_version": None,
            "split": "test",
            "region": None,
            "metric": "AUC",
            "value": 0.97,
            "unit": "ratio",
            "source_page": 5,
            "modality": ["visual", "audio"],
        },
        {
            "paper_id": "p2",
            "model": "N",
            "dataset": None,
            "dataset_version": None,
            "split": None,
            "region": None,
            "metric": "Dice",
            "value": 80.0,
            "unit": None,
        },
    ]
    path = tmp_path / "ledger" / "t.csv"
    assert export_ledger_csv(rows, path, {"p1": "a.pdf"}) == 2
    with path.open(encoding="utf-8-sig", newline="") as f:
        data = list(csv.DictReader(f))
    assert list(data[0].keys()) == COLUMNS
    assert data[0]["paper_file"] == "a.pdf" and data[0]["modality"] == "visual, audio" and data[0]["issues"] == ""
    assert "nguồn" in data[1]["issues"] and "đơn vị" in data[1]["issues"]  # bản ghi thiếu nguồn/đơn vị được đánh dấu
