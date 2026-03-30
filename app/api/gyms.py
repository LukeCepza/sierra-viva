from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.gym import Gym

router = APIRouter(prefix="/api/gyms", tags=["gyms"])


@router.get("")
async def list_gyms(db: AsyncSession = Depends(get_db)):
    """Return all gyms as a GeoJSON FeatureCollection."""
    result = await db.execute(select(Gym))
    gyms = result.scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [g.to_geojson_feature() for g in gyms],
    }
