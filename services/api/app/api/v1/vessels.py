from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


# Vessels
@router.get("/vessels", response_model=List[schemas.VesselResponse])
def get_vessels(
    vessel_status: Optional[enums.VesselStatus] = Query(None, alias="status"),
    operator_company_id: Optional[UUID] = Query(None, alias="operatorCompanyId"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/vessels - List vessel fleet."""
    query = db.query(models.Vessel)
    if vessel_status:
        query = query.filter(models.Vessel.status == vessel_status)
    if operator_company_id:
        query = query.filter(models.Vessel.operator_company_id == operator_company_id)
    return query.all()


@router.get("/vessels/{vessel_id}", response_model=schemas.VesselResponse)
def get_vessel_by_id(vessel_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/vessels/:id - Vessel details."""
    vessel = db.query(models.Vessel).filter(models.Vessel.id == vessel_id).first()
    if not vessel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vessel {vessel_id} not found",
        )
    return vessel


# Services
@router.get("/services", response_model=List[schemas.ServiceResponse])
def get_services(
    service_status: Optional[enums.ServiceStatus] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/services - List trade services."""
    query = db.query(models.Service)
    if service_status:
        query = query.filter(models.Service.status == service_status)
    return query.all()


@router.get("/services/{service_id}", response_model=schemas.ServiceResponse)
def get_service_by_id(service_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/services/:id - Service details."""
    service = db.query(models.Service).filter(models.Service.id == service_id).first()
    if not service:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Service {service_id} not found",
        )
    return service


# Voyages
@router.get("/voyages", response_model=List[schemas.VoyageResponse])
def get_voyages(
    service_id: Optional[UUID] = Query(None, alias="serviceId"),
    vessel_id: Optional[UUID] = Query(None, alias="vesselId"),
    voyage_status: Optional[enums.VoyageStatus] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="fromDate"),
    to_date: Optional[datetime] = Query(None, alias="toDate"),
    location_id: Optional[UUID] = Query(None, alias="locationId"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/voyages - List scheduled voyages."""
    query = db.query(models.Voyage)

    if service_id:
        query = query.filter(models.Voyage.service_id == service_id)
    if vessel_id:
        query = query.filter(models.Voyage.vessel_id == vessel_id)
    if voyage_status:
        query = query.filter(models.Voyage.status == voyage_status)
    if from_date:
        query = query.filter(models.Voyage.departure_time >= from_date)
    if to_date:
        query = query.filter(models.Voyage.arrival_time <= to_date)
    if location_id:
        query = query.join(models.VoyagePortCall).filter(models.VoyagePortCall.port_id == location_id)

    return query.all()


@router.get("/voyages/{voyage_id}", response_model=schemas.VoyageResponse)
def get_voyage_by_id(voyage_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/voyages/:id - Single voyage details."""
    voyage = db.query(models.Voyage).filter(models.Voyage.id == voyage_id).first()
    if not voyage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Voyage {voyage_id} not found",
        )
    return voyage


@router.get("/voyages/{voyage_id}/port-calls", response_model=List[schemas.VoyagePortCallResponse])
def get_voyage_port_calls(voyage_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/voyages/:id/port-calls - Sequential port calls for a voyage."""
    port_calls = (
        db.query(models.VoyagePortCall)
        .filter(models.VoyagePortCall.voyage_id == voyage_id)
        .order_by(models.VoyagePortCall.sequence)
        .all()
    )
    return port_calls


@router.get("/voyages/{voyage_id}/legs", response_model=List[schemas.VoyageLegResponse])
def get_voyage_legs(voyage_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/voyages/:id/legs - Legs for a voyage with calculated availableCapacity."""
    legs = db.query(models.VoyageLeg).filter(models.VoyageLeg.voyage_id == voyage_id).all()
    return legs
