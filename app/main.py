import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select

from app.api import alerts, cafes, crags, gyms, vegetation
from app.config import settings
from app.database import get_db, async_session
from app.models.crag import Crag
from app.models.satellite import SatelliteAlert
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=logging.INFO)

BASE_DIR = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(
    title="SierraViva",
    description="Open platform that protects and connects the Monterrey climbing community.",
    version="0.3.0",
    lifespan=lifespan,
)

# Static files and templates
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# API routes
app.include_router(crags.router)
app.include_router(gyms.router)
app.include_router(cafes.router)
app.include_router(alerts.router)
app.include_router(vegetation.router)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the main map page."""
    return templates.TemplateResponse(request, "map.html")


@app.get("/crag/{crag_id}", response_class=HTMLResponse)
async def crag_dashboard(request: Request, crag_id: int):
    """Render the environmental dashboard for a specific crag."""
    async with async_session() as db:
        result = await db.execute(select(Crag).where(Crag.id == crag_id))
        crag = result.scalar_one_or_none()
        if not crag:
            return HTMLResponse("<h1>Crag not found</h1>", status_code=404)

        alerts_result = await db.execute(
            select(SatelliteAlert)
            .where(SatelliteAlert.crag_id == crag_id)
            .order_by(SatelliteAlert.detected_at.desc())
            .limit(1000)
        )
        crag_alerts = alerts_result.scalars().all()

        fire_alerts = [a for a in crag_alerts if a.alert_type == "fire"]
        deforestation_alerts = [a for a in crag_alerts if a.alert_type == "deforestation"]

    return templates.TemplateResponse(request, "dashboard.html", {
        "crag": crag,
        "fire_alerts": fire_alerts,
        "deforestation_alerts": deforestation_alerts,
        "total_alerts": len(crag_alerts),
    })


@app.get("/crags", response_class=HTMLResponse)
async def crags_listing(request: Request):
    """Render the crags listing page with alert counts."""
    async with async_session() as db:
        result = await db.execute(select(Crag).order_by(Crag.name))
        all_crags = result.scalars().all()

        # Get alert counts per crag
        counts_result = await db.execute(
            select(SatelliteAlert.crag_id, func.count(SatelliteAlert.id))
            .group_by(SatelliteAlert.crag_id)
        )
        alert_counts = dict(counts_result.all())

    crags_data = [
        {"crag": c, "alert_count": alert_counts.get(c.id, 0)}
        for c in all_crags
    ]
    return templates.TemplateResponse(request, "crags.html", {"crags": crags_data})


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host=settings.app_host, port=settings.app_port, reload=True)
