from uuid import UUID
from datetime import datetime
from typing import Optional, List
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
    parent_location_id: Optional[UUID] = None
    operating_hours: Optional[str] = None
    pickup_hours: Optional[str] = None
    return_hours: Optional[str] = None
    closed_days: Optional[str] = None
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
    parent_location_id: Optional[UUID] = None
    operating_hours: Optional[str] = None
    pickup_hours: Optional[str] = None
    return_hours: Optional[str] = None
    closed_days: Optional[str] = None
    operational_status: Optional[OperationalStatus] = None


class LocationResponse(LocationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class LocationClosureWindowBase(CamelModel):
    location_id: UUID
    start_time: datetime
    end_time: datetime
    reason: Optional[str] = None


class LocationClosureWindowResponse(LocationClosureWindowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class NetworkRouteBase(CamelModel):
    from_location_id: UUID
    to_location_id: UUID
    transport_mode: str = "TRUCK"
    lead_time_days: int = 1
    cost_per_container: float = 1000.0
    daily_capacity: int = 50
    is_connected: bool = True


class NetworkRouteResponse(NetworkRouteBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
