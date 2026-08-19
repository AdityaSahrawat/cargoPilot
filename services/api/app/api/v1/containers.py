from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/containers", response_model=schemas.ContainerListResponse)
def list_containers(
    location_id: Optional[UUID] = Query(None, alias="locationId"),
    container_type: Optional[enums.ContainerType] = Query(None, alias="containerType"),
    container_status: Optional[enums.ContainerStatus] = Query(None, alias="status"),
    condition: Optional[enums.ContainerCondition] = Query(None, alias="condition"),
    owner_company_id: Optional[UUID] = Query(None, alias="ownerCompanyId"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """GET /api/v1/containers - List physical containers with pagination & filtering."""
    query = db.query(models.Container)

    if location_id:
        query = query.filter(models.Container.current_location_id == location_id)
    if container_type:
        query = query.filter(models.Container.container_type == container_type)
    if container_status:
        query = query.filter(models.Container.status == container_status)
    if condition:
        query = query.filter(models.Container.condition == condition)
    if owner_company_id:
        query = query.filter(models.Container.owner_company_id == owner_company_id)

    total = query.count()
    offset = (page - 1) * limit
    containers = query.offset(offset).limit(limit).all()

    return schemas.ContainerListResponse(
        data=[schemas.ContainerResponse.model_validate(c) for c in containers],
        total=total,
    )


@router.get("/containers/{container_id}", response_model=schemas.ContainerResponse)
def get_container_by_id(container_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/containers/:id - Complete container details."""
    container = db.query(models.Container).filter(models.Container.id == container_id).first()
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container {container_id} not found",
        )
    return container


@router.get("/inventory", response_model=List[schemas.InventorySummaryResponse])
def get_inventory_summary(
    location_id: Optional[UUID] = Query(None, alias="locationId"),
    container_type: Optional[enums.ContainerType] = Query(None, alias="containerType"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/inventory - Aggregated equipment inventory by location & container type."""
    query = db.query(models.Container)

    if location_id:
        query = query.filter(models.Container.current_location_id == location_id)
    if container_type:
        query = query.filter(models.Container.container_type == container_type)

    containers = query.all()

    # Group by (location_id, container_type)
    grouped = {}
    for c in containers:
        if not c.current_location_id:
            continue
        key = (c.current_location_id, c.container_type)
        if key not in grouped:
            grouped[key] = {
                "available": 0,
                "assigned": 0,
                "in_transit": 0,
                "under_repair": 0,
            }

        if c.status == enums.ContainerStatus.AVAILABLE:
            grouped[key]["available"] += 1
        elif c.status == enums.ContainerStatus.ASSIGNED or c.status == enums.ContainerStatus.LOADED:
            grouped[key]["assigned"] += 1
        elif c.status == enums.ContainerStatus.IN_TRANSIT:
            grouped[key]["in_transit"] += 1
        elif c.status == enums.ContainerStatus.UNDER_REPAIR:
            grouped[key]["under_repair"] += 1

    summary = []
    for (loc_id, ctype), counts in grouped.items():
        summary.append(
            schemas.InventorySummaryResponse(
                location_id=loc_id,
                container_type=ctype,
                available=counts["available"],
                assigned=counts["assigned"],
                in_transit=counts["in_transit"],
                under_repair=counts["under_repair"],
            )
        )

    return summary
