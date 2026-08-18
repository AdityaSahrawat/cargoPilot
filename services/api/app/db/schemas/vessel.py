from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.db.enums import VesselType, VesselStatus


class VesselBase(BaseModel):
    imo_number: str
    name: str
    owner_company_id: UUID
    operator_company_id: UUID
    vessel_type: VesselType
    container_capacity: int
    status: VesselStatus = VesselStatus.ACTIVE


class VesselCreate(VesselBase):
    pass


class VesselUpdate(BaseModel):
    imo_number: Optional[str] = None
    name: Optional[str] = None
    owner_company_id: Optional[UUID] = None
    operator_company_id: Optional[UUID] = None
    vessel_type: Optional[VesselType] = None
    container_capacity: Optional[int] = None
    status: Optional[VesselStatus] = None


class VesselResponse(VesselBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
