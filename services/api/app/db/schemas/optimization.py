from uuid import UUID
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.db.enums import ContainerType, OptimizationStatus


class OptimizationRunBase(BaseModel):
    company_id: UUID
    start_week: date
    horizon_weeks: int
    status: OptimizationStatus = OptimizationStatus.PENDING
    objective_value: Optional[float] = None
    completed_at: Optional[datetime] = None


class OptimizationRunCreate(OptimizationRunBase):
    pass


class OptimizationRunResponse(OptimizationRunBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OptimizationRepositionBase(BaseModel):
    run_id: UUID
    voyage_leg_id: UUID
    container_type: ContainerType
    quantity: int
    departure_week: date


class OptimizationRepositionCreate(OptimizationRepositionBase):
    pass


class OptimizationRepositionResponse(OptimizationRepositionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OptimizationLeaseBase(BaseModel):
    run_id: UUID
    lease_id: Optional[UUID] = None
    location_id: UUID
    container_type: ContainerType
    quantity: int
    week: date


class OptimizationLeaseCreate(OptimizationLeaseBase):
    pass


class OptimizationLeaseResponse(OptimizationLeaseBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OptimizationInventoryBase(BaseModel):
    run_id: UUID
    location_id: UUID
    container_type: ContainerType
    week: date
    quantity: int


class OptimizationInventoryCreate(OptimizationInventoryBase):
    pass


class OptimizationInventoryResponse(OptimizationInventoryBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OptimizationDemandBase(BaseModel):
    run_id: UUID
    location_id: UUID
    container_type: ContainerType
    week: date
    confirmed_served: int = 0
    forecast_served: int = 0
    forecast_backlog: int = 0
    confirmed_shortage: int = 0


class OptimizationDemandCreate(OptimizationDemandBase):
    pass


class OptimizationDemandResponse(OptimizationDemandBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
