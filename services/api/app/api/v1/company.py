from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/company", response_model=schemas.CompanyResponse)
def get_current_company(db: Session = Depends(get_db)):
    """GET /api/v1/company - Get the currently authenticated CargoPilot company's information."""
    company = db.query(models.Company).filter(models.Company.is_self == True).first()
    if not company:
        company = db.query(models.Company).first()

    if not company:
        # Create a default self company if none exists
        company = models.Company(
            name="CargoPilot Carrier",
            company_type=enums.CompanyType.CARRIER,
            is_self=True,
            hq_country="India",
            alliance="CargoPilot Alliance",
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    return company


@router.get("/locations", response_model=List[schemas.LocationResponse])
def get_locations(
    type: Optional[enums.LocationType] = Query(None, alias="type"),
    status: Optional[enums.OperationalStatus] = Query(None, alias="status"),
    country: Optional[str] = Query(None, alias="country"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/locations - Filterable locations list."""
    query = db.query(models.Location)

    if type:
        query = query.filter(models.Location.location_type == type)
    if status:
        query = query.filter(models.Location.operational_status == status)
    if country:
        query = query.filter(models.Location.country.ilike(f"%{country}%"))

    return query.all()


@router.get("/locations/{location_id}", response_model=schemas.LocationResponse)
def get_location_by_id(location_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/locations/:id - Complete location information."""
    loc = db.query(models.Location).filter(models.Location.id == location_id).first()
    if not loc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location {location_id} not found",
        )
    return loc
