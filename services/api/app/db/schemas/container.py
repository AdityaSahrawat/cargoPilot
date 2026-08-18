from uuid import UUID
from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict
from app.db.enums import ContainerType, ContainerStatus, ContainerCondition, ContainerEventType


class ContainerBase(BaseModel):
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


class ContainerUpdate(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)


class ContainerEventBase(BaseModel):
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

    model_config = ConfigDict(from_attributes=True)
