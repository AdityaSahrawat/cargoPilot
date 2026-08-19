from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/leases", response_model=List[schemas.LeaseResponse])
def list_leases(
    container_type: Optional[enums.ContainerType] = Query(None, alias="containerType"),
    location_id: Optional[UUID] = Query(None, alias="locationId"),
    status_filter: Optional[str] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="fromDate"),
    to_date: Optional[datetime] = Query(None, alias="toDate"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/leases - List active and past lease agreements."""
    query = db.query(models.Lease)

    if container_type:
        query = query.filter(models.Lease.container_type == container_type)
    if location_id:
        query = query.filter(
            (models.Lease.pickup_location_id == location_id)
            | (models.Lease.return_location_id == location_id)
        )
    if from_date:
        query = query.filter(models.Lease.start_date >= from_date)
    if to_date:
        query = query.filter(models.Lease.start_date <= to_date)

    return query.all()


@router.get("/leases/{lease_id}", response_model=schemas.LeaseResponse)
def get_lease_by_id(lease_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/leases/:id - Complete lease details."""
    lease = db.query(models.Lease).filter(models.Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Lease {lease_id} not found",
        )
    return lease
