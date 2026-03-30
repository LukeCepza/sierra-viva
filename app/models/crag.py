from sqlalchemy import Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class Crag(Base, TimestampMixin):
    __tablename__ = "crags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    approach_notes: Mapped[str | None] = mapped_column(Text)
    access_status: Mapped[str] = mapped_column(
        String(50), default="open"
    )  # open, restricted, closed
    season: Mapped[str | None] = mapped_column(String(200))  # e.g. "Oct-Apr"
    monitoring_radius_km: Mapped[float] = mapped_column(Float, default=10.0)

    alerts = relationship("SatelliteAlert", back_populates="crag", lazy="selectin")

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lng, self.lat]},
            "properties": {
                "id": self.id,
                "name": self.name,
                "type": "crag",
                "description": self.description,
                "approach_notes": self.approach_notes,
                "access_status": self.access_status,
                "season": self.season,
                "monitoring_radius_km": self.monitoring_radius_km,
            },
        }
