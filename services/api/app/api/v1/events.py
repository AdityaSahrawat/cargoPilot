from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.post("/container-events", response_model=schemas.ContainerEventResponse, status_code=status.HTTP_201_CREATED)
def create_container_event(
    body: schemas.ContainerEventCreate,
    db: Session = Depends(get_db),
):
    """POST /api/v1/container-events - Create container event & update container operational state."""
    container = db.query(models.Container).filter(models.Container.id == body.container_id).first()
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container {body.container_id} not found",
        )

    event = models.ContainerEvent(
        container_id=body.container_id,
        event_type=body.event_type,
        timestamp=body.timestamp,
        location_id=body.location_id,
        voyage_id=body.voyage_id,
        metadata_json=body.metadata_json,
    )
    db.add(event)

    # State reconstruction logic based on event type
    container.last_movement_at = body.timestamp

    if body.event_type == enums.ContainerEventType.GATE_IN:
        container.status = enums.ContainerStatus.AVAILABLE
        if body.location_id:
            container.current_location_id = body.location_id

    elif body.event_type == enums.ContainerEventType.GATE_OUT:
        container.status = enums.ContainerStatus.IN_TRANSIT
        container.current_location_id = None

    elif body.event_type == enums.ContainerEventType.LOADED:
        container.status = enums.ContainerStatus.LOADED
        if body.voyage_id:
            container.current_voyage_id = body.voyage_id

    elif body.event_type == enums.ContainerEventType.DISCHARGED:
        container.status = enums.ContainerStatus.AVAILABLE
        container.current_voyage_id = None
        if body.location_id:
            container.current_location_id = body.location_id

    elif body.event_type == enums.ContainerEventType.RETURNED:
        container.status = enums.ContainerStatus.AVAILABLE
        if body.location_id:
            container.current_location_id = body.location_id

    elif body.event_type == enums.ContainerEventType.REPAIRED:
        container.status = enums.ContainerStatus.AVAILABLE
        container.condition = enums.ContainerCondition.CARGO_WORTHY

    elif body.event_type == enums.ContainerEventType.RELEASED:
        container.status = enums.ContainerStatus.AVAILABLE

    elif body.event_type == enums.ContainerEventType.DAMAGED:
        container.status = enums.ContainerStatus.UNDER_REPAIR
        container.condition = enums.ContainerCondition.DAMAGED

    db.commit()
    db.refresh(event)

    return event


@router.get("/containers/{container_id}/events", response_model=List[schemas.ContainerEventResponse])
def get_container_events(
    container_id: UUID,
    from_date: Optional[datetime] = Query(None, alias="fromDate"),
    to_date: Optional[datetime] = Query(None, alias="toDate"),
    event_type: Optional[enums.ContainerEventType] = Query(None, alias="eventType"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/containers/:id/events - Chronological events for a container."""
    container = db.query(models.Container).filter(models.Container.id == container_id).first()
    if not container:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Container {container_id} not found",
        )

    query = (
        db.query(models.ContainerEvent)
        .filter(models.ContainerEvent.container_id == container_id)
        .order_by(models.ContainerEvent.timestamp.asc())
    )

    if from_date:
        query = query.filter(models.ContainerEvent.timestamp >= from_date)
    if to_date:
        query = query.filter(models.ContainerEvent.timestamp <= to_date)
    if event_type:
        query = query.filter(models.ContainerEvent.event_type == event_type)

    return query.all()
