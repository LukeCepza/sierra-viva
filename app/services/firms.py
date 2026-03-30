"""NASA FIRMS (Fire Information for Resource Management System) integration.

Polls near real-time fire/hotspot data from MODIS and VIIRS satellites
for areas around registered climbing crags.

API docs: https://firms.modaps.eosdis.nasa.gov/api/
"""

import json
import logging
import math
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.crag import Crag
from app.models.satellite import SatelliteAlert

logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
# VIIRS_SNPP has good coverage and resolution
FIRMS_SOURCE = "VIIRS_SNPP_NRT"


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    r = 6371  # Earth radius in km
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


def _parse_firms_csv(csv_text: str) -> list[dict]:
    """Parse FIRMS CSV response into list of fire detections."""
    lines = csv_text.strip().split("\n")
    if len(lines) < 2:
        return []
    headers = lines[0].split(",")
    results = []
    for line in lines[1:]:
        values = line.split(",")
        if len(values) == len(headers):
            results.append(dict(zip(headers, values)))
    return results


async def fetch_fires_for_crag(crag: Crag) -> list[dict]:
    """Fetch recent fire detections near a crag from NASA FIRMS.

    Uses the area endpoint with a bounding box around the crag's coordinates.
    """
    if not settings.firms_api_key or settings.firms_api_key == "your_firms_api_key_here":
        logger.warning("FIRMS API key not configured — skipping fire check for %s", crag.name)
        return []

    # Build bounding box: approximate degrees from km at this latitude
    km_per_deg_lat = 111.0
    km_per_deg_lng = 111.0 * math.cos(math.radians(crag.lat))
    delta_lat = crag.monitoring_radius_km / km_per_deg_lat
    delta_lng = crag.monitoring_radius_km / km_per_deg_lng

    west = crag.lng - delta_lng
    south = crag.lat - delta_lat
    east = crag.lng + delta_lng
    north = crag.lat + delta_lat
    area = f"{west},{south},{east},{north}"

    url = f"{FIRMS_BASE_URL}/{settings.firms_api_key}/{FIRMS_SOURCE}/{area}/{settings.firms_days_back}"

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url)
        if response.status_code != 200:
            logger.error("FIRMS API error for %s: %d %s", crag.name, response.status_code, response.text[:200])
            return []

    fires = _parse_firms_csv(response.text)
    logger.info("Found %d fire detections near %s", len(fires), crag.name)
    return fires


def _severity_from_confidence(confidence: str) -> str:
    """Map FIRMS confidence to our severity levels."""
    if confidence in ("high", "h"):
        return "high"
    elif confidence in ("nominal", "n"):
        return "medium"
    return "low"


async def poll_all_crags(db: AsyncSession) -> int:
    """Poll NASA FIRMS for all crags and store new alerts. Returns count of new alerts."""
    result = await db.execute(select(Crag))
    crags = result.scalars().all()
    new_alerts = 0

    for crag in crags:
        fires = await fetch_fires_for_crag(crag)
        for fire in fires:
            try:
                fire_lat = float(fire.get("latitude", 0))
                fire_lng = float(fire.get("longitude", 0))
                distance = _haversine_km(crag.lat, crag.lng, fire_lat, fire_lng)

                # Parse the acquisition date
                acq_date = fire.get("acq_date", "")
                acq_time = fire.get("acq_time", "0000")
                detected_at = datetime.strptime(
                    f"{acq_date} {acq_time}", "%Y-%m-%d %H%M"
                ).replace(tzinfo=timezone.utc)

                confidence = fire.get("confidence", "low").lower()

                alert = SatelliteAlert(
                    crag_id=crag.id,
                    alert_type="fire",
                    source=f"FIRMS/{FIRMS_SOURCE}",
                    detected_at=detected_at,
                    severity=_severity_from_confidence(confidence),
                    lat=fire_lat,
                    lng=fire_lng,
                    confidence=confidence,
                    brightness=float(fire.get("bright_ti4", 0) or 0),
                    distance_km=round(distance, 2),
                    data_json=json.dumps(fire),
                )
                db.add(alert)
                new_alerts += 1
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse fire detection: %s — %s", fire, e)

    await db.commit()
    logger.info("Stored %d new fire alerts across %d crags", new_alerts, len(crags))
    return new_alerts
