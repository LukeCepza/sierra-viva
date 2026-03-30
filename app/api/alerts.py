from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.satellite import SatelliteAlert

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
async def list_alerts(limit: int = 100, db: AsyncSession = Depends(get_db)):
    """Return recent satellite alerts as a GeoJSON FeatureCollection."""
    result = await db.execute(
        select(SatelliteAlert).order_by(SatelliteAlert.detected_at.desc()).limit(limit)
    )
    alerts = result.scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [a.to_geojson_feature() for a in alerts],
    }


@router.get("/crag/{crag_id}")
async def alerts_for_crag(crag_id: int, limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Return satellite alerts for a specific crag."""
    result = await db.execute(
        select(SatelliteAlert)
        .where(SatelliteAlert.crag_id == crag_id)
        .order_by(SatelliteAlert.detected_at.desc())
        .limit(limit)
    )
    alerts = result.scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [a.to_geojson_feature() for a in alerts],
    }


@router.post("/poll/firms")
async def trigger_firms_poll(db: AsyncSession = Depends(get_db)):
    """Manually trigger a NASA FIRMS fire detection poll for all crags."""
    from app.services.firms import poll_all_crags

    count = await poll_all_crags(db)
    return {"status": "ok", "new_alerts": count}


@router.post("/poll/gfw")
async def trigger_gfw_poll(db: AsyncSession = Depends(get_db)):
    """Manually trigger a GFW deforestation alert poll for all crags."""
    from app.services.gfw import poll_all_crags

    count = await poll_all_crags(db)
    return {"status": "ok", "new_alerts": count}


@router.get("/stats")
async def alert_stats(db: AsyncSession = Depends(get_db)):
    """Return alert counts by type."""
    result = await db.execute(
        select(SatelliteAlert.alert_type, func.count(SatelliteAlert.id)).group_by(
            SatelliteAlert.alert_type
        )
    )
    stats = {row[0]: row[1] for row in result.all()}
    total = sum(stats.values())
    return {"total": total, "by_type": stats}
