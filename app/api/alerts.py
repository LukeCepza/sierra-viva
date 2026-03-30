from fastapi import APIRouter, Depends
from sqlalchemy import select
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
