from uuid import UUID
from datetime import datetime
from typing import Optional
from app.db.enums import ServiceStatus
from app.db.schemas.base import CamelModel


class ServiceBase(CamelModel):
    name: str
    operator_company_id: UUID
    status: ServiceStatus = ServiceStatus.ACTIVE


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(CamelModel):
    name: Optional[str] = None
    operator_company_id: Optional[UUID] = None
    status: Optional[ServiceStatus] = None


class ServiceResponse(ServiceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
