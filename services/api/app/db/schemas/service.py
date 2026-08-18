from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict
from app.db.enums import ServiceStatus


class ServiceBase(BaseModel):
    name: str
    operator_company_id: UUID
    status: ServiceStatus = ServiceStatus.ACTIVE


class ServiceCreate(ServiceBase):
    pass


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    operator_company_id: Optional[UUID] = None
    status: Optional[ServiceStatus] = None


class ServiceResponse(ServiceBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
