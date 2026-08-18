import uuid
from typing import Optional, List
from sqlalchemy import String, Boolean, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import CompanyType
from app.db.models.base import UUIDMixin, TimestampMixin


class CompanyLocation(Base):
    __tablename__ = "company_locations"

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        primary_key=True,
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("locations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    is_home_port: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    company: Mapped["Company"] = relationship("Company", back_populates="company_locations")
    location: Mapped["Location"] = relationship("Location", back_populates="company_locations")


class Company(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    company_type: Mapped[CompanyType] = mapped_column(
        SQLEnum(CompanyType, native_enum=False),
        nullable=False,
    )
    is_self: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    hq_country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    alliance: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    company_locations: Mapped[List["CompanyLocation"]] = relationship(
        "CompanyLocation", back_populates="company", cascade="all, delete-orphan"
    )
    owned_containers: Mapped[List["Container"]] = relationship(
        "Container", back_populates="owner_company", foreign_keys="[Container.owner_company_id]"
    )
    owned_vessels: Mapped[List["Vessel"]] = relationship(
        "Vessel", back_populates="owner_company", foreign_keys="[Vessel.owner_company_id]"
    )
    operated_vessels: Mapped[List["Vessel"]] = relationship(
        "Vessel", back_populates="operator_company", foreign_keys="[Vessel.operator_company_id]"
    )
    operated_services: Mapped[List["Service"]] = relationship(
        "Service", back_populates="operator_company"
    )
    customer_bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="customer_company", foreign_keys="[Booking.customer_company_id]"
    )
    carrier_bookings: Mapped[List["Booking"]] = relationship(
        "Booking", back_populates="carrier_company", foreign_keys="[Booking.carrier_company_id]"
    )
    lessor_leases: Mapped[List["Lease"]] = relationship(
        "Lease", back_populates="lessor_company", foreign_keys="[Lease.lessor_company_id]"
    )
    lessee_leases: Mapped[List["Lease"]] = relationship(
        "Lease", back_populates="lessee_company", foreign_keys="[Lease.lessee_company_id]"
    )
    demand_forecasts: Mapped[List["DemandForecast"]] = relationship(
        "DemandForecast", back_populates="company"
    )
    optimization_runs: Mapped[List["OptimizationRun"]] = relationship(
        "OptimizationRun", back_populates="company"
    )
