from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db import models, schemas, enums
from app.db.database import get_db
from app.optimization.service import OptimizationService

router = APIRouter()


@router.post("/optimization/runs", response_model=schemas.OptimizationRunStartResponse, status_code=status.HTTP_201_CREATED)
def start_optimization_run(
    body: schemas.OptimizationRunRequest,
    db: Session = Depends(get_db),
):
    """POST /api/v1/optimization/runs - Start an optimization run."""
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

    opt_service = OptimizationService(db)
    opt_run = opt_service.run_optimization(
        company_id=c.id,
        start_week=body.start_week,
        horizon_weeks=body.horizon_weeks,
        container_types=body.container_types,
        location_ids=body.location_ids,
    )

    return schemas.OptimizationRunStartResponse(
        run_id=opt_run.id,
        status=opt_run.status,
    )


@router.get("/optimization/runs", response_model=List[schemas.OptimizationRunResponse])
def list_optimization_runs(
    status_filter: Optional[enums.OptimizationStatus] = Query(None, alias="status"),
    from_date: Optional[datetime] = Query(None, alias="fromDate"),
    to_date: Optional[datetime] = Query(None, alias="toDate"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """GET /api/v1/optimization/runs - List previous optimization runs."""
    query = db.query(models.OptimizationRun)

    if status_filter:
        query = query.filter(models.OptimizationRun.status == status_filter)
    if from_date:
        query = query.filter(models.OptimizationRun.created_at >= from_date)
    if to_date:
        query = query.filter(models.OptimizationRun.created_at <= to_date)

    offset = (page - 1) * limit
    runs = query.order_by(models.OptimizationRun.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for r in runs:
        week_str = r.start_week if isinstance(r.start_week, str) else r.start_week.isoformat()
        results.append(
            schemas.OptimizationRunResponse(
                id=r.id,
                company_id=r.company_id,
                start_week=week_str,
                horizon_weeks=r.horizon_weeks,
                status=r.status,
                objective_value=float(r.objective_value) if r.objective_value else None,
                created_at=r.created_at,
                completed_at=r.completed_at,
            )
        )
    return results


@router.get("/optimization/runs/{run_id}", response_model=schemas.OptimizationRunResponse)
def get_optimization_run_by_id(run_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/optimization/runs/:id - Optimization run status & details."""
    run = db.query(models.OptimizationRun).filter(models.OptimizationRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization run {run_id} not found",
        )

    week_str = run.start_week if isinstance(run.start_week, str) else run.start_week.isoformat()
    return schemas.OptimizationRunResponse(
        id=run.id,
        company_id=run.company_id,
        start_week=week_str,
        horizon_weeks=run.horizon_weeks,
        status=run.status,
        objective_value=float(run.objective_value) if run.objective_value else None,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )


@router.get("/optimization/runs/{run_id}/plan", response_model=schemas.OptimizationPlanResponse)
def get_optimization_plan(run_id: UUID, db: Session = Depends(get_db)):
    """GET /api/v1/optimization/runs/:id/plan - Get complete recommended plan."""
    opt_service = OptimizationService(db)
    try:
        plan = opt_service.get_plan(run_id)
        return plan
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/optimization/runs/{run_id}/approve", response_model=schemas.OptimizationRunApproveResponse)
def approve_optimization_plan(
    run_id: UUID,
    body: schemas.OptimizationRunApproveRequest = schemas.OptimizationRunApproveRequest(),
    db: Session = Depends(get_db),
):
    """POST /api/v1/optimization/runs/:id/approve - Approve generated optimization plan."""
    run = db.query(models.OptimizationRun).filter(models.OptimizationRun.id == run_id).first()
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Optimization run {run_id} not found",
        )

    return schemas.OptimizationRunApproveResponse(
        run_id=run.id,
        status="APPROVED",
        approved_at=datetime.utcnow(),
    )
