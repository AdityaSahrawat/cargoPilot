from uuid import UUID
from datetime import date, datetime
from typing import Optional
from app.db.enums import ContainerType
from app.db.schemas.base import CamelModel


class ProcurementOrderBase(CamelModel):
    po_number: str
    supplier_name: str
    container_type: ContainerType
    quantity: int
    order_date: date
    expected_delivery: date
    delivery_location_id: UUID
    unit_price: float
    status: str = "IN_PRODUCTION"


class ProcurementOrderCreate(ProcurementOrderBase):
    pass


class ProcurementOrderResponse(ProcurementOrderBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ProcurementRecommendationBase(CamelModel):
    recommendation_code: str
    container_type: ContainerType
    quantity: int
    recommended_location_id: UUID
    required_by_week: str
    recommended_order_by_date: str
    reason: Optional[str] = None


class ProcurementRecommendationCreate(ProcurementRecommendationBase):
    pass


class ProcurementRecommendationResponse(ProcurementRecommendationBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
