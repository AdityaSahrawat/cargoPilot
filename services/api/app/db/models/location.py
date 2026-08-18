from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, Enum as SQLEnum
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
    repair_capability: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    operational_status: Mapped[OperationalStatus] = mapped_column(
        SQLEnum(OperationalStatus, native_enum=False),
        default=OperationalStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
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
