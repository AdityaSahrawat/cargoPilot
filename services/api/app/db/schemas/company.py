from uuid import UUID
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict
from app.db.enums import CompanyType


class CompanyLocationBase(BaseModel):
    company_id: UUID
    location_id: UUID
    is_home_port: bool = False


class CompanyLocationCreate(CompanyLocationBase):
    pass


class CompanyLocationResponse(CompanyLocationBase):
    model_config = ConfigDict(from_attributes=True)


class CompanyBase(BaseModel):
    name: str
    company_type: CompanyType
    is_self: bool = False
    hq_country: Optional[str] = None
    alliance: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    company_type: Optional[CompanyType] = None
    is_self: Optional[bool] = None
    hq_country: Optional[str] = None
    alliance: Optional[str] = None


class CompanyResponse(CompanyBase):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
