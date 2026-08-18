import uuid
from typing import List
from sqlalchemy import String, Enum as SQLEnum, ForeignKey, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base
from app.db.enums import ServiceStatus
from app.db.models.base import UUIDMixin, TimestampMixin


class Service(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    operator_company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[ServiceStatus] = mapped_column(
        SQLEnum(ServiceStatus, native_enum=False),
        default=ServiceStatus.ACTIVE,
        nullable=False,
    )

    # Relationships
    operator_company: Mapped["Company"] = relationship(
        "Company", back_populates="operated_services"
    )
    voyages: Mapped[List["Voyage"]] = relationship("Voyage", back_populates="service")
