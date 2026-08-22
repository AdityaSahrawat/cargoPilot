import uuid
from typing import Optional
from sqlalchemy import String, Float, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base
from app.db.models.base import UUIDMixin, TimestampMixin


class CostParameter(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "cost_parameters"

    parameter_key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
