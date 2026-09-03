import uuid
from datetime import datetime, date, timedelta, timezone
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import get_test_db
from app.db import models
from app.db.enums import LocationType, ContainerType, ContainerStatus, ContainerCondition, BookingPriority, BookingStatus, VoyageStatus, OperationalStatus
from app.test_worlds.world_1.db_seeder import reseed_world_1_db, load_world_1_from_db, BASE_DATE
from app.scheduling.schedule_planner import (
    generate_and_assign_fleet_schedule,
    CANONICAL_SERVICES,
)

router = APIRouter(prefix="/test-admin", tags=["Test Admin & DB Controls"])


# -------------------------------------------------------------
# Pydantic Schemas for Admin Input
# -------------------------------------------------------------
class CreateBookingRequest(BaseModel):
    origin_unlocode: str
    destination_unlocode: str
    container_type: ContainerType
    quantity: int = Field(..., ge=1)
    cargo_weight_mt: float = Field(default=15.0, ge=1.0)
    cargo_ready_day: int = Field(default=5, ge=0, le=40)
    cutoff_day: int = Field(default=6, ge=0, le=40)
    delivery_deadline_day: int = Field(default=25, ge=0, le=50)
    priority: BookingPriority = Field(default=BookingPriority.NORMAL)


class UpdateBookingRequest(BaseModel):
    quantity: Optional[int] = Field(None, ge=1)
    cargo_weight_mt: Optional[float] = Field(None, ge=1.0)
    cargo_ready_day: Optional[int] = Field(None, ge=0, le=40)
    cutoff_day: Optional[int] = Field(None, ge=0, le=40)
    delivery_deadline_day: Optional[int] = Field(None, ge=0, le=50)
    priority: Optional[BookingPriority] = None


class UpdateVoyageLegRequest(BaseModel):
    departure_day: Optional[int] = Field(None, ge=0, le=50)
    arrival_day: Optional[int] = Field(None, ge=0, le=50)
    capacity_teu: Optional[int] = Field(None, ge=100)
    capacity_weight_mt: Optional[float] = Field(None, ge=1000.0)
    booked_capacity_teu: Optional[int] = Field(None, ge=0)
    booked_weight_mt: Optional[float] = Field(None, ge=0.0)


class UpdateVoyageRequest(BaseModel):
    is_blank_sailing: Optional[bool] = None
    status: Optional[VoyageStatus] = None


class AdjustInventoryRequest(BaseModel):
    port_unlocode: str
    container_type: ContainerType
    quantity_change: int = Field(..., description="Positive to add, negative to remove")


class UpdatePortSettingsRequest(BaseModel):
    safety_stock_teu: Optional[int] = Field(None, ge=0)
    devanning_lead_time_days: Optional[int] = Field(None, ge=0, le=10)
    storage_capacity_teu: Optional[int] = Field(None, ge=500)


class GenerateScheduleRequest(BaseModel):
    horizon_days: int = Field(default=40, ge=10, le=180)
    firm_horizon_days: int = Field(default=14, ge=1, le=60)


class ReassignVesselRequest(BaseModel):
    voyage_number: str
    vessel_name: str
    vessel_assignment_status: Optional[str] = "FIRM"


# -------------------------------------------------------------
# 1. Database Reset & Lifecycle
# -------------------------------------------------------------
@router.post("/reset-db")
def reset_test_database(db: Session = Depends(get_test_db)):
    """
    Clears all tables in cargo_pilot_test.db and restores clean canonical World 1 fixtures.
    """
    counts = reseed_world_1_db(db)
    return {
        "status": "success",
        "message": "cargo_pilot_test.db reset and reseeded with canonical World 1 dataset",
        "records_seeded": counts,
    }


