from uuid import UUID
from datetime import datetime
from typing import Optional, List
from app.db.enums import ContainerType, OptimizationStatus
from app.db.schemas.base import CamelModel


class OptimizationRunRequest(CamelModel):
    start_week: str
    horizon_weeks: int
    container_types: Optional[List[ContainerType]] = None
    location_ids: Optional[List[UUID]] = None


class OptimizationRunStartResponse(CamelModel):
    run_id: UUID
    status: OptimizationStatus


class OptimizationRunResponse(CamelModel):
    id: UUID
    company_id: UUID
    start_week: str
    horizon_weeks: int
    status: OptimizationStatus
    objective_value: Optional[float] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class OptimizationRunApproveRequest(CamelModel):
    comment: Optional[str] = "Approved for execution"


class OptimizationRunApproveResponse(CamelModel):
    run_id: UUID
    status: str = "APPROVED"
    approved_at: datetime


class RepositioningPlanItem(CamelModel):
    week: str
    voyage_leg_id: UUID
    from_location_id: Optional[UUID] = None
    to_location_id: Optional[UUID] = None
    container_type: ContainerType
    quantity: int
    cost: float = 0.0


class LeasingPlanItem(CamelModel):
    week: str
    location_id: UUID
    container_type: ContainerType
    quantity: int
    cost: float = 0.0


class InventoryPlanItem(CamelModel):
    week: str
    location_id: UUID
    container_type: ContainerType
    quantity: int


class DemandPlanItem(CamelModel):
    week: str
    location_id: UUID
    container_type: ContainerType
    confirmed_demand: int = 0
    confirmed_served: int = 0
    forecast_demand: int = 0
    forecast_served: int = 0
    forecast_backlog: int = 0
    confirmed_shortage: int = 0


class OptimizationPlanResponse(CamelModel):
    run_id: UUID
    total_cost: float
    repositioning: List[RepositioningPlanItem] = []
    leasing: List[LeasingPlanItem] = []
    inventory: List[InventoryPlanItem] = []
    demand: List[DemandPlanItem] = []
