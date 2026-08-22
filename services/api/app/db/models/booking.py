import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Integer, Boolean, String, DateTime, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType, BookingPriority, BookingStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class Booking(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "bookings"

    customer_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    carrier_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    origin_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    destination_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    requested_pickup_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    required_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    requested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    empty_pickup_open_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    gate_cutoff_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="SET NULL"),
        nullable=True,
    )
    priority: Mapped[Optional[BookingPriority]] = mapped_column(
        SQLEnum(BookingPriority, native_enum=False),
        default=BookingPriority.NORMAL,
        nullable=True,
    )
    operational_criticality: Mapped[Optional[BookingPriority]] = mapped_column(
        SQLEnum(BookingPriority, native_enum=False),
        default=BookingPriority.NORMAL,
        nullable=True,
    )
    allowed_equipment_sources: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    alternative_voyage_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[BookingStatus] = mapped_column(
        SQLEnum(BookingStatus, native_enum=False),
        default=BookingStatus.PENDING,
        nullable=False,
    )

    # Relationships
    customer_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[customer_company_id], back_populates="customer_bookings"
    )
    carrier_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[carrier_company_id], back_populates="carrier_bookings"
    )
    origin_location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[origin_location_id], back_populates="origin_bookings"
    )
    destination_location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[destination_location_id], back_populates="destination_bookings"
    )
    voyage: Mapped[Optional["Voyage"]] = relationship("Voyage", back_populates="bookings")
    equipment_assignments: Mapped[List["EquipmentAssignment"]] = relationship(
        "EquipmentAssignment", back_populates="booking"
    )


class EquipmentAssignment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "equipment_assignments"

    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="RESTRICT"),
        nullable=False,
    )
    booking_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bookings.id", ondelete="CASCADE"),
        nullable=False,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    container: Mapped["Container"] = relationship("Container", back_populates="equipment_assignments")
    booking: Mapped["Booking"] = relationship("Booking", back_populates="equipment_assignments")
