import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType
from app.db.models.base import UUIDMixin, TimestampMixin


class ProcurementOrder(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "procurement_orders"

    po_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    supplier_name: Mapped[str] = mapped_column(String(100), nullable=False)
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_delivery: Mapped[date] = mapped_column(Date, nullable=False)
    delivery_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="IN_PRODUCTION", nullable=False)

    # Relationships
    delivery_location: Mapped["Location"] = relationship("Location")


class ProcurementRecommendation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "procurement_recommendations"

    recommendation_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    recommended_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    required_by_week: Mapped[str] = mapped_column(String(50), nullable=False)
    recommended_order_by_date: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    recommended_location: Mapped["Location"] = relationship("Location")
