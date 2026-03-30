import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api import alerts, cafes, crags, gyms
from app.config import settings

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(
    title="SierraViva",
    description="Open platform that protects and connects the Monterrey climbing community.",
    version="0.1.0",
)

# Static files and templates
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# API routes
app.include_router(crags.router)
app.include_router(gyms.router)
app.include_router(cafes.router)
app.include_router(alerts.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main map page."""
    return templates.TemplateResponse(request, "map.html")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
