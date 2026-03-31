from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.crag import Crag
from app.models.vegetation import VegetationAnalysis
from app.services.sentinel import (
    search_sentinel2_products,
    process_vegetation_index,
    get_quicklook,
)

router = APIRouter(prefix="/api/vegetation", tags=["vegetation"])


@router.get("/search/{crag_id}")
async def search_imagery(
    crag_id: int,
    start_date: str,
    end_date: str,
    max_cloud: int = 30,
    db: AsyncSession = Depends(get_db),
):
    """Search for available Sentinel-2 imagery near a crag."""
    result = await db.execute(select(Crag).where(Crag.id == crag_id))
    crag = result.scalar_one_or_none()
    if not crag:
        return {"error": "Crag not found"}

    products = await search_sentinel2_products(
        crag.lat, crag.lng, crag.monitoring_radius_km,
        start_date, end_date, max_cloud,
    )
    return {"crag": crag.name, "products": products}


@router.post("/analyze/{crag_id}")
async def analyze_vegetation(
    crag_id: int,
    target_date: str,
    index_type: str = "ndvi",
    db: AsyncSession = Depends(get_db),
):
    """Compute NDVI or NBR for a crag and store the result."""
    result = await db.execute(select(Crag).where(Crag.id == crag_id))
    crag = result.scalar_one_or_none()
    if not crag:
        return {"error": "Crag not found"}

    analysis = await process_vegetation_index(
        crag.id, crag.lat, crag.lng, crag.monitoring_radius_km,
        target_date, index_type,
    )
    if not analysis:
        return {"error": "No suitable Sentinel-2 imagery found", "crag": crag.name}

    if analysis.get("status") == "error":
        return analysis

    # Store in database
    image_date = datetime.fromisoformat(
        analysis["product"]["date"].replace("Z", "+00:00")
    )
    record = VegetationAnalysis(
        crag_id=crag_id,
        analysis_type=index_type,
        image_date=image_date,
        source=analysis["product"]["name"],
        mean_value=analysis["stats"]["mean"],
        min_value=analysis["stats"]["min"],
        max_value=analysis["stats"]["max"],
        std_value=analysis["stats"]["std"],
        pixel_count=analysis["stats"]["pixel_count"],
        cloud_cover_pct=analysis["product"]["cloud_cover"],
    )
    db.add(record)
    await db.commit()

    return analysis


# Keep the old endpoint as an alias
@router.post("/ndvi/{crag_id}")
async def compute_crag_ndvi(
    crag_id: int,
    target_date: str,
    db: AsyncSession = Depends(get_db),
):
    """Compute NDVI for a crag (alias for /analyze with index_type=ndvi)."""
    return await analyze_vegetation(crag_id, target_date, "ndvi", db)


@router.get("/quicklook/{product_id}")
async def quicklook_image(product_id: str):
    """Proxy quicklook thumbnail from CDSE for a Sentinel-2 product."""
    data = await get_quicklook(product_id)
    if not data:
        return Response(status_code=404, content="Quicklook not available")
    return Response(content=data, media_type="image/jpeg")


@router.get("/history/{crag_id}")
async def vegetation_history(
    crag_id: int,
    analysis_type: str = "ndvi",
    db: AsyncSession = Depends(get_db),
):
    """Get vegetation analysis history for a crag."""
    result = await db.execute(
        select(VegetationAnalysis)
        .where(VegetationAnalysis.crag_id == crag_id)
        .where(VegetationAnalysis.analysis_type == analysis_type)
        .order_by(VegetationAnalysis.image_date.desc())
        .limit(50)
    )
    analyses = result.scalars().all()

    return {
        "crag_id": crag_id,
        "analysis_type": analysis_type,
        "data": [
            {
                "date": a.image_date.isoformat(),
                "mean": a.mean_value,
                "min": a.min_value,
                "max": a.max_value,
                "std": a.std_value,
                "pixels": a.pixel_count,
                "cloud_pct": a.cloud_cover_pct,
            }
            for a in analyses
        ],
    }
