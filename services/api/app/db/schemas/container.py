from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.db.enums import ContainerType, ContainerStatus, ContainerCondition, ContainerEventType
from app.db.schemas.base import CamelModel


class ContainerBase(CamelModel):
    container_number: str
    container_type: ContainerType
    owner_company_id: UUID
    current_location_id: Optional[UUID] = None
    current_voyage_id: Optional[UUID] = None
    status: ContainerStatus = ContainerStatus.AVAILABLE
    condition: ContainerCondition = ContainerCondition.CARGO_WORTHY
    available_from: datetime
    last_movement_at: Optional[datetime] = None


class ContainerCreate(ContainerBase):
    pass


class ContainerUpdate(CamelModel):
    container_number: Optional[str] = None
    container_type: Optional[ContainerType] = None
    owner_company_id: Optional[UUID] = None
    current_location_id: Optional[UUID] = None
    current_voyage_id: Optional[UUID] = None
    status: Optional[ContainerStatus] = None
    condition: Optional[ContainerCondition] = None
    available_from: Optional[datetime] = None
    last_movement_at: Optional[datetime] = None


class ContainerResponse(ContainerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ContainerListResponse(CamelModel):
    data: List[ContainerResponse]
    total: int


class ContainerEventBase(CamelModel):
    container_id: UUID
    event_type: ContainerEventType
    timestamp: datetime
    location_id: Optional[UUID] = None
    voyage_id: Optional[UUID] = None
    metadata_json: Optional[Dict[str, Any]] = None


class ContainerEventCreate(ContainerEventBase):
    pass


class ContainerEventResponse(ContainerEventBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class InventorySummaryResponse(CamelModel):
    location_id: UUID
    container_type: ContainerType
    available: int = 0
    assigned: int = 0
    in_transit: int = 0
    under_repair: int = 0
