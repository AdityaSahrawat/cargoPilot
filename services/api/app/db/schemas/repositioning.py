from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import ContainerType
from app.db.schemas.base import CamelModel


class RepositioningOptionBase(CamelModel):
    option_code: str
    from_location_id: UUID
    to_location_id: UUID
    week: str
    container_type: ContainerType
    max_quantity: int
    arrival_week: str
    cost_per_unit: float


class RepositioningOptionResponse(RepositioningOptionBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class RepositioningCommitmentBase(CamelModel):
    commitment_code: str
    from_location_id: UUID
    to_location_id: UUID
    container_type: ContainerType
    quantity: int
    departure_week: str
    arrival_week: str
    status: str = "BOOKED"
    cost_per_unit: float


class RepositioningCommitmentResponse(RepositioningCommitmentBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
