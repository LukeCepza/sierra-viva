from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Gym(Base, TimestampMixin):
    __tablename__ = "gyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    hours: Mapped[str | None] = mapped_column(String(500))
    wall_types: Mapped[str | None] = mapped_column(String(500))  # e.g. "boulder, lead, top-rope"
    website: Mapped[str | None] = mapped_column(String(500))
    membership_info: Mapped[str | None] = mapped_column(Text)

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lng, self.lat]},
            "properties": {
                "id": self.id,
                "name": self.name,
                "type": "gym",
                "hours": self.hours,
                "wall_types": self.wall_types,
                "website": self.website,
            },
        }
