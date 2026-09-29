"""Orchestrates the whole pipeline: outline -> story -> images -> layout."""
from __future__ import annotations

import logging
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.config import EXPORTS_DIR, PANELS_DIR, get_settings, redact
from app.schemas import Comic, ComicRequest
from app.services import exporters
from app.services.fallbacks import fallback_outline, fallback_story
from app.services.gemini_flash import generate_outline
from app.services.gemini_pro import generate_story
from app.services.image_generator import ImageBackend, compose_prompt
from app.services.layout_builder import build_panels

log = logging.getLogger("comiccraft.service")

_CACHE: dict[str, Comic] = {}
_ID_RE = re.compile(r"^[a-f0-9]{8,32}$")


def create_comic(req: ComicRequest) -> Comic:
    settings = get_settings()
    n = settings.comic_panels
    warnings: list[str] = []
    PANELS_DIR.mkdir(parents=True, exist_ok=True)
    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

    gemini_ok = not settings.mock_ai

    # 1) outline (Gemini Flash)
    if settings.mock_ai:
        outline = fallback_outline(req, n)
    else:
        try:
            outline = generate_outline(req, settings, n)
        except Exception as exc:  # noqa: BLE001
            gemini_ok = False
            log.exception("Outline generation failed")
            warnings.append(f"Gemini outline failed, offline template used. Reason: {redact(exc)[:350]}")
            outline = fallback_outline(req, n)

    # 2) story (Gemini)
    if not gemini_ok:
        story = fallback_story(req, outline)  # no point calling Gemini again if it just failed
    else:
        try:
            story = generate_story(req, outline, settings)
        except Exception as exc:  # noqa: BLE001
            log.exception("Story generation failed")
            warnings.append(f"Gemini story failed, offline text used. Reason: {redact(exc)[:350]}")
            story = fallback_story(req, outline)

    # 3) images (Hugging Face) - a few in parallel
    comic_id = uuid.uuid4().hex[:12]
    backend = ImageBackend(settings)
    prompts = {sp.panel_number: sp.image_prompt for sp in story}

    def render(op):
        img, warn = backend.generate(compose_prompt(prompts[op.panel_number], req), op.panel_number, op.title, op.scene)
        path = PANELS_DIR / f"{comic_id}_{op.panel_number}.png"
        img.save(path, format="PNG")
        return op.panel_number, str(path), f"/static/panels/{path.name}", warn

    images: dict[int, tuple[str, str]] = {}
    with ThreadPoolExecutor(max_workers=max(1, settings.image_workers)) as pool:
        for number, path, url, warn in pool.map(render, outline.panels):
            images[number] = (path, url)
            if warn and settings.show_provider_warnings:
                warnings.append(warn)

    # 4) layout
    panels = build_panels(outline, story, images)
    comic = Comic(
        id=comic_id,
        title=outline.title,
        request=req,
        panels=panels,
        warnings=list(dict.fromkeys(warnings)),
        mock=settings.mock_ai,
    )
    _CACHE[comic_id] = comic
    (EXPORTS_DIR / f"{comic_id}.json").write_text(comic.model_dump_json(indent=2), encoding="utf-8")
    return comic


def get_comic(comic_id: str) -> Comic | None:
    if not _ID_RE.match(comic_id or ""):
        return None
    if comic_id in _CACHE:
        return _CACHE[comic_id]
    f = EXPORTS_DIR / f"{comic_id}.json"
    if f.exists():
        comic = Comic.model_validate_json(f.read_text(encoding="utf-8"))
        _CACHE[comic_id] = comic
        return comic
    return None


def export_comic_pdf(comic: Comic) -> Path:
    return exporters.export_pdf(comic, EXPORTS_DIR / f"{comic.id}.pdf")
