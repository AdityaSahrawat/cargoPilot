from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/bookings", response_model=schemas.BookingListResponse)
def list_bookings(
    voyage_id: Optional[UUID] = Query(None, alias="voyageId"),
    origin_location_id: Optional[UUID] = Query(None, alias="originLocationId"),
    destination_location_id: Optional[UUID] = Query(None, alias="destinationLocationId"),
    container_type: Optional[enums.ContainerType] = Query(None, alias="containerType"),
    booking_status: Optional[enums.BookingStatus] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="fromDate"),
    to_date: Optional[datetime] = Query(None, alias="toDate"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """GET /api/v1/bookings - List bookings with filtering & pagination."""
    query = db.query(models.Booking)

    if voyage_id:
        query = query.filter(models.Booking.voyage_id == voyage_id)
    if origin_location_id:
        query = query.filter(models.Booking.origin_location_id == origin_location_id)
    if destination_location_id:
        query = query.filter(models.Booking.destination_location_id == destination_location_id)
    if container_type:
        query = query.filter(models.Booking.container_type == container_type)
    if booking_status:
        query = query.filter(models.Booking.status == booking_status)
    if from_date:
        query = query.filter(models.Booking.requested_pickup_date >= from_date)
    if to_date:
        query = query.filter(models.Booking.requested_pickup_date <= to_date)

    offset = (page - 1) * limit
    bookings = query.offset(offset).limit(limit).all()

    return schemas.BookingListResponse(
        data=[schemas.BookingResponse.model_validate(b) for b in bookings]
    )


@router.get("/bookings/{booking_id}", response_model=schemas.BookingResponse)
def get_booking_by_id(booking_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/bookings/:id - Complete booking details."""
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Booking {booking_id} not found",
        )
    return booking


@router.get("/bookings/{booking_id}/assignments", response_model=List[schemas.EquipmentAssignmentResponse])
def get_booking_assignments(booking_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/bookings/:id/assignments - Physical containers assigned to a booking."""
    assignments = (
        db.query(models.EquipmentAssignment)
        .filter(models.EquipmentAssignment.booking_id == booking_id)
        .all()
    )
    return assignments


@router.get("/assignments", response_model=List[schemas.EquipmentAssignmentResponse])
def list_assignments(
    booking_id: Optional[UUID] = Query(None, alias="bookingId"),
    container_id: Optional[UUID] = Query(None, alias="containerId"),
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/assignments - Query equipment assignments."""
    query = db.query(models.EquipmentAssignment)

    if booking_id:
        query = query.filter(models.EquipmentAssignment.booking_id == booking_id)
    if container_id:
        query = query.filter(models.EquipmentAssignment.container_id == container_id)
    if status_filter == "ACTIVE":
        query = query.filter(models.EquipmentAssignment.released_at.is_(None))
    elif status_filter == "RELEASED":
        query = query.filter(models.EquipmentAssignment.released_at.isnot(None))

    return query.all()


@router.post("/assignments", response_model=schemas.EquipmentAssignmentResponse, status_code=status.HTTP_201_CREATED)
def create_assignment(
    body: schemas.EquipmentAssignmentCreate,
    db: Session = Depends(get_db),
):
    """POST /api/v1/assignments - Create a physical container -> booking assignment."""
    container = db.query(models.Container).filter(models.Container.id == body.container_id).first()
    if not container:
        raise HTTPException(status_code=404, detail=f"Container {body.container_id} not found")

    booking = db.query(models.Booking).filter(models.Booking.id == body.booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail=f"Booking {body.booking_id} not found")

    assignment = models.EquipmentAssignment(
        container_id=body.container_id,
        booking_id=body.booking_id,
        assigned_at=datetime.utcnow(),
    )
    db.add(assignment)

    # Update container status to ASSIGNED
    container.status = enums.ContainerStatus.ASSIGNED
    db.commit()
    db.refresh(assignment)

    return assignment


@router.post("/assignments/{assignment_id}/release", response_model=schemas.EquipmentAssignmentResponse)
def release_assignment(assignment_id: UUID, db: Session = Depends(get_db)):
    """POST /api/v1/assignments/:id/release - Release an equipment assignment."""
    assignment = (
        db.query(models.EquipmentAssignment)
        .filter(models.EquipmentAssignment.id == assignment_id)
        .first()
    )
    if not assignment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Assignment {assignment_id} not found",
        )

    assignment.released_at = datetime.utcnow()

    # Revert container status to AVAILABLE
    if assignment.container:
        assignment.container.status = enums.ContainerStatus.AVAILABLE

    db.commit()
    db.refresh(assignment)

    return assignment
