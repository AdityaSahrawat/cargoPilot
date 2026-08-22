import uuid
from typing import Optional
from sqlalchemy import String, Integer, Float, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType
from app.db.models.base import UUIDMixin, TimestampMixin


class RepositioningOption(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "repositioning_options"

    option_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    week: Mapped[str] = mapped_column(String(20), nullable=False)
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    max_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    arrival_week: Mapped[str] = mapped_column(String(20), nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    from_location: Mapped["Location"] = relationship("Location", foreign_keys=[from_location_id])
    to_location: Mapped["Location"] = relationship("Location", foreign_keys=[to_location_id])


class RepositioningCommitment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "repositioning_commitments"

    commitment_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    from_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_week: Mapped[str] = mapped_column(String(20), nullable=False)
    arrival_week: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="BOOKED", nullable=False)
    cost_per_unit: Mapped[float] = mapped_column(Float, nullable=False)

    # Relationships
    from_location: Mapped["Location"] = relationship("Location", foreign_keys=[from_location_id])
    to_location: Mapped["Location"] = relationship("Location", foreign_keys=[to_location_id])
