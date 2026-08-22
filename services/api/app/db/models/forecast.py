import uuid
from datetime import date
from typing import Optional
from sqlalchemy import String, Integer, Date, Float, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType
from app.db.models.base import UUIDMixin, TimestampMixin


class DemandForecast(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "demand_forecasts"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    week: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="demand_forecasts")
    location: Mapped["Location"] = relationship("Location", back_populates="demand_forecasts")


class ImportReturnForecast(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "import_return_forecasts"

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    week: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    import_volume: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_empty_returns: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    location: Mapped["Location"] = relationship("Location")
