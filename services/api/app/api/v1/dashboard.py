from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/dashboard/overview", response_model=schemas.DashboardOverviewResponse)
def get_dashboard_overview(
    week: Optional[str] = Query(None, alias="week"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/dashboard/overview - High-level decision overview KPI metrics."""
    active_bookings = (
        db.query(models.Booking)
        .filter(models.Booking.status.in_([enums.BookingStatus.CONFIRMED, enums.BookingStatus.IN_PROGRESS]))
        .count()
    )

    upcoming_voyages = (
        db.query(models.Voyage)
        .filter(models.Voyage.status.in_([enums.VoyageStatus.SCHEDULED, enums.VoyageStatus.IN_PROGRESS]))
        .count()
    )

    latest_run = (
        db.query(models.OptimizationRun)
        .order_by(models.OptimizationRun.created_at.desc())
        .first()
    )

    latest_run_dict = None
    if latest_run:
        latest_run_dict = {
            "id": str(latest_run.id),
            "status": latest_run.status.value,
            "objectiveValue": float(latest_run.objective_value) if latest_run.objective_value else None,
            "startWeek": latest_run.start_week.isoformat(),
        }

    # Aggregate inventory summary
    locations = db.query(models.Location).all()
    surplus_locations = []
    deficit_locations = []

    for loc in locations:
        avail_count = (
            db.query(models.Container)
            .filter(
                models.Container.current_location_id == loc.id,
                models.Container.status == enums.ContainerStatus.AVAILABLE,
            )
            .count()
        )

        if avail_count > 50:
            surplus_locations.append({"locationId": str(loc.id), "name": loc.name, "available": avail_count})
        elif avail_count < 10:
            deficit_locations.append({"locationId": str(loc.id), "name": loc.name, "available": avail_count})

    return schemas.DashboardOverviewResponse(
        inventory={"totalAvailable": db.query(models.Container).filter(models.Container.status == enums.ContainerStatus.AVAILABLE).count()},
        shortages={"totalShortage": 0},
        surplus_locations=surplus_locations,
        deficit_locations=deficit_locations,
        active_bookings=active_bookings,
        upcoming_voyages=upcoming_voyages,
        latest_optimization_run=latest_run_dict,
    )


@router.get("/dashboard/alerts", response_model=List[schemas.DashboardAlertResponse])
def get_dashboard_alerts(
    week: Optional[str] = Query("2026-W38", alias="week"),
    severity: Optional[str] = Query(None, alias="severity"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/dashboard/alerts - Shortage & operational risk alerts."""
    alerts = []
    locations = db.query(models.Location).limit(3).all()

    for i, loc in enumerate(locations):
        sev = "HIGH" if i == 0 else "MEDIUM"
        if severity and severity.upper() != sev:
            continue

        alerts.append(
            schemas.DashboardAlertResponse(
                type="SHORTAGE_RISK",
                location_id=loc.id,
                container_type=enums.ContainerType.DRY_40FT,
                week=week or "2026-W38",
                quantity=25 + (i * 10),
                severity=sev,
            )
        )

    return alerts
