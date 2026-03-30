"""Fetch 2 years of historical fire data from NASA FIRMS for all crags.

Uses VIIRS_SNPP_SP (science/archive, up to 2025-12-31) and
VIIRS_SNPP_NRT (near real-time, 2026-01-01 to present).

The API allows max 5 days per request, so we batch in 5-day windows.
Rate limit: 5000 requests per 10 minutes — we add a small delay.
"""

import asyncio
import json
import logging
import math
from datetime import date, datetime, timedelta, timezone

import httpx
from sqlalchemy import select, text

from app.config import settings
from app.database import async_session, engine
from app.models import Base
from app.models.crag import Crag
from app.models.satellite import SatelliteAlert
from app.services.firms import _haversine_km, _parse_firms_csv, _severity_from_confidence

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FIRMS_BASE_URL = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# Historical sources and their date ranges
SOURCES = [
    ("VIIRS_SNPP_SP", date(2024, 3, 30), date(2025, 12, 31)),  # Archive
    ("VIIRS_SNPP_NRT", date(2026, 1, 1), date.today()),          # Near real-time
]


def _bbox_area(lat: float, lng: float, radius_km: float) -> str:
    """Create FIRMS area string (west,south,east,north) from center + radius."""
    km_per_deg_lat = 111.0
    km_per_deg_lng = 111.0 * math.cos(math.radians(lat))
    delta_lat = radius_km / km_per_deg_lat
    delta_lng = radius_km / km_per_deg_lng
    return f"{lng - delta_lng},{lat - delta_lat},{lng + delta_lng},{lat + delta_lat}"


async def fetch_historical_for_crag(crag: Crag) -> list[dict]:
    """Fetch all historical fire data for a crag across all sources."""
    all_fires = []
    area = _bbox_area(crag.lat, crag.lng, crag.monitoring_radius_km)

    for source, start_date, end_date in SOURCES:
        current = start_date
        while current <= end_date:
            days_remaining = (end_date - current).days + 1
            day_range = min(5, days_remaining)
            date_str = current.strftime("%Y-%m-%d")

            url = f"{FIRMS_BASE_URL}/{settings.firms_api_key}/{source}/{area}/{day_range}/{date_str}"

            for attempt in range(3):
                try:
                    async with httpx.AsyncClient(timeout=30) as client:
                        response = await client.get(url)
                    if response.status_code == 200:
                        fires = _parse_firms_csv(response.text)
                        if fires:
                            all_fires.extend(fires)
                            logger.info(
                                "  %s %s +%dd: %d detections",
                                crag.name, date_str, day_range, len(fires),
                            )
                        break
                    else:
                        logger.warning(
                            "  %s %s: HTTP %d", crag.name, date_str, response.status_code
                        )
                        break
                except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ConnectError) as e:
                    if attempt < 2:
                        logger.warning("  %s %s: %s — retrying in 5s...", crag.name, date_str, type(e).__name__)
                        await asyncio.sleep(5)
                    else:
                        logger.error("  %s %s: failed after 3 attempts", crag.name, date_str)

            current += timedelta(days=day_range)
            # Delay between requests to avoid rate limiting
            await asyncio.sleep(1)

    logger.info("%s: total %d fire detections over 2 years", crag.name, len(all_fires))
    return all_fires


async def main():
    api_key = settings.firms_api_key
    if not api_key or api_key == "your_firms_api_key_here":
        logger.error("FIRMS API key not configured in .env")
        return

    async with async_session() as db:
        # Check current alert count
        result = await db.execute(text("SELECT count(*) FROM satellite_alerts"))
        existing = result.scalar()
        logger.info("Existing alerts in DB: %d", existing)

        # Get all crags
        result = await db.execute(select(Crag))
        crags = result.scalars().all()
        logger.info("Fetching 2 years of fire history for %d crags...", len(crags))

        total_new = 0
        for crag in crags:
            logger.info("Processing %s...", crag.name)
            fires = await fetch_historical_for_crag(crag)

            for fire in fires:
                try:
                    fire_lat = float(fire.get("latitude", 0))
                    fire_lng = float(fire.get("longitude", 0))
                    distance = _haversine_km(crag.lat, crag.lng, fire_lat, fire_lng)

                    acq_date = fire.get("acq_date", "")
                    acq_time = fire.get("acq_time", "0000")
                    detected_at = datetime.strptime(
                        f"{acq_date} {acq_time}", "%Y-%m-%d %H%M"
                    ).replace(tzinfo=timezone.utc)

                    confidence = fire.get("confidence", "low").lower()

                    alert = SatelliteAlert(
                        crag_id=crag.id,
                        alert_type="fire",
                        source=f"FIRMS/historical",
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
                    total_new += 1
                except (ValueError, KeyError) as e:
                    logger.warning("Failed to parse: %s", e)

            # Commit per crag to avoid huge transactions
            await db.commit()
            logger.info("Committed %s data", crag.name)

        logger.info("Done! Total new historical alerts: %d", total_new)


if __name__ == "__main__":
    asyncio.run(main())
