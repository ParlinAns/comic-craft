# ComicCraft - AI Comic Story Creator (v2, crash-proof rewrite)

FastAPI + Jinja2 app: story idea -> Gemini outline -> Gemini narration/dialogue -> Hugging Face panel art -> layout -> PDF.

## What was rewritten and why

| Problem that causes `500 Internal Server Error` | Fix in this version |
|---|---|
| `.env` says `COMIC_PANELS=6` but the code expected exactly 5 panels | Panel count comes from `COMIC_PANELS` (3-8); Gemini output is padded/trimmed to match |
| Gemini returns JSON in fences, extra prose, or slightly different field names | Tolerant JSON parser and field mapping instead of strict schema |
| Gemini 3.x rejects old parameters (`temperature`, `thinking_level=MINIMAL`) | Only `response_mime_type=application/json` is sent |
| Model id unavailable / rate limited | Automatic fallback models (`GEMINI_FALLBACK_MODELS`) |
| Hugging Face rejects token, provider, model or `width/height` | Retries without size, tries fallback models, then uses labelled placeholder art |
| fpdf2 crashes on curly quotes, em dashes, emoji | All PDF text is sanitised to Latin-1 first |
| Old `TemplateResponse(name, {"request": ...})` signature | Uses the current `TemplateResponse(request, name, context)` |
| `.env` saved with a Windows BOM or quotes around keys | `utf-8-sig` decoding and quote stripping (your key values are never altered) |
| Any other unexpected exception | Global handler shows a readable error page and logs the full traceback |

If Gemini or Hugging Face fails, you still get a comic and a yellow warning banner that says exactly why, instead of a 500.

## Setup

```powershell
py -3.12 -m venv .venv          # 3.11-3.13 recommended; 3.14 works if all wheels install
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -U google-genai huggingface_hub
```

Keep your existing `.env` (same variable names). Optional new lines are in `.env.example`.

```powershell
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Diagnose in 30 seconds

| URL | What it tells you |
|---|---|
| `/health` | Are keys present, which models and panel count are loaded (no secrets shown) |
| `/dev/test-gemini` | One tiny Gemini call: `{"ok": true}` or the exact error |
| `/dev/test-image` | One Hugging Face image (response header `X-ComicCraft-Warning` shows any failure) |
| `/docs` | Interactive API docs |

The terminal log also prints a startup line showing which keys were detected.

## Tests

```bash
pytest -q
```

Tests force `MOCK_AI=true`; no keys needed.

## Project layout

```text
app/  main.py config.py schemas.py routes.py
      services/ gemini_core.py gemini_flash.py gemini_pro.py fallbacks.py
                image_generator.py layout_builder.py exporters.py comic_service.py
static/ css/style.css  js/app.js  panels/  exports/
templates/ base.html index.html comic_preview.html export_success.html error.html
tests/ conftest.py test_layout_export.py test_api.py
```

## Resilient AI pipeline

The image pipeline is now `Gemini -> Hugging Face -> local`. Gemini native image generation is the first choice, so a Hugging Face Inference Providers permission problem does not stop image generation. If an online provider is unavailable, ComicCraft quietly creates deterministic local panel art instead of showing a provider error or returning HTTP 500.

Gemini text requests retry transient 429/5xx/high-demand failures before moving to the configured fallback model. Image requests are deliberately limited to one worker by default to reduce bursts that can trigger provider overload.

Only the safe `.env.example` is included in the distribution. Never commit your real `.env` or API keys.
