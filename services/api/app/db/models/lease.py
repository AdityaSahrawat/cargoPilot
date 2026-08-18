import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, Numeric, DateTime, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType
from app.db.models.base import UUIDMixin, TimestampMixin


class Lease(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "leases"

    lessor_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    lessee_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pickup_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    return_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    cost_per_unit: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    # Relationships
    lessor_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[lessor_company_id], back_populates="lessor_leases"
    )
    lessee_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[lessee_company_id], back_populates="lessee_leases"
    )
    pickup_location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[pickup_location_id], back_populates="pickup_leases"
    )
    return_location: Mapped[Optional["Location"]] = relationship(
        "Location", foreign_keys=[return_location_id], back_populates="return_leases"
    )
    optimization_leases: Mapped[List["OptimizationLease"]] = relationship(
        "OptimizationLease", back_populates="lease"
    )
