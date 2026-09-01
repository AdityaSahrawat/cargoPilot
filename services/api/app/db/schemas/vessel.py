from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import VesselType, VesselStatus
from app.db.schemas.base import CamelModel


class VesselBase(CamelModel):
    imo_number: str
    name: str
    owner_company_id: UUID
    operator_company_id: UUID
    vessel_type: VesselType
    container_capacity: int
    deadweight_capacity_mt: float = 20000.0
    reefer_plugs: int = 100
    status: VesselStatus = VesselStatus.ACTIVE


class VesselCreate(VesselBase):
    pass


class VesselUpdate(CamelModel):
    imo_number: Optional[str] = None
    name: Optional[str] = None
    owner_company_id: Optional[UUID] = None
    operator_company_id: Optional[UUID] = None
    vessel_type: Optional[VesselType] = None
    container_capacity: Optional[int] = None
    deadweight_capacity_mt: Optional[float] = None
    reefer_plugs: Optional[int] = None
    status: Optional[VesselStatus] = None


class VesselResponse(VesselBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
