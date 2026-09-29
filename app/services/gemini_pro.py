"""Step 2 - Gemini expands the outline into narration, dialogue and image prompts."""
from __future__ import annotations

import json
import logging

from app.config import Settings
from app.schemas import ComicRequest, Outline, StoryPanel
from app.services.fallbacks import fallback_story, image_prompt_for
from app.services.gemini_core import generate_json

log = logging.getLogger("comiccraft.story")

_SHAPE = json.dumps(
    {"panels": [{"panel_number": 1, "narration": "Caption text", "dialogue": "Speech bubble text or empty", "image_prompt": "Visual description"}]}
)


def _prompt(req: ComicRequest, outline: Outline) -> str:
    outline_json = json.dumps([p.model_dump() for p in outline.panels], ensure_ascii=False)
    return (
        f"You are a comic writer. Comic title: {outline.title}\n"
        f"Main character: {req.character_name or 'the hero'} | Setting: {req.setting or 'as outlined'} | "
        f"Tone: {req.tone} | Art style: {req.art_style}\n"
        f"Panel outline: {outline_json}\n\n"
        f"For EVERY panel write:\n"
        f"- narration: max 25 words, caption style\n"
        f"- dialogue: max 18 words, one speech bubble (may be an empty string)\n"
        f"- image_prompt: an English visual description for an image generator. Describe the character's "
        f"look the same way in every panel. No text, letters or speech bubbles in the picture.\n\n"
        f"Reply with ONLY valid JSON in this shape: {_SHAPE}"
    )


def _coerce(data, req: ComicRequest, outline: Outline) -> list[StoryPanel]:
    if isinstance(data, list):
        data = {"panels": data}
    raw = data.get("panels", []) if isinstance(data, dict) else []
    if not raw:
        raise ValueError("story has no panels")
    fallback = {p.panel_number: p for p in fallback_story(req, outline)}
    result: list[StoryPanel] = []
    for i, op in enumerate(outline.panels):
        item = raw[i] if i < len(raw) and isinstance(raw[i], dict) else {}
        fb = fallback[op.panel_number]
        narration = str(item.get("narration") or item.get("caption") or fb.narration).strip()
        dialogue = str(item.get("dialogue") or "").strip()
        prompt = str(item.get("image_prompt") or item.get("image") or "").strip() or image_prompt_for(req, op.scene)
        result.append(StoryPanel(panel_number=op.panel_number, narration=narration, dialogue=dialogue, image_prompt=prompt))
    return result


def generate_story(req: ComicRequest, outline: Outline, settings: Settings) -> list[StoryPanel]:
    data, model = generate_json(settings, settings.gemini_story_model, _prompt(req, outline))
    log.info("Story generated with %s", model)
    return _coerce(data, req, outline)
