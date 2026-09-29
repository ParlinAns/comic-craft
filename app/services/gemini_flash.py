"""Step 1 - Gemini Flash creates the structured panel outline."""
from __future__ import annotations

import json
import logging

from app.config import Settings
from app.schemas import ComicRequest, Outline, OutlinePanel
from app.services.fallbacks import fallback_outline
from app.services.gemini_core import generate_json

log = logging.getLogger("comiccraft.outline")

_SHAPE = json.dumps(
    {"title": "Comic title", "panels": [{"panel_number": 1, "title": "Short caption", "scene": "What is visible and happening"}]}
)


def _prompt(req: ComicRequest, n: int) -> str:
    return (
        f"You are a comic-book story planner. Plan a comic of EXACTLY {n} panels with a clear "
        f"beginning, middle and end.\n"
        f"Story idea: {req.story_prompt}\n"
        f"Main character: {req.character_name or 'invent one'}\n"
        f"Setting: {req.setting or 'your choice'}\n"
        f"Tone: {req.tone}\n"
        f"Art style: {req.art_style}\n\n"
        f"Reply with ONLY valid JSON in this shape: {_SHAPE}\n"
        f"Each scene is one or two sentences describing the visible action."
    )


def _coerce(data, req: ComicRequest, n: int) -> Outline:
    if isinstance(data, list):
        data = {"panels": data}
    if not isinstance(data, dict):
        raise ValueError("outline is not a JSON object")
    raw = data.get("panels") or data.get("outline") or []
    panels: list[OutlinePanel] = []
    for item in raw:
        if isinstance(item, str):
            item = {"scene": item}
        if not isinstance(item, dict):
            continue
        scene = item.get("scene") or item.get("description") or item.get("summary") or item.get("action") or ""
        if not str(scene).strip():
            continue
        i = len(panels) + 1
        title = item.get("title") or item.get("caption") or f"Panel {i}"
        panels.append(OutlinePanel(panel_number=i, title=str(title).strip(), scene=str(scene).strip()))
        if len(panels) == n:
            break
    if len(panels) < 2:
        raise ValueError("Gemini returned fewer than 2 usable panels")
    if len(panels) < n:  # pad rather than fail
        filler = fallback_outline(req, n).panels
        for extra in filler[len(panels):]:
            panels.append(OutlinePanel(panel_number=len(panels) + 1, title=extra.title, scene=extra.scene))
    title = str(data.get("title") or "").strip() or fallback_outline(req, n).title
    return Outline(title=title, panels=panels)


def generate_outline(req: ComicRequest, settings: Settings, n: int) -> Outline:
    data, model = generate_json(settings, settings.gemini_outline_model, _prompt(req, n))
    log.info("Outline generated with %s", model)
    return _coerce(data, req, n)
