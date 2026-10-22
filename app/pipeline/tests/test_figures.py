"""Trích hình có chú thích từ PDF và lưu sidecar figures.json."""

import pymupdf

from app.pipeline import figures as figures_mod


def _make_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 300, 200), False)
    pix.clear_with(120)
    page.insert_image(pymupdf.Rect(72, 72, 372, 272), pixmap=pix)
    page.insert_text((72, 290), "Figure 2: Satellite view of the study area.")
    # ảnh nhỏ (logo) và ảnh lớn không có chú thích đều bị bỏ
    page.insert_image(pymupdf.Rect(72, 400, 102, 430), pixmap=pix)
    page.insert_image(pymupdf.Rect(300, 450, 550, 650), pixmap=pix)
    doc.save(path)
    doc.close()


def test_extract_and_load_figures(tmp_path, monkeypatch):
    monkeypatch.setattr(figures_mod, "figures_root", lambda: tmp_path / "figures")
    pdf = tmp_path / "p.pdf"
    _make_pdf(pdf)

    figs = figures_mod.extract_figures(pdf, figures_mod.figures_dir("paper-1"), source_title="p.pdf")

    assert len(figs) == 1
    assert figs[0]["page"] == 1 and figs[0]["caption"].startswith("Figure 2: Satellite view")
    loaded = figures_mod.load_figures("paper-1")
    assert loaded[0]["paper_id"] == "paper-1" and loaded[0]["source_title"] == "p.pdf"
    assert figures_mod.resolve_figure_path(loaded[0]["path"]) is not None
    # chạy lại không nhân đôi hình
    assert len(figures_mod.extract_figures(pdf, figures_mod.figures_dir("paper-1"))) == 1


def test_load_figures_rejects_bad_ids_and_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(figures_mod, "figures_root", lambda: tmp_path / "figures")
    assert figures_mod.load_figures("../etc") == []
    assert figures_mod.load_figures("missing") == []
    outside = tmp_path / "x.png"
    outside.write_bytes(b"x")
    assert figures_mod.resolve_figure_path(str(outside)) is None
    assert figures_mod.resolve_figure_path(None) is None


def test_composite_figure_is_merged_and_thin_bars_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(figures_mod, "figures_root", lambda: tmp_path / "figures")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    pix.clear_with(90)
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(100, 90, 165, 220), pixmap=pix)  # (left) hẹp, cách xa chú thích
    page.insert_image(pymupdf.Rect(300, 80, 420, 265), pixmap=pix)  # (right)
    page.insert_text((100, 290), "Figure 2: (left) Scaled attention. (right) Multi-head attention.")
    page.insert_image(pymupdf.Rect(50, 500, 550, 520), pixmap=pix)  # thanh ngang 25:1
    page.insert_text((50, 535), "Figure 3: separator-like banner")
    pdf = tmp_path / "c.pdf"
    doc.save(pdf)
    doc.close()

    figs = figures_mod.extract_figures(pdf, figures_mod.figures_dir("c"))

    assert [f["caption"][:9] for f in figs] == ["Figure 2:"]
    assert figs[0]["width"] > 600  # gộp cả hai ô: ~320pt ở 150 dpi


def _gray_pix():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), False)
    pix.clear_with(120)
    return pix


def _extract(tmp_path, monkeypatch, doc, name):
    monkeypatch.setattr(figures_mod, "figures_root", lambda: tmp_path / "figures")
    pdf = tmp_path / f"{name}.pdf"
    doc.save(pdf)
    doc.close()
    return figures_mod.extract_figures(pdf, figures_mod.figures_dir(name))


def test_caption_regex_variants():
    for text in ("Fig 3", "FIGURE 3 The model", "Figure 3. Overview", "Hình 3: Sơ đồ", "Fig. 12a: x"):
        assert figures_mod._CAPTION_RE.match(text), text
    for text in ("Figure 3 shows the results", "Table 1: BLEU", "In Figure 3, we"):
        assert not figures_mod._CAPTION_RE.match(text), text


def test_vector_chart_is_extracted(tmp_path, monkeypatch):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(72, 60, 540, 110), "Body paragraph before the chart. " * 6)
    shape = page.new_shape()
    shape.draw_line((100, 330), (500, 330))  # trục x
    shape.draw_line((100, 330), (100, 140))  # trục y
    for i in range(8):  # cột
        shape.draw_rect(pymupdf.Rect(120 + i * 45, 330 - 20 * (i + 1), 150 + i * 45, 330))
    shape.finish(color=(0, 0, 0), fill=(0.3, 0.5, 0.8))
    shape.commit()
    page.insert_text((280, 345), "Epoch")  # nhãn trục: nằm trong hình
    page.insert_text((72, 370), "Figure 4: Accuracy per epoch.")
    page.insert_textbox(pymupdf.Rect(72, 390, 540, 450), "Body paragraph after the chart. " * 6)

    figs = _extract(tmp_path, monkeypatch, doc, "vec")

    assert len(figs) == 1
    assert figs[0]["kind"] == "vector" and figs[0]["caption"].startswith("Figure 4:")
    assert figs[0]["height"] > 190 * 150 / 72  # phủ hết vùng cột + nhãn trục


def test_table_rules_are_not_a_figure(tmp_path, monkeypatch):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Table 1: BLEU scores of the models.")
    for row in range(12):  # kẻ ngang + chữ: bảng kiểu booktabs
        y = 115 + row * 18
        page.draw_line((72, y), (520, y), width=0.5)
        page.insert_text((80, y + 13), f"Model {row}    27.{row}    41.{row}")
    # chú thích kiểu hình đặt ngay dưới bảng vẫn không biến bảng thành hình
    page.insert_text((72, 340), "Figure 9: mislabeled caption under the table.")

    assert _extract(tmp_path, monkeypatch, doc, "tbl") == []


def test_caption_from_other_column_is_ignored(tmp_path, monkeypatch):
    doc = pymupdf.open()
    page = doc.new_page()  # 612 x 792, hai cột chia tại x=306
    page.insert_textbox(pymupdf.Rect(40, 40, 296, 90), "Left column paragraph text here. " * 4)
    page.insert_textbox(pymupdf.Rect(316, 40, 572, 90), "Right column paragraph text here. " * 4)
    page.insert_image(pymupdf.Rect(40, 100, 300, 280), pixmap=_gray_pix())
    # chú thích cột phải gần ảnh hơn nhưng chỉ chạm mép ảnh
    page.insert_text((292, 290), "Figure 2: right column.")
    page.insert_text((40, 320), "Figure 1: left image.")

    figs = _extract(tmp_path, monkeypatch, doc, "twocol")

    assert [f["caption"] for f in figs] == ["Figure 1: left image."]
    assert figs[0]["kind"] == "raster"


def test_side_caption(tmp_path, monkeypatch):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(72, 100, 300, 300), pixmap=_gray_pix())
    page.insert_text((315, 180), "Fig. 5. Side caption.")

    figs = _extract(tmp_path, monkeypatch, doc, "side")

    assert len(figs) == 1 and figs[0]["caption"] == "Fig. 5. Side caption." and figs[0]["kind"] == "raster"
