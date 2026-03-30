from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.crag import Crag

router = APIRouter(prefix="/api/crags", tags=["crags"])


@router.get("")
async def list_crags(db: AsyncSession = Depends(get_db)):
    """Return all crags as a GeoJSON FeatureCollection."""
    result = await db.execute(select(Crag))
    crags = result.scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [c.to_geojson_feature() for c in crags],
    }


@router.get("/{crag_id}")
async def get_crag(crag_id: int, db: AsyncSession = Depends(get_db)):
    """Return a single crag as a GeoJSON Feature."""
    result = await db.execute(select(Crag).where(Crag.id == crag_id))
    crag = result.scalar_one_or_none()
    if not crag:
        return {"error": "Crag not found"}, 404
    return crag.to_geojson_feature()
