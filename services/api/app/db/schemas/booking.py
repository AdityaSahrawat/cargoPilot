from uuid import UUID
from datetime import datetime
from typing import Optional, List
from app.db.enums import ContainerType, BookingPriority, BookingStatus
from app.db.schemas.base import CamelModel


class BookingBase(CamelModel):
    customer_company_id: UUID
    carrier_company_id: UUID
    origin_location_id: UUID
    destination_location_id: UUID
    container_type: ContainerType
    quantity: int
    requested_pickup_date: datetime
    required_delivery_date: Optional[datetime] = None
    voyage_id: Optional[UUID] = None
    priority: Optional[BookingPriority] = None
    status: BookingStatus = BookingStatus.DRAFT


class BookingCreate(BookingBase):
    pass


class BookingUpdate(CamelModel):
    customer_company_id: Optional[UUID] = None
    carrier_company_id: Optional[UUID] = None
    origin_location_id: Optional[UUID] = None
    destination_location_id: Optional[UUID] = None
    container_type: Optional[ContainerType] = None
    quantity: Optional[int] = None
    requested_pickup_date: Optional[datetime] = None
    required_delivery_date: Optional[datetime] = None
    voyage_id: Optional[UUID] = None
    priority: Optional[BookingPriority] = None
    status: Optional[BookingStatus] = None


class BookingResponse(BookingBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class BookingListResponse(CamelModel):
    data: List[BookingResponse]


class EquipmentAssignmentBase(CamelModel):
    container_id: UUID
    booking_id: UUID
    assigned_at: datetime
    released_at: Optional[datetime] = None


class EquipmentAssignmentCreate(CamelModel):
    container_id: UUID
    booking_id: UUID


class EquipmentAssignmentResponse(EquipmentAssignmentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
