"""Resilient comic-panel image generation.

Pipeline:
1. Gemini native image generation (uses the same Gemini API key as story generation)
2. Hugging Face Inference Providers (optional)
3. Deterministic local placeholder art (always available)

The web app never exposes provider stack traces or turns an image-provider failure
into HTTP 500. Provider details are logged locally for debugging.
"""
from __future__ import annotations

import hashlib
import logging
import textwrap
import threading
import time

from PIL import Image, ImageDraw, ImageFont

from app.config import Settings, redact
from app.schemas import ComicRequest
from app.services.gemini_core import get_client

log = logging.getLogger("comiccraft.image")

_INK = (20, 20, 43)
_PALETTE = [(255, 210, 63), (255, 122, 150), (60, 200, 185), (150, 140, 255), (255, 160, 90)]
_TRANSIENT = ("429", "500", "502", "503", "504", "unavailable", "high demand", "rate limit", "resource exhausted", "overloaded")
_AUTH = ("401", "403", "unauthorized", "forbidden", "invalid token", "invalid credentials", "sufficient permissions", "permission")
_NEXT_MODEL = ("404", "not found", "not supported", "unsupported", "model_not_supported")


def compose_prompt(panel_prompt: str, req: ComicRequest) -> str:
    who = f" Keep the character {req.character_name} looking consistent." if req.character_name else ""
    return (
        f"{panel_prompt.strip()} Art style: {req.art_style}. Single comic-book panel illustration.{who} "
        f"No text, no letters, no speech bubbles, no watermark."
    )[:1500]


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def make_placeholder(number: int, title: str, scene: str, width: int, height: int, note: str = "") -> Image.Image:
    seed = int(hashlib.md5(f"{number}|{title}".encode("utf-8")).hexdigest()[:6], 16)
    bg = _PALETTE[seed % len(_PALETTE)]
    dot = tuple(min(255, c + 28) for c in bg)
    img = Image.new("RGB", (width, height), bg)
    d = ImageDraw.Draw(img)
    step = max(24, width // 24)
    for row, y in enumerate(range(0, height + step, step)):
        for x in range(0, width + step, step):
            r = int(2 + 0.34 * step * (x + y) / (width + height))
            ox = step // 2 if row % 2 else 0
            d.ellipse((x + ox - r, y - r, x + ox + r, y + r), fill=dot)
    pad = width // 14
    box = (pad, int(height * 0.52), width - pad, height - pad)
    d.rounded_rectangle((box[0] + 8, box[1] + 8, box[2] + 8, box[3] + 8), radius=18, fill=_INK)
    d.rounded_rectangle(box, radius=18, fill=(255, 255, 255), outline=_INK, width=4)
    f_title, f_body = _font(max(20, width // 22)), _font(max(15, width // 34))
    title_chars = max(12, int((box[2] - box[0] - 36) / (max(20, width // 22) * 0.55)))
    y = box[1] + 16
    for line in textwrap.wrap(title, width=title_chars)[:2]:
        d.text((box[0] + 18, y), line, font=f_title, fill=_INK)
        y += width // 20
    y += 6
    body_size = max(15, width // 34)
    chars = max(16, int((box[2] - box[0] - 36) / (body_size * 0.55)))
    for line in textwrap.wrap(scene, width=chars)[:5]:
        d.text((box[0] + 18, y), line, font=f_body, fill=(60, 60, 90))
        y += width // 30
    d.ellipse((pad, pad, pad + 84, pad + 84), fill=(255, 255, 255), outline=_INK, width=5)
    d.text((pad + 42, pad + 42), str(number), font=_font(46), fill=_INK, anchor="mm")
    if note:
        d.text((width - pad, pad + 6), note, font=_font(max(14, width // 44)), fill=_INK, anchor="ra")
    return img


class ImageBackend:
    """Try configured providers, then always return local art."""

    def __init__(self, settings: Settings):
        self.s = settings
        self._hf_client = None
        self._lock = threading.Lock()
        self._provider_disabled: set[str] = set()

    def _get_hf_client(self):
        with self._lock:
            if self._hf_client is None:
                from huggingface_hub import InferenceClient
                try:
                    self._hf_client = InferenceClient(provider=self.s.hf_provider, api_key=self.s.hf_token, timeout=120)
                except (TypeError, ValueError):
                    self._hf_client = InferenceClient(api_key=self.s.hf_token, timeout=120)
            return self._hf_client

    def _gemini_image(self, prompt: str) -> Image.Image:
        """Generate an image using Gemini's native image model."""
        from google.genai import types

        client = get_client(self.s)
        models = [self.s.gemini_image_model] + [m for m in self.s.gemini_image_fallbacks if m != self.s.gemini_image_model]
        last = "unknown Gemini image error"
        for model in models:
            for attempt in range(3):
                try:
                    response = client.models.generate_content(
                        model=model,
                        contents=[prompt],
                        config=types.GenerateContentConfig(response_modalities=["IMAGE"]),
                    )
                    for part in (response.parts or []):
                        try:
                            image = part.as_image()
                        except Exception:
                            image = None
                        if image is not None:
                            return image.convert("RGB")
                    raise RuntimeError("Gemini image response contained no image data")
                except Exception as exc:  # noqa: BLE001
                    last = redact(f"{type(exc).__name__}: {exc}")[:300]
                    low = last.lower()
                    log.warning("Gemini image failed (%s, attempt %d): %s", model, attempt + 1, last)
                    if any(k in low for k in _AUTH):
                        # Key/permission errors are not fixed by retrying the same request.
                        break
                    if any(k in low for k in _NEXT_MODEL):
                        break
                    if attempt < 2 and any(k in low for k in _TRANSIENT):
                        time.sleep(2 ** attempt)
                    elif attempt < 2:
                        time.sleep(1)
        raise RuntimeError(last)

    def _hf_image(self, prompt: str) -> Image.Image:
        if not self.s.hf_token:
            raise RuntimeError("HF token not configured")
        client = self._get_hf_client()
        models = [self.s.hf_image_model] + [m for m in self.s.hf_fallbacks if m != self.s.hf_image_model]
        last = "unknown Hugging Face error"
        for model in models:
            for attempt in range(2):
                try:
                    return client.text_to_image(prompt, model=model)
                except Exception as exc:  # noqa: BLE001
                    last = redact(f"{type(exc).__name__}: {exc}")[:300]
                    low = last.lower()
                    log.warning("Hugging Face image failed (%s, attempt %d): %s", model, attempt + 1, last)
                    if any(k in low for k in _AUTH):
                        # Permission errors will affect every panel; stop wasting requests.
                        raise RuntimeError(last)
                    if any(k in low for k in _NEXT_MODEL):
                        break
                    if attempt < 1 and any(k in low for k in _TRANSIENT):
                        time.sleep(2)
        raise RuntimeError(last)

    def generate(self, prompt: str, number: int, title: str, scene: str) -> tuple[Image.Image, str | None]:
        w, h = self.s.image_width, self.s.image_height
        if self.s.mock_ai:
            return make_placeholder(number, title, scene, w, h, "mock"), None

        failures: list[str] = []
        for backend in self.s.image_backends or ["local"]:
            if backend in self._provider_disabled:
                continue
            try:
                if backend == "gemini":
                    if not self.s.gemini_api_key:
                        raise RuntimeError("Gemini API key not configured")
                    img = self._gemini_image(prompt)
                elif backend == "huggingface":
                    if not self.s.hf_token:
                        raise RuntimeError("Hugging Face token not configured")
                    img = self._hf_image(prompt)
                else:
                    img = make_placeholder(number, title, scene, w, h, "local")
                if img.size != (w, h):
                    img = img.resize((w, h), Image.LANCZOS)
                return img.convert("RGB"), None
            except Exception as exc:  # noqa: BLE001
                reason = redact(f"{type(exc).__name__}: {exc}")[:180]
                failures.append(f"{backend}: {reason}")
                log.warning("Image backend '%s' unavailable for panel %d: %s", backend, number, reason)
                if backend in {"gemini", "huggingface"} and ("403" in reason or "401" in reason or "permission" in reason.lower() or "token" in reason.lower()):
                    self._provider_disabled.add(backend)

        # This is deliberately not an error page: the comic can always be rendered locally.
        return make_placeholder(number, title, scene, w, h, "local"), None
