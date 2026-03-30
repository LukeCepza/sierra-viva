"""Re-fetch historical fire data for updated/new crags (ids 3,4,5,6)."""

import asyncio
import json
import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.database import async_session
from app.models.crag import Crag
from app.models.satellite import SatelliteAlert
from app.services.firms import _haversine_km, _severity_from_confidence
from scripts.fetch_history import fetch_historical_for_crag

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    async with async_session() as db:
        # Clear old alerts for crags with updated coordinates
        for cid in [3, 4]:
            r = await db.execute(
                delete(SatelliteAlert).where(SatelliteAlert.crag_id == cid)
            )
            logger.info("Cleared alerts for crag %d", cid)
        await db.commit()

        # Fetch for updated + new crags
        result = await db.execute(select(Crag).where(Crag.id.in_([3, 4, 5, 6])))
        crags = result.scalars().all()

        total = 0
        for crag in crags:
            logger.info("Fetching %s (%.4f, %.4f, radius=%skm)...", crag.name, crag.lat, crag.lng, crag.monitoring_radius_km)
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
                        source="FIRMS/historical",
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
                    total += 1
                except (ValueError, KeyError):
                    pass

            await db.commit()
            logger.info("  %s: %d detections stored", crag.name, len(fires))

        logger.info("Done! Total new alerts: %d", total)


if __name__ == "__main__":
    asyncio.run(main())
