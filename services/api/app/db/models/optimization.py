import uuid
from datetime import date, datetime
from typing import Optional, List
from sqlalchemy import Integer, Date, DateTime, Numeric, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ContainerType, OptimizationStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class OptimizationRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_runs"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_week: Mapped[date] = mapped_column(Date, nullable=False)
    horizon_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[OptimizationStatus] = mapped_column(
        SQLEnum(OptimizationStatus, native_enum=False),
        default=OptimizationStatus.PENDING,
        nullable=False,
    )
    objective_value: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="optimization_runs")
    repositions: Mapped[List["OptimizationReposition"]] = relationship(
        "OptimizationReposition", back_populates="run", cascade="all, delete-orphan"
    )
    leases: Mapped[List["OptimizationLease"]] = relationship(
        "OptimizationLease", back_populates="run", cascade="all, delete-orphan"
    )
    inventories: Mapped[List["OptimizationInventory"]] = relationship(
        "OptimizationInventory", back_populates="run", cascade="all, delete-orphan"
    )
    demands: Mapped[List["OptimizationDemand"]] = relationship(
        "OptimizationDemand", back_populates="run", cascade="all, delete-orphan"
    )


class OptimizationReposition(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_repositions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    voyage_leg_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("voyage_legs.id", ondelete="CASCADE"),
        nullable=False,
    )
    container_type: Mapped[ContainerType] = mapped_column(
        SQLEnum(ContainerType, native_enum=False),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    departure_week: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    run: Mapped["OptimizationRun"] = relationship("OptimizationRun", back_populates="repositions")
    voyage_leg: Mapped["VoyageLeg"] = relationship("VoyageLeg", back_populates="optimization_repositions")


class OptimizationLease(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_leases"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    lease_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leases.id", ondelete="SET NULL"),
        nullable=True,
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
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[date] = mapped_column(Date, nullable=False)

    # Relationships
    run: Mapped["OptimizationRun"] = relationship("OptimizationRun", back_populates="leases")
    lease: Mapped[Optional["Lease"]] = relationship("Lease", back_populates="optimization_leases")
    location: Mapped["Location"] = relationship("Location", back_populates="optimization_leases")


class OptimizationInventory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_inventories"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.id", ondelete="CASCADE"),
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
    week: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    run: Mapped["OptimizationRun"] = relationship("OptimizationRun", back_populates="inventories")
    location: Mapped["Location"] = relationship("Location", back_populates="optimization_inventories")


class OptimizationDemand(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "optimization_demands"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("optimization_runs.id", ondelete="CASCADE"),
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
    week: Mapped[date] = mapped_column(Date, nullable=False)
    confirmed_served: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forecast_served: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    forecast_backlog: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confirmed_shortage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    run: Mapped["OptimizationRun"] = relationship("OptimizationRun", back_populates="demands")
    location: Mapped["Location"] = relationship("Location", back_populates="optimization_demands")
