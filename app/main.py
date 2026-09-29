from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import EXPORTS_DIR, PANELS_DIR, STATIC_DIR, get_settings, redact
from app.routes import error_page, router

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(name)s: %(message)s")
log = logging.getLogger("comiccraft")

# StaticFiles crashes at startup if a folder is missing, so create them first.
for d in (STATIC_DIR, PANELS_DIR, EXPORTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    s = get_settings()
    log.info("ComicCraft started | mock=%s | gemini_key=%s | hf_token=%s | panels=%d | outline=%s | story=%s | image=%s",
             s.mock_ai, "set" if s.gemini_api_key else "MISSING", "set" if s.hf_token else "MISSING",
             s.comic_panels, s.gemini_outline_model, s.gemini_story_model, s.hf_image_model)
    log.info("Image pipeline=%s | workers=%d", s.image_backends, s.image_workers)
    yield


app = FastAPI(title="ComicCraft", version="2.0.0", description="AI comic story creator", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(router)


def _wants_json(request: Request) -> bool:
    return request.url.path.endswith("/json") or request.url.path.startswith(("/docs", "/openapi")) \
        or "application/json" in request.headers.get("accept", "")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if _wants_json(request):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    title = "Page not found" if exc.status_code == 404 else "Something went wrong"
    return error_page(request, title, str(exc.detail), exc.status_code)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    if _wants_json(request):
        return JSONResponse({"detail": redact(f"{type(exc).__name__}: {exc}")}, status_code=500)
    return error_page(request, "Unexpected error", "Something broke on our side. Details are in the terminal.",
                      500, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    import uvicorn

    cfg = get_settings()
    uvicorn.run("app.main:app", host=cfg.app_host, port=cfg.app_port, reload=True)
