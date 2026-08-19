from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import ContainerType
from app.db.schemas.base import CamelModel


class LeaseBase(CamelModel):
    lessor_company_id: UUID
    lessee_company_id: UUID
    container_type: ContainerType
    quantity: int
    start_date: datetime
    end_date: Optional[datetime] = None
    pickup_location_id: UUID
    return_location_id: Optional[UUID] = None
    cost_per_unit: float


class LeaseCreate(LeaseBase):
    pass


class LeaseUpdate(CamelModel):
    lessor_company_id: Optional[UUID] = None
    lessee_company_id: Optional[UUID] = None
    container_type: Optional[ContainerType] = None
    quantity: Optional[int] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    pickup_location_id: Optional[UUID] = None
    return_location_id: Optional[UUID] = None
    cost_per_unit: Optional[float] = None


class LeaseResponse(LeaseBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
