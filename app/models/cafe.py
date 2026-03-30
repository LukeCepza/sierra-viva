from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Cafe(Base, TimestampMixin):
    __tablename__ = "cafes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    hours: Mapped[str | None] = mapped_column(String(500))
    brew_methods: Mapped[str | None] = mapped_column(String(500))  # e.g. "espresso, pour-over, cold brew"
    specialty: Mapped[bool] = mapped_column(Boolean, default=False)
    near_crag_id: Mapped[int | None] = mapped_column(ForeignKey("crags.id"), nullable=True)

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lng, self.lat]},
            "properties": {
                "id": self.id,
                "name": self.name,
                "type": "cafe",
                "hours": self.hours,
                "brew_methods": self.brew_methods,
                "specialty": self.specialty,
                "near_crag_id": self.near_crag_id,
            },
        }