@router.get("/db-status")
def get_test_db_status(db: Session = Depends(get_test_db)):
    """
    Returns live statistics on records stored in cargo_pilot_test.db.
    """
    ports_count = db.query(models.Location).filter(models.Location.location_type == LocationType.PORT).count()
    vessels_count = db.query(models.Vessel).count()
    services_count = db.query(models.Service).count()
    voyages_count = db.query(models.Voyage).count()
    legs_count = db.query(models.VoyageLeg).count()
    bookings_count = db.query(models.Booking).count()
    containers_count = db.query(models.Container).count()

    return {
        "database": "cargo_pilot_test.db",
        "status": "ACTIVE",
        "counts": {
            "ports": ports_count,
            "vessels": vessels_count,
            "services": services_count,
            "voyages": voyages_count,
            "voyage_legs": legs_count,
            "bookings": bookings_count,
            "containers": containers_count,
        },
    }


# -------------------------------------------------------------
# 2. Upstream Service Rotations & Vessel Assignment Engine
# -------------------------------------------------------------
@router.get("/services")
def list_service_templates(db: Session = Depends(get_test_db)):
    """Lists recurring Service rotation templates (Loop A, Loop B) with port stops and frequencies."""
    services = db.query(models.Service).all()
    results = []
    for s in services:
        results.append({
            "service_id": str(s.id),
            "name": s.name,
            "code": s.code,
            "frequency_days": s.frequency_days,
            "rotation_pattern": s.rotation_pattern,
            "voyages_count": len(s.voyages),
        })
    return {"services": results}


@router.post("/generate-schedule")
def run_schedule_and_vessel_assignment(payload: GenerateScheduleRequest, db: Session = Depends(get_test_db)):
    """
    Executes Upstream Workflow:
    Service Pattern -> Voyage Generator -> Vessel Assignment Planner (Firm vs Provisional) -> Persists in DB.
    """
    res = generate_and_assign_fleet_schedule(
        db=db,
        horizon_days=payload.horizon_days,
        firm_horizon_days=payload.firm_horizon_days,
        base_date=BASE_DATE,
    )
    return res


@router.post("/reassign-vessel")
def reassign_vessel_to_voyage(payload: ReassignVesselRequest, db: Session = Depends(get_test_db)):
    """
    Manually reassigns a vessel to a future voyage and updates leg capacities in cargo_pilot_test.db.
    """
    voy = db.query(models.Voyage).filter(models.Voyage.voyage_number == payload.voyage_number).first()
    if not voy:
        raise HTTPException(status_code=404, detail="Voyage not found")

    vessel = db.query(models.Vessel).filter(models.Vessel.name == payload.vessel_name).first()
    if not vessel:
        raise HTTPException(status_code=404, detail="Vessel not found")

    voy.vessel_id = vessel.id
    voy.vessel_assignment_status = payload.vessel_assignment_status or "FIRM"

    # Propagate new vessel capacities to all legs of this voyage
    for leg in voy.legs:
        leg.total_capacity = vessel.container_capacity
        leg.deadweight_capacity_mt = vessel.deadweight_capacity_mt

    db.commit()

    return {
        "status": "success",
        "message": f"Voyage {voy.voyage_number} reassigned to {vessel.name}",
        "vessel_assignment_status": voy.vessel_assignment_status,
        "capacity_teu": vessel.container_capacity,
        "deadweight_capacity_mt": vessel.deadweight_capacity_mt,
    }


# -------------------------------------------------------------
# 3. Voyage & Leg Management
# -------------------------------------------------------------
@router.get("/voyages")
def list_test_voyages(db: Session = Depends(get_test_db)):
    """Lists all voyages and legs from cargo_pilot_test.db with firm/provisional vessel assignment status."""
    voyages = db.query(models.Voyage).all()
    results = []
    for v in voyages:
        legs_data = []
        for l in v.legs:
            from_un = l.from_port_call.port.unlocode if l.from_port_call and l.from_port_call.port else "—"
            to_un = l.to_port_call.port.unlocode if l.to_port_call and l.to_port_call.port else "—"
            dep_d = (l.from_port_call.departure_time.date() - BASE_DATE).days if l.from_port_call else 0
            arr_d = (l.to_port_call.arrival_time.date() - BASE_DATE).days if l.to_port_call else dep_d + 5

            legs_data.append({
                "leg_id": str(l.id),
                "from_port": from_un,
                "to_port": to_un,
                "departure_day": dep_d,
                "arrival_day": arr_d,
                "capacity_teu": l.total_capacity,
                "booked_capacity_teu": l.booked_capacity,
                "deadweight_capacity_mt": l.deadweight_capacity_mt,
                "booked_weight_mt": l.booked_weight_mt,
            })

        results.append({
            "voyage_id": str(v.id),
            "voyage_number": v.voyage_number,
            "service_name": v.service.name if v.service else "—",
            "vessel_name": v.vessel.name if v.vessel else "UNASSIGNED",
            "vessel_assignment_status": v.vessel_assignment_status or "FIRM",
            "is_blank_sailing": v.is_blank_sailing,
            "status": v.status.value,
            "legs": legs_data,
        })
    return {"voyages": results}


