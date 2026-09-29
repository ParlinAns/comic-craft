"""Offline outline/story templates.

Used by MOCK_AI mode and as a safety net when Gemini is unreachable, so the
app always produces a comic instead of crashing with HTTP 500.
"""
from __future__ import annotations

from app.schemas import ComicRequest, Outline, OutlinePanel, StoryPanel

_BEATS = [
    ("Meet {name}", "{name} is introduced in {setting}, ready for whatever the day brings. Story seed: {story}"),
    ("A strange discovery", "{name} notices something unusual in {setting} that sparks curiosity."),
    ("Into the unknown", "{name} follows the clue deeper into {setting}, leaving the familiar behind."),
    ("An obstacle appears", "A surprising obstacle blocks the way and {name} has to think fast."),
    ("A clever plan", "{name} comes up with a bold, {tone} plan."),
    ("Things go sideways", "The plan works, just not the way anyone expected."),
    ("The big moment", "{name} faces the biggest challenge of the whole story."),
    ("A happy ending", "Back where it all began, {name} smiles. Nothing will be quite the same."),
]
_LINES = [
    "Today is going to be interesting!",
    "Wait... what is that?",
    "Stay close. We're going in.",
    "Well, that wasn't in the plan!",
    "I have an idea!",
    "Hold on tight!",
    "Now or never!",
    "Best. Day. Ever.",
]


def _beat_indices(n: int) -> list[int]:
    if n <= 1:
        return [0]
    return [min(len(_BEATS) - 1, int(i * (len(_BEATS) - 1) / (n - 1) + 0.5)) for i in range(n)]


def _fmt(template: str, req: ComicRequest) -> str:
    # str.replace instead of str.format so user text containing { } can never break it.
    values = {
        "{name}": req.character_name or "The hero",
        "{setting}": req.setting or "a colourful world",
        "{tone}": req.tone or "playful",
        "{story}": req.story_prompt,
    }
    for key, val in values.items():
        template = template.replace(key, val)
    return template


def fallback_outline(req: ComicRequest, n: int) -> Outline:
    panels = []
    for i, b in enumerate(_beat_indices(n), start=1):
        title, scene = _BEATS[b]
        panels.append(OutlinePanel(panel_number=i, title=_fmt(title, req), scene=_fmt(scene, req)))
    title = req.story_prompt if len(req.story_prompt) <= 60 else req.story_prompt[:57].rstrip() + "..."
    return Outline(title=title, panels=panels)


def image_prompt_for(req: ComicRequest, scene: str) -> str:
    who = req.character_name or "the hero"
    return f"{scene} Main character: {who}. Setting: {req.setting or 'a colourful world'}. Mood: {req.tone}."


def fallback_story(req: ComicRequest, outline: Outline) -> list[StoryPanel]:
    idx = _beat_indices(len(outline.panels))
    out = []
    for p, b in zip(outline.panels, idx):
        out.append(
            StoryPanel(
                panel_number=p.panel_number,
                narration=p.scene,
                dialogue=_LINES[b],
                image_prompt=image_prompt_for(req, p.scene),
            )
        )
    return out
