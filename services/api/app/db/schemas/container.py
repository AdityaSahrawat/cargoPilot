from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.db.enums import (
    ContainerType,
    ContainerStatus,
    ContainerCondition,
    ContainerEventType,
    CommitmentType,
    CommitmentStatus,
)
from app.db.schemas.base import CamelModel


class ContainerBase(CamelModel):
    container_number: str
    container_type: ContainerType
    owner_company_id: UUID
    current_location_id: Optional[UUID] = None
    current_voyage_id: Optional[UUID] = None
    status: ContainerStatus = ContainerStatus.AVAILABLE
    condition: ContainerCondition = ContainerCondition.CARGO_WORTHY
    controlled_by_carrier: bool = True
    customs_hold: bool = False
    is_emergency_reserve: bool = False
    available_from: Optional[datetime] = None
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
    controlled_by_carrier: Optional[bool] = None
    customs_hold: Optional[bool] = None
    is_emergency_reserve: Optional[bool] = None
    available_from: Optional[datetime] = None
    last_movement_at: Optional[datetime] = None


class ContainerResponse(ContainerBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ContainerListResponse(CamelModel):
    data: List[ContainerResponse]
    total: int


class ContainerCommitmentBase(CamelModel):
    container_id: UUID
    commitment_type: CommitmentType
    reference_id: Optional[str] = None
    required_location_id: Optional[UUID] = None
    required_at: Optional[datetime] = None
    status: CommitmentStatus = CommitmentStatus.ACTIVE


class ContainerCommitmentCreate(ContainerCommitmentBase):
    pass


class ContainerCommitmentResponse(ContainerCommitmentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ExpectedContainerMovementBase(CamelModel):
    container_id: UUID
    from_location_id: Optional[UUID] = None
    to_location_id: Optional[UUID] = None
    voyage_id: Optional[UUID] = None
    planned_date: datetime
    expected_date: datetime
    status: str = "EXPECTED"


class ExpectedContainerMovementResponse(ExpectedContainerMovementBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


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
