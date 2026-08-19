import uuid
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict
from app.db.enums import ContainerType


@dataclass
class ForecastItem:
    location_id: uuid.UUID
    container_type: ContainerType
    week: str
    quantity: int


@dataclass
class LegCapacityItem:
    leg_id: uuid.UUID
    voyage_id: uuid.UUID
    from_port_id: uuid.UUID
    to_port_id: uuid.UUID
    available_capacity: int


@dataclass
class OptimizationInput:
    company_id: uuid.UUID
    start_week: str
    horizon_weeks: int
    container_types: List[ContainerType]
    location_ids: List[uuid.UUID]
    initial_inventories: Dict[str, int] = field(default_factory=dict)
    forecasts: List[ForecastItem] = field(default_factory=list)
    leg_capacities: List[LegCapacityItem] = field(default_factory=list)


@dataclass
class RepositioningResult:
    week: str
    voyage_leg_id: uuid.UUID
    from_location_id: Optional[uuid.UUID]
    to_location_id: Optional[uuid.UUID]
    container_type: ContainerType
    quantity: int
    cost: float


@dataclass
class LeasingResult:
    week: str
    location_id: uuid.UUID
    lease_id: Optional[uuid.UUID]
    container_type: ContainerType
    quantity: int
    cost: float


@dataclass
class InventoryResult:
    week: str
    location_id: uuid.UUID
    container_type: ContainerType
    quantity: int


@dataclass
class DemandResult:
    week: str
    location_id: uuid.UUID
    container_type: ContainerType
    confirmed_demand: int
    confirmed_served: int
    forecast_demand: int
    forecast_served: int
    forecast_backlog: int
    confirmed_shortage: int


@dataclass
class OptimizationResult:
    objective_value: float
    repositioning: List[RepositioningResult] = field(default_factory=list)
    leasing: List[LeasingResult] = field(default_factory=list)
    inventory: List[InventoryResult] = field(default_factory=list)
    demand: List[DemandResult] = field(default_factory=list)
