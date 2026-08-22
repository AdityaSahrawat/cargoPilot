import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import (
    ContainerType,
    ContainerStatus,
    ContainerCondition,
    ContainerEventType,
    CommitmentType,
    CommitmentStatus,
)
from app.db.models.base import UUIDMixin, TimestampMixin


class Container(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "containers"

    container_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    owner_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    current_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    current_voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[ContainerStatus] = mapped_column(
        SQLEnum(ContainerStatus, native_enum=False),
        default=ContainerStatus.AVAILABLE,
        nullable=False,
    )
    condition: Mapped[ContainerCondition] = mapped_column(
        SQLEnum(ContainerCondition, native_enum=False),
        default=ContainerCondition.CARGO_WORTHY,
        nullable=False,
    )
    controlled_by_carrier: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    customs_hold: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_emergency_reserve: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    available_from: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=True
    )
    last_movement_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    owner_company: Mapped["Company"] = relationship("Company", back_populates="owned_containers")
    current_location: Mapped[Optional["Location"]] = relationship("Location", back_populates="containers_here")
    current_voyage: Mapped[Optional["Voyage"]] = relationship("Voyage", back_populates="containers")
    equipment_assignments: Mapped[List["EquipmentAssignment"]] = relationship(
        "EquipmentAssignment", back_populates="container"
    )
    events: Mapped[List["ContainerEvent"]] = relationship(
        "ContainerEvent", back_populates="container", order_by="ContainerEvent.timestamp"
    )
    commitments: Mapped[List["ContainerCommitment"]] = relationship(
        "ContainerCommitment", back_populates="container"
    )
    expected_movements: Mapped[List["ExpectedContainerMovement"]] = relationship(
        "ExpectedContainerMovement", back_populates="container"
    )


class ContainerCommitment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "container_commitments"

    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
    )
    commitment_type: Mapped[CommitmentType] = mapped_column(
        SQLEnum(CommitmentType, native_enum=False),
        nullable=False,
    )
    reference_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    required_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    required_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CommitmentStatus] = mapped_column(
        SQLEnum(CommitmentStatus, native_enum=False),
        default=CommitmentStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    container: Mapped["Container"] = relationship("Container", back_populates="commitments")
    required_location: Mapped[Optional["Location"]] = relationship("Location")


class ExpectedContainerMovement(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "expected_container_movements"

    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
    )
    from_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="SET NULL"),
        nullable=True,
    )
    planned_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expected_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="EXPECTED", nullable=False)

    # Relationships
    container: Mapped["Container"] = relationship("Container", back_populates="expected_movements")
    from_location: Mapped[Optional["Location"]] = relationship("Location", foreign_keys=[from_location_id])
    to_location: Mapped[Optional["Location"]] = relationship("Location", foreign_keys=[to_location_id])
    voyage: Mapped[Optional["Voyage"]] = relationship("Voyage")


class ContainerEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "container_events"

    container_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("containers.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[ContainerEventType] = mapped_column(
        SQLEnum(ContainerEventType, native_enum=False),
        nullable=False,
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyages.id", ondelete="SET NULL"),
        nullable=True,
    )
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

    # Relationships
    container: Mapped["Container"] = relationship("Container", back_populates="events")
    location: Mapped[Optional["Location"]] = relationship("Location", back_populates="container_events")
    voyage: Mapped[Optional["Voyage"]] = relationship("Voyage", back_populates="container_events")
