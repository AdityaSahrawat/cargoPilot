from uuid import UUID
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.db.enums import ContainerType


class DemandForecastBase(BaseModel):
    company_id: UUID
    location_id: UUID
    container_type: ContainerType
    week: date
    quantity: int
    confidence: Optional[float] = None


class DemandForecastCreate(DemandForecastBase):
    pass


class DemandForecastUpdate(BaseModel):
    company_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    container_type: Optional[ContainerType] = None
    week: Optional[date] = None
    quantity: Optional[int] = None
    confidence: Optional[float] = None


class DemandForecastResponse(DemandForecastBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
