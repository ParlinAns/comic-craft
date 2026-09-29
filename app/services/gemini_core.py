"""Shared Gemini helper: one client, model fallbacks, tolerant JSON parsing."""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from app.config import Settings, redact

log = logging.getLogger("comiccraft.gemini")


class AIServiceError(RuntimeError):
    """A readable error coming from an external AI provider."""


_AUTH = ("api key not valid", "api_key_invalid", "unauthenticated", "permission_denied",
         "invalid authentication", "api keys are not supported", "401", "403")
_MISSING = ("not found", "404", "not supported", "unsupported")
_TRANSIENT = ("429", "500", "502", "503", "504", "unavailable", "high demand", "rate limit", "resource exhausted", "overloaded")

_CLIENTS: dict[str, Any] = {}


def get_client(settings: Settings):
    if not settings.gemini_api_key:
        raise AIServiceError("GEMINI_API_KEY is missing in .env")
    if settings.gemini_api_key not in _CLIENTS:
        from google import genai
        from google.genai import types

        _CLIENTS[settings.gemini_api_key] = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=90_000),  # milliseconds
        )
    return _CLIENTS[settings.gemini_api_key]


def extract_json(text: str) -> Any:
    """Parse JSON even if the model wrapped it in ```json fences or added prose."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
        if not m:
            raise
        return json.loads(m.group(1))


def generate_json(settings: Settings, primary_model: str, prompt: str) -> tuple[Any, str]:
    """Ask Gemini for JSON. Returns (parsed_data, model_used)."""
    from google.genai import types

    client = get_client(settings)
    models = [primary_model] + [m for m in settings.gemini_fallbacks if m != primary_model]
    errors: list[str] = []

    for model in models:
        for attempt in range(3):
            try:
                # Gemini 3.x ignores temperature/top_p, so we only request JSON output.
                resp = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(response_mime_type="application/json"),
                )
                text = resp.text
                if not text:
                    raise ValueError("empty response (possibly blocked by safety filters)")
                return extract_json(text), model
            except Exception as exc:  # noqa: BLE001 - we want every failure reported
                msg = redact(f"{type(exc).__name__}: {exc}")
                errors.append(f"{model} -> {msg[:300]}")
                log.warning("Gemini call failed (%s, attempt %d): %s", model, attempt + 1, msg)
                low = msg.lower()
                if any(k in low for k in _AUTH):
                    raise AIServiceError(
                        "Gemini rejected the API key/permissions. " + msg[:300]
                    ) from exc
                if any(k in low for k in _MISSING):
                    break  # this model id doesn't exist for this key -> next model
                if attempt < 2 and any(k in low for k in _TRANSIENT):
                    time.sleep(2 ** attempt)
                elif attempt < 2:
                    time.sleep(1)

    raise AIServiceError("Gemini request failed. " + " | ".join(errors[-3:]))
