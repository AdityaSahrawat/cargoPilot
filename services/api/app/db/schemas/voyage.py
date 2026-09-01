from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import VoyageStatus
from app.db.schemas.base import CamelModel


class VoyageBase(CamelModel):
    service_id: UUID
    vessel_id: UUID
    voyage_number: str
    departure_time: datetime
    arrival_time: datetime
    expected_arrival_time: Optional[datetime] = None
    is_blank_sailing: bool = False
    status: VoyageStatus = VoyageStatus.SCHEDULED


class VoyageCreate(VoyageBase):
    pass


class VoyageUpdate(CamelModel):
    service_id: Optional[UUID] = None
    vessel_id: Optional[UUID] = None
    voyage_number: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
    expected_arrival_time: Optional[datetime] = None
    is_blank_sailing: Optional[bool] = None
    status: Optional[VoyageStatus] = None


class VoyageResponse(VoyageBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class VoyagePortCallBase(CamelModel):
    voyage_id: UUID
    port_id: UUID
    sequence: int
    arrival_time: datetime
    departure_time: datetime


class VoyagePortCallCreate(VoyagePortCallBase):
    pass


class VoyagePortCallResponse(VoyagePortCallBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class VoyageLegBase(CamelModel):
    voyage_id: UUID
    from_port_call_id: UUID
    to_port_call_id: UUID
    total_capacity: int
    booked_capacity: int = 0
    accessible_capacity: Optional[int] = None
    deadweight_capacity_mt: float = 20000.0
    booked_weight_mt: float = 0.0
    alliance_slots: Optional[int] = 0
    alliance_cost_adjustment: Optional[float] = 0.0


class VoyageLegCreate(VoyageLegBase):
    pass


class VoyageLegResponse(VoyageLegBase):
    id: UUID
    available_capacity: int
    available_weight_capacity: float
    created_at: datetime
    updated_at: datetime


class ContainerVoyageAssignmentBase(CamelModel):
    container_id: UUID
    voyage_id: UUID
    status: str = "COMMITTED"


class ContainerVoyageAssignmentResponse(ContainerVoyageAssignmentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
