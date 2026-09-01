import uuid
from typing import List
from sqlalchemy import String, Integer, Float, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import VesselType, VesselStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class Vessel(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "vessels"

    imo_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    operator_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    vessel_type: Mapped[VesselType] = mapped_column(
        SQLEnum(VesselType, native_enum=False),
        nullable=False,
    )
    container_capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    deadweight_capacity_mt: Mapped[float] = mapped_column(Float, default=20000.0, nullable=False)
    reefer_plugs: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    status: Mapped[VesselStatus] = mapped_column(
        SQLEnum(VesselStatus, native_enum=False),
        default=VesselStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    owner_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[owner_company_id], back_populates="owned_vessels"
    )
    operator_company: Mapped["Company"] = relationship(
        "Company", foreign_keys=[operator_company_id], back_populates="operated_vessels"
    )
    voyages: Mapped[List["Voyage"]] = relationship("Voyage", back_populates="vessel")
