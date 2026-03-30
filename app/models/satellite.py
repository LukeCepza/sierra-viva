from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin


class SatelliteAlert(Base, TimestampMixin):
    __tablename__ = "satellite_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crag_id: Mapped[int] = mapped_column(ForeignKey("crags.id"), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(50), nullable=False)  # fire, deforestation, land_change
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # FIRMS, GFW, Landsat
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), default="low")  # low, medium, high
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lng: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(20))  # FIRMS confidence level
    brightness: Mapped[float | None] = mapped_column(Float)  # FIRMS brightness value
    distance_km: Mapped[float | None] = mapped_column(Float)  # distance from crag center
    data_json: Mapped[str | None] = mapped_column(Text)  # raw response data

    crag = relationship("Crag", back_populates="alerts")

    def to_geojson_feature(self) -> dict:
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [self.lng, self.lat]},
            "properties": {
                "id": self.id,
                "type": "fire_alert",
                "crag_id": self.crag_id,
                "alert_type": self.alert_type,
                "source": self.source,
                "detected_at": self.detected_at.isoformat(),
                "severity": self.severity,
                "confidence": self.confidence,
                "brightness": self.brightness,
                "distance_km": self.distance_km,
            },
        }
