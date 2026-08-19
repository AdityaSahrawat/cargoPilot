from typing import Optional, List
from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db

router = APIRouter()


@router.get("/demand/forecast", response_model=List[schemas.DemandForecastResponse])
def get_demand_forecasts(
    location_id: Optional[UUID] = Query(None, alias="locationId"),
    container_type: Optional[enums.ContainerType] = Query(None, alias="containerType"),
    from_week: Optional[str] = Query(None, alias="fromWeek"),
    to_week: Optional[str] = Query(None, alias="toWeek"),
    db: Session = Depends(get_db),
):
    """GET /api/v1/demand/forecast - Query expected future demand forecasts."""
    query = db.query(models.DemandForecast)

    if location_id:
        query = query.filter(models.DemandForecast.location_id == location_id)
    if container_type:
        query = query.filter(models.DemandForecast.container_type == container_type)

    forecasts = query.all()

    # Format week strings for response
    results = []
    for f in forecasts:
        week_str = f.week if isinstance(f.week, str) else f.week.isoformat()
        results.append(
            schemas.DemandForecastResponse(
                id=f.id,
                company_id=f.company_id,
                location_id=f.location_id,
                container_type=f.container_type,
                week=week_str,
                quantity=f.quantity,
                confidence=f.confidence,
                created_at=f.created_at,
                updated_at=f.updated_at,
            )
        )
    return results


@router.post("/demand/forecast", response_model=schemas.DemandForecastResponse, status_code=status.HTTP_201_CREATED)
def create_demand_forecast(
    body: schemas.DemandForecastCreate,
    db: Session = Depends(get_db),
):
    """POST /api/v1/demand/forecast - Create a manual or synthetic demand forecast."""
    company_id = body.company_id
    if not company_id:
        c = db.query(models.Company).filter(models.Company.is_self == True).first()
        if not c:
            c = db.query(models.Company).first()
        if not c:
            c = models.Company(
                name="CargoPilot Carrier",
                company_type=enums.CompanyType.CARRIER,
                is_self=True,
            )
            db.add(c)
            db.commit()
            db.refresh(c)
        company_id = c.id

    try:
        week_date = date.fromisoformat(body.week)
    except ValueError:
        week_date = date.today()

    forecast = models.DemandForecast(
        company_id=company_id,
        location_id=body.location_id,
        container_type=body.container_type,
        week=week_date,
        quantity=body.quantity,
        confidence=body.confidence,
    )
    db.add(forecast)
    db.commit()
    db.refresh(forecast)

    week_str = forecast.week if isinstance(forecast.week, str) else forecast.week.isoformat()

    return schemas.DemandForecastResponse(
        id=forecast.id,
        company_id=forecast.company_id,
        location_id=forecast.location_id,
        container_type=forecast.container_type,
        week=week_str,
        quantity=forecast.quantity,
        confidence=forecast.confidence,
        created_at=forecast.created_at,
        updated_at=forecast.updated_at,
    )


@router.patch("/demand/forecast/{forecast_id}", response_model=schemas.DemandForecastResponse)
def update_demand_forecast(
    forecast_id: UUID,
    body: schemas.DemandForecastUpdate,
    db: Session = Depends(get_db),
):
    """PATCH /api/v1/demand/forecast/:id - Update an existing demand forecast."""
    forecast = db.query(models.DemandForecast).filter(models.DemandForecast.id == forecast_id).first()
    if not forecast:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Demand forecast {forecast_id} not found",
        )

    if body.location_id is not None:
        forecast.location_id = body.location_id
    if body.container_type is not None:
        forecast.container_type = body.container_type
    if body.week is not None:
        try:
            forecast.week = date.fromisoformat(body.week)
        except ValueError:
            pass
    if body.quantity is not None:
        forecast.quantity = body.quantity
    if body.confidence is not None:
        forecast.confidence = body.confidence

    db.commit()
    db.refresh(forecast)

    week_str = forecast.week if isinstance(forecast.week, str) else forecast.week.isoformat()

    return schemas.DemandForecastResponse(
        id=forecast.id,
        company_id=forecast.company_id,
        location_id=forecast.location_id,
        container_type=forecast.container_type,
        week=week_str,
        quantity=forecast.quantity,
        confidence=forecast.confidence,
        created_at=forecast.created_at,
        updated_at=forecast.updated_at,
    )
