from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator


class ComicRequest(BaseModel):
    story_prompt: str = Field(min_length=3, max_length=2000)
    character_name: str = Field(default="", max_length=100)
    setting: str = Field(default="", max_length=200)
    tone: str = Field(default="funny", max_length=50)
    art_style: str = Field(default="comic book", max_length=80)

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class OutlinePanel(BaseModel):
    panel_number: int
    title: str
    scene: str


class Outline(BaseModel):
    title: str
    panels: list[OutlinePanel]


class StoryPanel(BaseModel):
    panel_number: int
    narration: str
    dialogue: str = ""
    image_prompt: str


class ComicPanel(BaseModel):
    number: int
    title: str
    scene: str
    narration: str
    dialogue: str = ""
    image_prompt: str
    image_url: str = ""
    image_path: str = ""


class Comic(BaseModel):
    id: str
    title: str
    request: ComicRequest
    panels: list[ComicPanel]
    warnings: list[str] = Field(default_factory=list)
    mock: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
