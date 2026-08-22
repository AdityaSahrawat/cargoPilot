from uuid import UUID
from datetime import datetime
from typing import Optional
from pydantic import ConfigDict
from app.db.enums import CompanyType, CustomerPriority
from app.db.schemas.base import CamelModel


class CompanyLocationBase(CamelModel):
    company_id: UUID
    location_id: UUID
    is_home_port: bool = False


class CompanyLocationCreate(CompanyLocationBase):
    pass


class CompanyLocationResponse(CompanyLocationBase):
    pass


class CompanyBase(CamelModel):
    name: str
    company_type: CompanyType
    is_self: bool = False
    hq_country: Optional[str] = None
    alliance: Optional[str] = None
    customer_priority: Optional[CustomerPriority] = CustomerPriority.STANDARD
    leased_equipment_allowed: bool = True
    equipment_source_policy: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(CamelModel):
    name: Optional[str] = None
    company_type: Optional[CompanyType] = None
    is_self: Optional[bool] = None
    hq_country: Optional[str] = None
    alliance: Optional[str] = None
    customer_priority: Optional[CustomerPriority] = None
    leased_equipment_allowed: Optional[bool] = None
    equipment_source_policy: Optional[str] = None


class CompanyResponse(CompanyBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
