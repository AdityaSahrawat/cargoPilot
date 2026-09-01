import uuid
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Enum as SQLEnum, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import LocationType, OperationalStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class Location(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "locations"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    location_type: Mapped[LocationType] = mapped_column(
        SQLEnum(LocationType, native_enum=False),
        nullable=False,
    )
    unlocode: Mapped[Optional[str]] = mapped_column(String(10), nullable=True, index=True)
    country: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    latitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    longitude: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    storage_capacity: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reserve_capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    safety_stock_teu: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    devanning_lead_time_days: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    max_daily_moves: Mapped[Optional[int]] = mapped_column(Integer, default=500, nullable=True)
    lift_on_cost: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    lift_off_cost: Mapped[float] = mapped_column(Float, default=50.0, nullable=False)
    repair_capability: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    parent_location_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    operating_hours: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    pickup_hours: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    return_hours: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    closed_days: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    operational_status: Mapped[OperationalStatus] = mapped_column(
        SQLEnum(OperationalStatus, native_enum=False),
        default=OperationalStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    parent_location: Mapped[Optional["Location"]] = relationship(
        "Location", remote_side="Location.id", backref="child_locations"
    )
    company_locations: Mapped[List["CompanyLocation"]] = relationship(
        "CompanyLocation", back_populates="location", cascade="all, delete-orphan"
    )
    containers_here: Mapped[List["Container"]] = relationship(
        "Container", back_populates="current_location", foreign_keys="[Container.current_location_id]"
    )
    origin_bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="origin_location", foreign_keys="[Booking.origin_location_id]"
    )
    destination_bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="destination_location", foreign_keys="[Booking.destination_location_id]"
    )
    pickup_leases: Mapped[List["Lease"]] = relationship(
        "Lease", back_populates="pickup_location", foreign_keys="[Lease.pickup_location_id]"
    )
    return_leases: Mapped[List["Lease"]] = relationship(
        "Lease", back_populates="return_location", foreign_keys="[Lease.return_location_id]"
    )
    port_calls: Mapped[List["VoyagePortCall"]] = relationship(
        "VoyagePortCall", back_populates="port"
    )
    demand_forecasts: Mapped[List["DemandForecast"]] = relationship(
        "DemandForecast", back_populates="location"
    )
    container_events: Mapped[List["ContainerEvent"]] = relationship(
        "ContainerEvent", back_populates="location"
    )
    optimization_leases: Mapped[List["OptimizationLease"]] = relationship(
        "OptimizationLease", back_populates="location"
    )
    optimization_inventories: Mapped[List["OptimizationInventory"]] = relationship(
        "OptimizationInventory", back_populates="location"
    )
    optimization_demands: Mapped[List["OptimizationDemand"]] = relationship(
        "OptimizationDemand", back_populates="location"
    )
    closure_windows: Mapped[List["LocationClosureWindow"]] = relationship(
        "LocationClosureWindow", back_populates="location", cascade="all, delete-orphan"
    )


class LocationClosureWindow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "location_closure_windows"

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[DateTime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # Relationships
    location: Mapped["Location"] = relationship("Location", back_populates="closure_windows")


class NetworkRoute(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "network_routes"

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
    transport_mode: Mapped[str] = mapped_column(String(50), nullable=False, default="TRUCK")
    lead_time_days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    cost_per_container: Mapped[float] = mapped_column(Float, nullable=False, default=1000.0)
    daily_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_connected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    from_location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[from_location_id]
    )
    to_location: Mapped["Location"] = relationship(
        "Location", foreign_keys=[to_location_id]
    )
