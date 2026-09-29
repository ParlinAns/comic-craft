"""PDF export with fpdf2.

fpdf2's built-in fonts only support Latin-1. AI-written text often contains
curly quotes, dashes or emoji, which would raise FPDFUnicodeEncodingException,
so all text goes through safe_text() first.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from fpdf import FPDF
from PIL import Image

from app.schemas import Comic

_REPLACEMENTS = {
    "\u2018": "'", "\u2019": "'", "\u201a": ",", "\u201c": '"', "\u201d": '"', "\u201e": '"',
    "\u2013": "-", "\u2014": "-", "\u2015": "-", "\u2026": "...", "\u2022": "*", "\u00a0": " ",
    "\u2192": "->", "\u2190": "<-", "\u2764": "<3",
}


def safe_text(text: str, limit: int | None = None) -> str:
    text = str(text or "")
    for src, dst in _REPLACEMENTS.items():
        text = text.replace(src, dst)
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    text = text.encode("latin-1", "replace").decode("latin-1")
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = textwrap.shorten(text, width=limit, placeholder="...")
    return text


def _valid_image(path: str) -> bool:
    try:
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:  # noqa: BLE001
        return False


def export_pdf(comic: Comic, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    pdf = FPDF(unit="mm", format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_margins(10, 10, 10)
    pdf.set_title(safe_text(comic.title))
    pdf.set_creator("ComicCraft")

    cell_w, img = 90.0, 84.0
    col_x = (10.0, 110.0)
    row_pitch = 124.0
    per_page = 4

    for idx, panel in enumerate(comic.panels):
        slot = idx % per_page
        if slot == 0:
            pdf.add_page()
            top = 10.0
            if idx == 0:
                pdf.set_xy(10, 10)
                pdf.set_font("Helvetica", "B", 20)
                pdf.cell(190, 10, safe_text(comic.title, 70), new_x="LMARGIN", new_y="NEXT", align="C")
                pdf.set_font("Helvetica", "I", 9)
                sub = " / ".join(x for x in (comic.request.character_name, comic.request.setting, comic.request.tone) if x)
                pdf.cell(190, 6, safe_text(sub, 100), new_x="LMARGIN", new_y="NEXT", align="C")
                top = 30.0
            page_top = top
        col, row = slot % 2, slot // 2
        x = col_x[col]
        y = page_top + row * row_pitch

        if panel.image_path and _valid_image(panel.image_path):
            pdf.image(panel.image_path, x=x + (cell_w - img) / 2, y=y, w=img, h=img)
        pdf.set_draw_color(20, 20, 43)
        pdf.set_line_width(0.6)
        pdf.rect(x + (cell_w - img) / 2, y, img, img)

        pdf.set_xy(x, y + img + 2)
        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(cell_w, 4, safe_text(f"{panel.number}. {panel.title}", 60), new_x="LEFT", new_y="NEXT")
        pdf.set_x(x)
        pdf.set_font("Helvetica", "", 8.5)
        pdf.multi_cell(cell_w - 2, 4, safe_text(panel.narration, 230))
        if panel.dialogue:
            pdf.set_x(x)
            pdf.set_font("Helvetica", "BI", 8.5)
            pdf.multi_cell(cell_w - 2, 4, safe_text('"' + panel.dialogue + '"', 160))

    if not comic.panels:
        pdf.add_page()
    pdf.output(str(out_path))
    return out_path
