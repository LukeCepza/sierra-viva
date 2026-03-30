from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.cafe import Cafe

router = APIRouter(prefix="/api/cafes", tags=["cafes"])


@router.get("")
async def list_cafes(db: AsyncSession = Depends(get_db)):
    """Return all cafes as a GeoJSON FeatureCollection."""
    result = await db.execute(select(Cafe))
    cafes = result.scalars().all()
    return {
        "type": "FeatureCollection",
        "features": [c.to_geojson_feature() for c in cafes],
    }
