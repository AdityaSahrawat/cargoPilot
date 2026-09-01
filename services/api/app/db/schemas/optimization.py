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
    solver_status: Optional[str] = "OPTIMAL"
    optimality_gap: Optional[float] = 0.0
    solve_time_seconds: Optional[float] = 0.0
    objective_value: Optional[float] = None
    total_repositioning_cost: Optional[float] = 0.0
    total_leasing_cost: Optional[float] = 0.0
    total_holding_cost: Optional[float] = 0.0
    total_shortage_penalty: Optional[float] = 0.0
    created_at: datetime
    completed_at: Optional[datetime] = None


class OptimizationRunApproveRequest(CamelModel):
    comment: Optional[str] = "Approved for execution"


class OptimizationRunApproveResponse(CamelModel):
    run_id: UUID
    status: str = "APPROVED"
    approved_at: datetime


class BookingAllocationPlanItem(CamelModel):
    booking_id: UUID
    path_id: str
    voyage_id: Optional[UUID] = None
    container_type: ContainerType
    owned_quantity: int = 0
    leased_quantity: int = 0
    unserved_quantity: int = 0
    departure_date: Optional[datetime] = None
    expected_arrival_date: Optional[datetime] = None
    delivery_delay_days: int = 0
    fulfillment_cost: float = 0.0


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
    solver_status: str = "OPTIMAL"
    optimality_gap: float = 0.0
    solve_time_seconds: float = 0.0
    booking_allocations: List[BookingAllocationPlanItem] = []
    repositioning: List[RepositioningPlanItem] = []
    leasing: List[LeasingPlanItem] = []
    inventory: List[InventoryPlanItem] = []
    demand: List[DemandPlanItem] = []
