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
    status: VoyageStatus = VoyageStatus.SCHEDULED


class VoyageCreate(VoyageBase):
    pass


class VoyageUpdate(CamelModel):
    service_id: Optional[UUID] = None
    vessel_id: Optional[UUID] = None
    voyage_number: Optional[str] = None
    departure_time: Optional[datetime] = None
    arrival_time: Optional[datetime] = None
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


class VoyageLegCreate(VoyageLegBase):
    pass


class VoyageLegResponse(VoyageLegBase):
    id: UUID
    available_capacity: int
    created_at: datetime
    updated_at: datetime
