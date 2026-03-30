"""Global Forest Watch (GFW) integration for deforestation alerts.

Uses the GFW Data API to query Integrated Deforestation Alerts
for areas around registered climbing crags.

API docs: https://data-api.globalforestwatch.org/
How to get an API key: https://developer.openepi.io/how-tos/getting-started-using-global-forest-watch-data-api
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

GFW_QUERY_URL = "https://data-api.globalforestwatch.org/dataset/gfw_integrated_alerts/latest/query/json"


def _bbox_polygon(lat: float, lng: float, radius_km: float) -> dict:
    """Create a GeoJSON Polygon from a center point and radius in km."""
    km_per_deg_lat = 111.0
    km_per_deg_lng = 111.0 * math.cos(math.radians(lat))
    delta_lat = radius_km / km_per_deg_lat
    delta_lng = radius_km / km_per_deg_lng

    west = lng - delta_lng
    south = lat - delta_lat
    east = lng + delta_lng
    north = lat + delta_lat

    return {
        "type": "Polygon",
        "coordinates": [[
            [west, south],
            [east, south],
            [east, north],
            [west, north],
            [west, south],
        ]],
    }


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Calculate distance in km between two lat/lng points."""
    r = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


async def fetch_deforestation_for_crag(crag: Crag, days_back: int = 30) -> list[dict]:
    """Fetch recent deforestation alerts near a crag from GFW.

    Returns list of alert dicts with latitude, longitude, date, intensity, confidence.
    """
    if not settings.gfw_api_key:
        logger.warning("GFW API key not configured — skipping deforestation check for %s", crag.name)
        return []

    from datetime import timedelta

    since_date = (datetime.now(timezone.utc) - timedelta(days=days_back)).strftime("%Y-%m-%d")
    geometry = _bbox_polygon(crag.lat, crag.lng, crag.monitoring_radius_km)

    payload = {
        "sql": (
            "SELECT longitude, latitude, gfw_integrated_alerts__date, "
            "gfw_integrated_alerts__intensity, gfw_integrated_alerts__confidence "
            f"FROM results WHERE gfw_integrated_alerts__date >= '{since_date}'"
        ),
        "geometry": geometry,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            GFW_QUERY_URL,
            json=payload,
            headers={
                "x-api-key": settings.gfw_api_key,
                "Content-Type": "application/json",
            },
        )
        if response.status_code != 200:
            logger.error(
                "GFW API error for %s: %d %s",
                crag.name, response.status_code, response.text[:200],
            )
            return []

    data = response.json()
    alerts = data.get("data", [])
    logger.info("Found %d deforestation alerts near %s (last %d days)", len(alerts), crag.name, days_back)
    return alerts


def _severity_from_confidence(confidence: str) -> str:
    """Map GFW confidence to our severity levels."""
    if confidence == "high":
        return "high"
    elif confidence == "nominal":
        return "medium"
    return "low"


async def poll_all_crags(db: AsyncSession, days_back: int = 30) -> int:
    """Poll GFW for all crags and store new deforestation alerts. Returns count of new alerts."""
    result = await db.execute(select(Crag))
    crags = result.scalars().all()
    new_alerts = 0

    for crag in crags:
        alerts = await fetch_deforestation_for_crag(crag, days_back)
        for alert in alerts:
            try:
                alert_lat = float(alert.get("latitude", 0))
                alert_lng = float(alert.get("longitude", 0))
                distance = _haversine_km(crag.lat, crag.lng, alert_lat, alert_lng)

                alert_date_str = alert.get("gfw_integrated_alerts__date", "")
                detected_at = datetime.strptime(alert_date_str, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )

                confidence = alert.get("gfw_integrated_alerts__confidence", "low")

                sat_alert = SatelliteAlert(
                    crag_id=crag.id,
                    alert_type="deforestation",
                    source="GFW/integrated_alerts",
                    detected_at=detected_at,
                    severity=_severity_from_confidence(confidence),
                    lat=alert_lat,
                    lng=alert_lng,
                    confidence=confidence,
                    brightness=float(alert.get("gfw_integrated_alerts__intensity", 0) or 0),
                    distance_km=round(distance, 2),
                    data_json=json.dumps(alert),
                )
                db.add(sat_alert)
                new_alerts += 1
            except (ValueError, KeyError) as e:
                logger.warning("Failed to parse deforestation alert: %s — %s", alert, e)

    await db.commit()
    logger.info("Stored %d new deforestation alerts across %d crags", new_alerts, len(crags))
    return new_alerts
