from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.config import TEMPLATES_DIR, get_settings, redact
from app.schemas import Comic, ComicRequest
from app.services.comic_service import create_comic, export_comic_pdf, get_comic
from app.services.image_generator import ImageBackend, compose_prompt
from app.services.layout_builder import layout_rows

log = logging.getLogger("comiccraft.routes")
router = APIRouter()
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

TONES = ["funny", "adventurous", "heartwarming", "mysterious", "dramatic", "sci-fi"]
STYLES = ["comic book", "manga", "cartoon", "watercolor", "pixel art", "noir ink"]


def render(request: Request, name: str, context: dict | None = None, status: int = 200) -> HTMLResponse:
    return templates.TemplateResponse(request, name, context or {}, status_code=status)


def error_page(request: Request, title: str, message: str, status: int = 500, detail: str = "") -> HTMLResponse:
    return render(request, "error.html", {"title": title, "message": message, "detail": redact(detail), "status": status}, status)


def _index_ctx(form: dict | None = None, error: str | None = None) -> dict:
    return {"tones": TONES, "styles": STYLES, "form": form or {}, "error": error, "mock": get_settings().mock_ai}


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render(request, "index.html", _index_ctx())


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@router.post("/generate-comic", response_class=HTMLResponse)
def generate_comic_form(
    request: Request,
    story_prompt: str = Form(""),
    character_name: str = Form(""),
    setting: str = Form(""),
    tone: str = Form("funny"),
    art_style: str = Form("comic book"),
):
    form = dict(story_prompt=story_prompt, character_name=character_name, setting=setting, tone=tone, art_style=art_style)
    try:
        req = ComicRequest(**form)
    except ValidationError:
        return render(request, "index.html", _index_ctx(form, "Please describe your story idea (at least 3 characters)."), 400)
    try:
        comic = create_comic(req)
    except Exception as exc:  # noqa: BLE001
        log.exception("Comic generation crashed")
        return error_page(request, "We couldn't build your comic", "Something unexpected went wrong while creating the panels.",
                          500, f"{type(exc).__name__}: {exc}")
    return render(request, "comic_preview.html", {"comic": comic, "rows": layout_rows(len(comic.panels))})


@router.post("/generate-comic/json", response_model=Comic, response_model_exclude={"panels": {"__all__": {"image_path"}}})
def generate_comic_json(req: ComicRequest):
    try:
        return create_comic(req)
    except Exception as exc:  # noqa: BLE001
        log.exception("Comic generation crashed")
        raise HTTPException(status_code=500, detail=redact(f"{type(exc).__name__}: {exc}"))


@router.get("/comic/{comic_id}", response_class=HTMLResponse)
def view_comic(request: Request, comic_id: str):
    comic = get_comic(comic_id)
    if not comic:
        return error_page(request, "Comic not found", "That comic doesn't exist (or was deleted).", 404)
    return render(request, "comic_preview.html", {"comic": comic, "rows": layout_rows(len(comic.panels))})


@router.post("/export-pdf/{comic_id}", response_class=HTMLResponse)
def export_pdf_page(request: Request, comic_id: str):
    comic = get_comic(comic_id)
    if not comic:
        return error_page(request, "Comic not found", "That comic doesn't exist (or was deleted).", 404)
    try:
        export_comic_pdf(comic)
    except Exception as exc:  # noqa: BLE001
        log.exception("PDF export failed")
        return error_page(request, "PDF export failed", "The comic was created but the PDF could not be built.",
                          500, f"{type(exc).__name__}: {exc}")
    return render(request, "export_success.html", {"comic": comic})


@router.get("/download/{comic_id}")
def download_pdf(request: Request, comic_id: str):
    comic = get_comic(comic_id)
    if not comic:
        return error_page(request, "Comic not found", "That comic doesn't exist (or was deleted).", 404)
    try:
        path = export_comic_pdf(comic)
    except Exception as exc:  # noqa: BLE001
        log.exception("PDF export failed")
        return error_page(request, "PDF export failed", "The PDF could not be built.", 500, f"{type(exc).__name__}: {exc}")
    slug = re.sub(r"[^a-z0-9]+", "-", comic.title.lower()).strip("-")[:40] or "comic"
    return FileResponse(path, media_type="application/pdf", filename=f"{slug}.pdf")


# ---------------------------------------------------------------- diagnostics
@router.get("/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "mock_ai": s.mock_ai,
        "gemini_key_present": bool(s.gemini_api_key),
        "hf_token_present": bool(s.hf_token),
        "outline_model": s.gemini_outline_model,
        "story_model": s.gemini_story_model,
        "gemini_image_model": s.gemini_image_model,
        "hf_image_model": s.hf_image_model,
        "hf_provider": s.hf_provider,
        "image_backends": s.image_backends,
        "panels": s.comic_panels,
        "image_size": [s.image_width, s.image_height],
    }


@router.get("/dev/test-gemini")
def dev_test_gemini():
    """Sends one tiny request to Gemini and returns the exact result or error."""
    from app.services.gemini_core import generate_json

    s = get_settings()
    try:
        data, model = generate_json(s, s.gemini_outline_model, 'Reply with only this JSON: {"ok": true}')
        return {"ok": True, "model_used": model, "reply": data}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": redact(f"{type(exc).__name__}: {exc}")}, status_code=502)


@router.get("/dev/test-image")
def dev_test_image(prompt: str = "a small red fox in an enchanted forest, comic book style"):
    """Generates one image with the configured Hugging Face model (or a placeholder + warning header)."""
    import io

    s = get_settings()
    req = ComicRequest(story_prompt="test")
    img, warn = ImageBackend(s).generate(compose_prompt(prompt, req), 1, "Test image", prompt)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    headers = {"X-ComicCraft-Warning": (warn or "none").encode("ascii", "replace").decode()[:400]}
    return Response(buf.getvalue(), media_type="image/png", headers=headers)
