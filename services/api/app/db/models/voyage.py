import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, DateTime, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.ext.hybrid import hybrid_property
from app.db.database import Base
from app.db.enums import VoyageStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class Voyage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "voyages"

    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vessel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vessels.id", ondelete="RESTRICT"),
        nullable=False,
    )
    voyage_number: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[VoyageStatus] = mapped_column(
        SQLEnum(VoyageStatus, native_enum=False),
        default=VoyageStatus.SCHEDULED,
        nullable=False,
    )

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="voyages")
    vessel: Mapped["Vessel"] = relationship("Vessel", back_populates="voyages")
    port_calls: Mapped[List["VoyagePortCall"]] = relationship(
        "VoyagePortCall", back_populates="voyage", cascade="all, delete-orphan", order_by="VoyagePortCall.sequence"
    )
    legs: Mapped[List["VoyageLeg"]] = relationship(
        "VoyageLeg", back_populates="voyage", cascade="all, delete-orphan"
    )
    containers: Mapped[List["Container"]] = relationship("Container", back_populates="current_voyage")
    bookings: Mapped[List["Booking"]] = relationship("Booking", back_populates="voyage")
    container_events: Mapped[List["ContainerEvent"]] = relationship("ContainerEvent", back_populates="voyage")


class VoyagePortCall(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "voyage_port_calls"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="CASCADE"),
        nullable=False,
    )
    port_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    departure_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    voyage: Mapped["Voyage"] = relationship("Voyage", back_populates="port_calls")
    port: Mapped["Location"] = relationship("Location", back_populates="port_calls")
    from_legs: Mapped[List["VoyageLeg"]] = relationship(
        "VoyageLeg", foreign_keys="[VoyageLeg.from_port_call_id]", back_populates="from_port_call"
    )
    to_legs: Mapped[List["VoyageLeg"]] = relationship(
        "VoyageLeg", foreign_keys="[VoyageLeg.to_port_call_id]", back_populates="to_port_call"
    )


class VoyageLeg(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "voyage_legs"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_port_call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyage_port_calls.id", ondelete="RESTRICT"),
        nullable=False,
    )
    to_port_call_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyage_port_calls.id", ondelete="RESTRICT"),
        nullable=False,
    )
    total_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    booked_capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    voyage: Mapped["Voyage"] = relationship("Voyage", back_populates="legs")
    from_port_call: Mapped["VoyagePortCall"] = relationship(
        "VoyagePortCall", foreign_keys=[from_port_call_id], back_populates="from_legs"
    )
    to_port_call: Mapped["VoyagePortCall"] = relationship(
        "VoyagePortCall", foreign_keys=[to_port_call_id], back_populates="to_legs"
    )
    optimization_repositions: Mapped[List["OptimizationReposition"]] = relationship(
        "OptimizationReposition", back_populates="voyage_leg"
    )

    @hybrid_property
    def available_capacity(self) -> int:
        return self.total_capacity - self.booked_capacity
