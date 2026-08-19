import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import String, DateTime, Enum as SQLEnum, ForeignKey, JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType, ContainerStatus, ContainerCondition, ContainerEventType
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
    available_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
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
