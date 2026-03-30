"""Background scheduler for periodic satellite data polling."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()


async def poll_firms():
    """Poll NASA FIRMS for fire alerts near all crags."""
    from app.services.firms import poll_all_crags

    logger.info("Scheduled FIRMS poll starting...")
    async with async_session() as db:
        count = await poll_all_crags(db)
        logger.info("FIRMS poll complete: %d new alerts", count)


async def poll_gfw():
    """Poll Global Forest Watch for deforestation alerts near all crags."""
    from app.services.gfw import poll_all_crags

    logger.info("Scheduled GFW poll starting...")
    async with async_session() as db:
        count = await poll_all_crags(db, days_back=settings.gfw_days_back)
        logger.info("GFW poll complete: %d new alerts", count)


def start_scheduler():
    """Start the background polling scheduler."""
    if settings.firms_api_key and settings.firms_api_key != "your_firms_api_key_here":
        scheduler.add_job(
            poll_firms,
            "interval",
            hours=settings.firms_poll_interval_hours,
            id="firms_poll",
            name="NASA FIRMS fire detection poll",
        )
        logger.info("FIRMS polling scheduled every %d hours", settings.firms_poll_interval_hours)
    else:
        logger.warning("FIRMS API key not configured — fire polling disabled")

    if settings.gfw_api_key:
        scheduler.add_job(
            poll_gfw,
            "interval",
            hours=settings.gfw_poll_interval_hours,
            id="gfw_poll",
            name="GFW deforestation alerts poll",
        )
        logger.info("GFW polling scheduled every %d hours", settings.gfw_poll_interval_hours)
    else:
        logger.warning("GFW API key not configured — deforestation polling disabled")

    scheduler.start()
    logger.info("Scheduler started")


def stop_scheduler():
    """Stop the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