@router.put("/voyages/{voyage_id}")
def update_voyage(voyage_id: str, payload: UpdateVoyageRequest, db: Session = Depends(get_test_db)):
    """Updates voyage status or marks/unmarks as blank sailing."""
    try:
        v_uuid = uuid.UUID(voyage_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid voyage UUID")

    voy = db.query(models.Voyage).filter(models.Voyage.id == v_uuid).first()
    if not voy:
        raise HTTPException(status_code=404, detail="Voyage not found")

    if payload.is_blank_sailing is not None:
        voy.is_blank_sailing = payload.is_blank_sailing
    if payload.status is not None:
        voy.status = payload.status

    db.commit()
    return {"status": "success", "message": f"Voyage {voy.voyage_number} updated", "is_blank_sailing": voy.is_blank_sailing}


@router.put("/voyage-legs/{leg_id}")
def update_voyage_leg(leg_id: str, payload: UpdateVoyageLegRequest, db: Session = Depends(get_test_db)):
    """Updates voyage leg timing or capacity."""
    try:
        l_uuid = uuid.UUID(leg_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid leg UUID")

    leg = db.query(models.VoyageLeg).filter(models.VoyageLeg.id == l_uuid).first()
    if not leg:
        raise HTTPException(status_code=404, detail="Voyage leg not found")

    if payload.capacity_teu is not None:
        leg.total_capacity = payload.capacity_teu
    if payload.capacity_weight_mt is not None:
        leg.deadweight_capacity_mt = payload.capacity_weight_mt
    if payload.booked_capacity_teu is not None:
        leg.booked_capacity = payload.booked_capacity_teu
    if payload.booked_weight_mt is not None:
        leg.booked_weight_mt = payload.booked_weight_mt

    if payload.departure_day is not None and leg.from_port_call:
        leg.from_port_call.departure_time = datetime.combine(
            BASE_DATE + timedelta(days=payload.departure_day), datetime.min.time(), tzinfo=timezone.utc
        )
    if payload.arrival_day is not None and leg.to_port_call:
        leg.to_port_call.arrival_time = datetime.combine(
            BASE_DATE + timedelta(days=payload.arrival_day), datetime.min.time(), tzinfo=timezone.utc
        )

    db.commit()
    return {"status": "success", "message": "Voyage leg updated successfully"}


# -------------------------------------------------------------
# 4. Bookings CRUD
# -------------------------------------------------------------
@router.get("/bookings")
def list_test_bookings(db: Session = Depends(get_test_db)):
    """Lists all bookings stored in cargo_pilot_test.db."""
    bookings = db.query(models.Booking).all()
    results = []
    for idx, b in enumerate(bookings):
        orig_un = b.origin_location.unlocode if b.origin_location else "—"
        dest_un = b.destination_location.unlocode if b.destination_location else "—"
        ready_d = (b.requested_pickup_date.date() - BASE_DATE).days if b.requested_pickup_date else 0
        cutoff_d = (b.booking_cutoff_at.date() - BASE_DATE).days if b.booking_cutoff_at else ready_d + 1
        deadline_d = (b.required_delivery_date.date() - BASE_DATE).days if b.required_delivery_date else ready_d + 20

        results.append({
            "id": str(b.id),
            "booking_code": f"BK-{idx+1:02d}",
            "origin": orig_un,
            "destination": dest_un,
            "container_type": b.container_type.value,
            "quantity": b.quantity,
            "cargo_weight_mt": b.cargo_weight_mt,
            "cargo_ready_day": ready_d,
            "cutoff_day": cutoff_d,
            "delivery_deadline_day": deadline_d,
            "priority": b.priority.value if b.priority else "NORMAL",
            "status": b.status.value if b.status else "CONFIRMED",
        })
    return {"bookings": results}


@router.post("/bookings")
def create_test_booking(payload: CreateBookingRequest, db: Session = Depends(get_test_db)):
    """Creates a new customer booking demand in cargo_pilot_test.db."""
    orig = db.query(models.Location).filter(models.Location.unlocode == payload.origin_unlocode).first()
    dest = db.query(models.Location).filter(models.Location.unlocode == payload.destination_unlocode).first()
    if not orig or not dest:
        raise HTTPException(status_code=400, detail="Invalid origin or destination port unlocode")

    carrier = db.query(models.Company).filter(models.Company.is_self == True).first()
    customer = db.query(models.Company).filter(models.Company.is_self == False).first()
    if not carrier or not customer:
        raise HTTPException(status_code=500, detail="Default company records missing in DB")

    ready_dt = datetime.combine(BASE_DATE + timedelta(days=payload.cargo_ready_day), datetime.min.time(), tzinfo=timezone.utc)
    cutoff_dt = datetime.combine(BASE_DATE + timedelta(days=payload.cutoff_day), datetime.min.time(), tzinfo=timezone.utc)
    deadline_dt = datetime.combine(BASE_DATE + timedelta(days=payload.delivery_deadline_day), datetime.min.time(), tzinfo=timezone.utc)

    booking = models.Booking(
        customer_company_id=customer.id,
        carrier_company_id=carrier.id,
        origin_location_id=orig.id,
        destination_location_id=dest.id,
        container_type=payload.container_type,
        quantity=payload.quantity,
        cargo_weight_mt=payload.cargo_weight_mt,
        requested_pickup_date=ready_dt,
        booking_cutoff_at=cutoff_dt,
        required_delivery_date=deadline_dt,
        priority=payload.priority,
        status=BookingStatus.CONFIRMED,
    )
    db.add(booking)
    db.commit()

    return {"status": "success", "message": "Booking created in test database", "booking_id": str(booking.id)}


@router.put("/bookings/{booking_id}")
def update_test_booking(booking_id: str, payload: UpdateBookingRequest, db: Session = Depends(get_test_db)):
    """Updates an existing booking in cargo_pilot_test.db."""
    try:
        b_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking UUID")

    b = db.query(models.Booking).filter(models.Booking.id == b_uuid).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")

    if payload.quantity is not None:
        b.quantity = payload.quantity
    if payload.cargo_weight_mt is not None:
        b.cargo_weight_mt = payload.cargo_weight_mt
    if payload.priority is not None:
        b.priority = payload.priority
    if payload.cargo_ready_day is not None:
        b.requested_pickup_date = datetime.combine(
            BASE_DATE + timedelta(days=payload.cargo_ready_day), datetime.min.time(), tzinfo=timezone.utc
        )
    if payload.cutoff_day is not None:
        b.booking_cutoff_at = datetime.combine(
            BASE_DATE + timedelta(days=payload.cutoff_day), datetime.min.time(), tzinfo=timezone.utc
        )
    if payload.delivery_deadline_day is not None:
        b.required_delivery_date = datetime.combine(
            BASE_DATE + timedelta(days=payload.delivery_deadline_day), datetime.min.time(), tzinfo=timezone.utc
        )

    db.commit()
    return {"status": "success", "message": "Booking updated successfully"}


@router.delete("/bookings/{booking_id}")
def delete_test_booking(booking_id: str, db: Session = Depends(get_test_db)):
    """Deletes a booking from cargo_pilot_test.db."""
    try:
        b_uuid = uuid.UUID(booking_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid booking UUID")

    b = db.query(models.Booking).filter(models.Booking.id == b_uuid).first()
    if not b:
        raise HTTPException(status_code=404, detail="Booking not found")

    db.delete(b)
    db.commit()
    return {"status": "success", "message": "Booking deleted"}


# -------------------------------------------------------------
# 5. Inventory & Container Adjustments
# -------------------------------------------------------------
@router.get("/inventory")
def list_test_inventory(db: Session = Depends(get_test_db)):
    """Returns available container stock by port and container type."""
    ports = db.query(models.Location).filter(models.Location.location_type == LocationType.PORT).all()
    results = []
    for p in ports:
        for ctype in [ContainerType.DRY_20FT, ContainerType.DRY_40FT, ContainerType.HIGH_CUBE_40FT]:
            count = (
                db.query(func.count(models.Container.id))
                .filter(
                    models.Container.current_location_id == p.id,
                    models.Container.container_type == ctype,
                    models.Container.status == ContainerStatus.AVAILABLE,
                )
                .scalar()
            )
            results.append({
                "port_unlocode": p.unlocode,
                "port_name": p.name,
                "container_type": ctype.value,
                "available_count": count or 0,
                "safety_stock": p.safety_stock_teu,
            })
    return {"inventory": results}


@router.post("/inventory/adjust")
def adjust_test_inventory(payload: AdjustInventoryRequest, db: Session = Depends(get_test_db)):
    """Adds or removes containers from a port depot in cargo_pilot_test.db."""
    loc = db.query(models.Location).filter(models.Location.unlocode == payload.port_unlocode).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Port location not found")

    carrier = db.query(models.Company).filter(models.Company.is_self == True).first()
    if not carrier:
        raise HTTPException(status_code=500, detail="Carrier company record missing")

    if payload.quantity_change > 0:
        # Add containers
        type_code = "20D" if payload.container_type == ContainerType.DRY_20FT else "40D" if payload.container_type == ContainerType.DRY_40FT else "40H"
        for i in range(payload.quantity_change):
            c_number = f"CP{payload.port_unlocode[:3]}{type_code}X{uuid.uuid4().hex[:8].upper()}"
            db.add(
                models.Container(
                    container_number=c_number,
                    container_type=payload.container_type,
                    owner_company_id=carrier.id,
                    current_location_id=loc.id,
                    status=ContainerStatus.AVAILABLE,
                    condition=ContainerCondition.CARGO_WORTHY,
                    controlled_by_carrier=True,
                )
            )
    elif payload.quantity_change < 0:
        # Remove available containers
        to_delete = (
            db.query(models.Container)
            .filter(
                models.Container.current_location_id == loc.id,
                models.Container.container_type == payload.container_type,
                models.Container.status == ContainerStatus.AVAILABLE,
            )
            .limit(abs(payload.quantity_change))
            .all()
        )
        for c in to_delete:
            db.delete(c)

    db.commit()

    new_count = (
        db.query(func.count(models.Container.id))
        .filter(
            models.Container.current_location_id == loc.id,
            models.Container.container_type == payload.container_type,
            models.Container.status == ContainerStatus.AVAILABLE,
        )
        .scalar()
    )

    return {
        "status": "success",
        "port": payload.port_unlocode,
        "container_type": payload.container_type.value,
        "new_available_count": new_count or 0,
    }


# -------------------------------------------------------------
# 6. Port / Location Settings
# -------------------------------------------------------------
@router.put("/ports/{unlocode}")
def update_port_settings(unlocode: str, payload: UpdatePortSettingsRequest, db: Session = Depends(get_test_db)):
    """Updates safety stock, storage capacity, or devanning lead time for a port."""
    loc = db.query(models.Location).filter(models.Location.unlocode == unlocode).first()
    if not loc:
        raise HTTPException(status_code=404, detail="Port location not found")

    if payload.safety_stock_teu is not None:
        loc.safety_stock_teu = payload.safety_stock_teu
    if payload.devanning_lead_time_days is not None:
        loc.devanning_lead_time_days = payload.devanning_lead_time_days
    if payload.storage_capacity_teu is not None:
        loc.storage_capacity = payload.storage_capacity_teu

    db.commit()
    return {"status": "success", "message": f"Port {unlocode} updated"}
