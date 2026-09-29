"""Turns outline + story + images into unified ComicPanel objects and a page layout."""
from __future__ import annotations

from app.schemas import ComicPanel, Outline, StoryPanel


def build_panels(outline: Outline, story: list[StoryPanel], images: dict[int, tuple[str, str]]) -> list[ComicPanel]:
    """images maps panel number -> (image_path, image_url)."""
    story_by_no = {s.panel_number: s for s in story}
    panels: list[ComicPanel] = []
    for op in outline.panels:
        sp = story_by_no[op.panel_number]
        path, url = images.get(op.panel_number, ("", ""))
        panels.append(
            ComicPanel(
                number=op.panel_number,
                title=op.title,
                scene=op.scene,
                narration=sp.narration,
                dialogue=sp.dialogue,
                image_prompt=sp.image_prompt,
                image_path=path,
                image_url=url,
            )
        )
    return panels


def layout_rows(n: int) -> list[list[int]]:
    """Row layout of panel numbers. Odd counts open with one wide panel, the rest are pairs."""
    nums = list(range(1, n + 1))
    rows: list[list[int]] = []
    if n % 2 == 1 and n > 0:
        rows.append([nums.pop(0)])
    while nums:
        rows.append(nums[:2])
        nums = nums[2:]
    return rows
