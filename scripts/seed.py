"""Seed the database with initial Monterrey climbing locations."""

import asyncio
import json
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session, engine
from app.models import Base, Cafe, Crag, Gym


async def seed():
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    data_path = Path(__file__).parent.parent / "seed" / "data.json"
    with open(data_path) as f:
        data = json.load(f)

    async with async_session() as db:
        # Check if already seeded
        result = await db.execute(text("SELECT count(*) FROM crags"))
        count = result.scalar()
        if count > 0:
            print(f"Database already has {count} crags — skipping seed.")
            return

        for crag_data in data["crags"]:
            db.add(Crag(**crag_data))
        print(f"  Added {len(data['crags'])} crags")

        for gym_data in data["gyms"]:
            db.add(Gym(**gym_data))
        print(f"  Added {len(data['gyms'])} gyms")

        for cafe_data in data["cafes"]:
            db.add(Cafe(**cafe_data))
        print(f"  Added {len(data['cafes'])} cafes")

        await db.commit()
        print("Seed complete!")


if __name__ == "__main__":
    asyncio.run(seed())
