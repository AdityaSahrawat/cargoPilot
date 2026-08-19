from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import LocationType, OperationalStatus
from app.db.schemas.base import CamelModel


class LocationBase(CamelModel):
    name: str
    location_type: LocationType
    unlocode: Optional[str] = None
    country: str
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    storage_capacity: Optional[int] = None
    repair_capability: Optional[bool] = None
    operational_status: OperationalStatus = OperationalStatus.ACTIVE


class LocationCreate(LocationBase):
    pass


class LocationUpdate(CamelModel):
    name: Optional[str] = None
    location_type: Optional[LocationType] = None
    unlocode: Optional[str] = None
    country: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    storage_capacity: Optional[int] = None
    repair_capability: Optional[bool] = None
    operational_status: Optional[OperationalStatus] = None


class LocationResponse(LocationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
