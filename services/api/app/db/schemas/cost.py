from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.schemas.base import CamelModel


class CostParameterBase(CamelModel):
    parameter_key: str
    category: str
    value: float
    unit: str
    description: Optional[str] = None


class CostParameterCreate(CostParameterBase):
    pass


class CostParameterResponse(CostParameterBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
