from app.schemas import Comic, ComicPanel, ComicRequest
from app.services.exporters import export_pdf, safe_text
from app.services.image_generator import make_placeholder
from app.services.layout_builder import layout_rows


def test_layout_rows():
    assert layout_rows(5) == [[1], [2, 3], [4, 5]]
    assert layout_rows(6) == [[1, 2], [3, 4], [5, 6]]
    assert layout_rows(3) == [[1], [2, 3]]


def test_safe_text_handles_unicode():
    out = safe_text("\u201cHello\u201d \u2014 it\u2019s fine \U0001F98A")
    out.encode("latin-1")  # must not raise
    assert "Hello" in out


def test_pdf_export_with_unicode(tmp_path):
    panels = []
    for i in range(1, 7):
        img_path = tmp_path / f"p{i}.png"
        make_placeholder(i, f"Panel {i}", "A scene", 256, 256).save(img_path)
        panels.append(ComicPanel(number=i, title="\u201cSmart\u201d title \u2014 \U0001F98A", scene="s",
                                 narration="It\u2019s a long story " * 30, dialogue="Wow\u2026", image_prompt="p",
                                 image_path=str(img_path), image_url="/x.png"))
    comic = Comic(id="abc123abc123", title="T\u00eate-\u00e0-t\u00eate \u2014 test", request=ComicRequest(story_prompt="test story"), panels=panels)
    out = export_pdf(comic, tmp_path / "out.pdf")
    assert out.read_bytes()[:4] == b"%PDF"
