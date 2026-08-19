from uuid import UUID
from typing import Optional, List, Dict, Any
from app.db.enums import ContainerType
from app.db.schemas.base import CamelModel


class DashboardOverviewResponse(CamelModel):
    inventory: Dict[str, Any] = {}
    shortages: Dict[str, Any] = {}
    surplus_locations: List[Dict[str, Any]] = []
    deficit_locations: List[Dict[str, Any]] = []
    active_bookings: int = 0
    upcoming_voyages: int = 0
    latest_optimization_run: Optional[Dict[str, Any]] = None


class DashboardAlertResponse(CamelModel):
    type: str
    location_id: UUID
    container_type: ContainerType
    week: str
    quantity: int
    severity: str
