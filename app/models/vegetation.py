from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class VegetationAnalysis(Base, TimestampMixin):
    """Stores NDVI/NBR vegetation analysis results per crag over time."""

    __tablename__ = "vegetation_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crag_id: Mapped[int] = mapped_column(ForeignKey("crags.id"), nullable=False)
    analysis_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ndvi, nbr
    image_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(100), default="Sentinel-2/L2A")

    # Aggregate stats for the monitoring zone
    mean_value: Mapped[float] = mapped_column(Float, nullable=False)
    min_value: Mapped[float] = mapped_column(Float, nullable=False)
    max_value: Mapped[float] = mapped_column(Float, nullable=False)
    std_value: Mapped[float] = mapped_column(Float, nullable=False)
    pixel_count: Mapped[int] = mapped_column(Integer, nullable=False)
    cloud_cover_pct: Mapped[float | None] = mapped_column(Float)

    # Optional: path to generated image
    image_path: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
