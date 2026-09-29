"""Central configuration. Reads .env but never changes your keys."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PANELS_DIR = STATIC_DIR / "panels"
EXPORTS_DIR = STATIC_DIR / "exports"
TEMPLATES_DIR = BASE_DIR / "templates"


class Settings(BaseSettings):
    # utf-8-sig silently drops the BOM that Windows editors sometimes add,
    # which would otherwise turn the first variable name into "\ufeffGEMINI_API_KEY".
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8-sig",
        extra="ignore",
        env_ignore_empty=True,
    )

    gemini_api_key: str = ""
    hf_token: str = ""

    gemini_outline_model: str = "gemini-3.8-flash"
    gemini_story_model: str = "gemini-3.8-flash"
    gemini_image_model: str = "gemini-3.1-flash-image"
    # Tried in order if the configured model is unavailable / rate limited.
    gemini_fallback_models: str = "gemini-3.7-flash,gemini-3.6-flash,gemini-3.5-flash"
    gemini_image_fallback_models: str = "gemini-3-pro-image"

    hf_image_model: str = "stabilityai/stable-diffusion-3.5-large"
    hf_fallback_models: str = "black-forest-labs/FLUX.1-schnell,stabilityai/stable-diffusion-xl-base-1.0"
    hf_provider: str = "auto"

    # Image pipeline: Gemini first, Hugging Face second, local art last.
    image_backend: str = "gemini,huggingface,local"
    image_workers: int = 1
    show_provider_warnings: bool = False

    mock_ai: bool = False

    comic_panels: int = 5
    image_width: int = 768
    image_height: int = 768

    app_host: str = "127.0.0.1"
    app_port: int = 8000

    @field_validator("gemini_api_key", "hf_token", mode="before")
    @classmethod
    def _clean_secret(cls, v):
        return str(v or "").strip().strip('"').strip("'").strip()

    @field_validator("comic_panels")
    @classmethod
    def _clamp_panels(cls, v: int) -> int:
        return max(3, min(8, v))

    @field_validator("image_width", "image_height")
    @classmethod
    def _clamp_size(cls, v: int) -> int:
        v = max(256, min(1024, v))
        return v - (v % 8)

    @property
    def gemini_fallbacks(self) -> list[str]:
        return [m.strip() for m in self.gemini_fallback_models.split(",") if m.strip()]

    @property
    def hf_fallbacks(self) -> list[str]:
        return [m.strip() for m in self.hf_fallback_models.split(",") if m.strip()]

    @property
    def gemini_image_fallbacks(self) -> list[str]:
        return [m.strip() for m in self.gemini_image_fallback_models.split(",") if m.strip()]

    @property
    def image_backends(self) -> list[str]:
        allowed = {"gemini", "huggingface", "local"}
        return [x.strip().lower() for x in self.image_backend.split(",") if x.strip().lower() in allowed]


@lru_cache
def get_settings() -> Settings:
    return Settings()


def redact(text: object) -> str:
    """Remove secrets from any text before it is logged or shown to the user."""
    s = get_settings()
    out = str(text)
    for secret in (s.gemini_api_key, s.hf_token):
        if secret and len(secret) > 6:
            out = out.replace(secret, "***")
    return out
