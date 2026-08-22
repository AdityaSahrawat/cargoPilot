from uuid import UUID
from datetime import datetime
from typing import Optional, Union
from app.db.enums import ContainerType
from app.db.schemas.base import CamelModel


class DemandForecastBase(CamelModel):
    location_id: UUID
    container_type: ContainerType
    week: str
    quantity: int
    confidence: Optional[float] = None
    company_id: Optional[UUID] = None


class DemandForecastCreate(DemandForecastBase):
    pass


class DemandForecastUpdate(CamelModel):
    company_id: Optional[UUID] = None
    location_id: Optional[UUID] = None
    container_type: Optional[ContainerType] = None
    week: Optional[str] = None
    quantity: Optional[int] = None
    confidence: Optional[float] = None


class DemandForecastResponse(DemandForecastBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ImportReturnForecastBase(CamelModel):
    location_id: UUID
    container_type: ContainerType
    week: str
    import_volume: int
    expected_empty_returns: int


class ImportReturnForecastResponse(ImportReturnForecastBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
