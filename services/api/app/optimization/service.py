import uuid
from datetime import datetime, date
from typing import Optional, List
from sqlalchemy.orm import Session

from app.db import models, enums, schemas
from app.optimization.input_builder import OptimizationInputBuilder
from app.optimization.solver import Solver
from app.optimization.models import OptimizationResult


class OptimizationService:
    """Orchestrates optimization runs: API -> Service -> InputBuilder -> Solver -> DB persistence."""

    def __init__(self, db: Session):
        self.db = db
        self.input_builder = OptimizationInputBuilder(db)
        self.solver = Solver()

    def run_optimization(
        self,
        company_id: uuid.UUID,
        start_week: str,
        horizon_weeks: int,
        container_types: Optional[List[enums.ContainerType]] = None,
        location_ids: Optional[List[uuid.UUID]] = None,
    ) -> models.OptimizationRun:
        # 1. Create OptimizationRun record
        # Parse date if string, e.g. "2026-W35" -> fallback to date
        try:
            start_date = date.fromisoformat(start_week)
        except ValueError:
            start_date = date.today()

        opt_run = models.OptimizationRun(
            company_id=company_id,
            start_week=start_date,
            horizon_weeks=horizon_weeks,
            status=enums.OptimizationStatus.RUNNING,
        )
        self.db.add(opt_run)
        self.db.commit()
        self.db.refresh(opt_run)

        try:
            # 2. Build inputs
            inp = self.input_builder.build_input(
                company_id=company_id,
                start_week=start_week,
                horizon_weeks=horizon_weeks,
                container_types=container_types,
                location_ids=location_ids,
            )

            # 3. Solve
            result: OptimizationResult = self.solver.solve(inp)

            # 4. Persist results
            opt_run.objective_value = result.objective_value
            opt_run.status = enums.OptimizationStatus.COMPLETED
            opt_run.completed_at = datetime.utcnow()

            # Save repositioning
            for r in result.repositioning:
                self.db.add(
                    models.OptimizationReposition(
                        run_id=opt_run.id,
                        voyage_leg_id=r.voyage_leg_id,
                        container_type=r.container_type,
                        quantity=r.quantity,
                        departure_week=start_date,
                    )
                )

            # Save leasing
            for l in result.leasing:
                self.db.add(
                    models.OptimizationLease(
                        run_id=opt_run.id,
                        lease_id=l.lease_id,
                        location_id=l.location_id,
                        container_type=l.container_type,
                        quantity=l.quantity,
                        week=start_date,
                    )
                )

            # Save inventory
            for inv in result.inventory:
                self.db.add(
                    models.OptimizationInventory(
                        run_id=opt_run.id,
                        location_id=inv.location_id,
                        container_type=inv.container_type,
                        week=start_date,
                        quantity=inv.quantity,
                    )
                )

            # Save demand
            for d in result.demand:
                self.db.add(
                    models.OptimizationDemand(
                        run_id=opt_run.id,
                        location_id=d.location_id,
                        container_type=d.container_type,
                        week=start_date,
                        confirmed_served=d.confirmed_served,
                        forecast_served=d.forecast_served,
                        forecast_backlog=d.forecast_backlog,
                        confirmed_shortage=d.confirmed_shortage,
                    )
                )

            self.db.commit()
            self.db.refresh(opt_run)

        except Exception as e:
            opt_run.status = enums.OptimizationStatus.FAILED
            self.db.commit()
            raise e

        return opt_run

    def get_plan(self, run_id: uuid.UUID) -> schemas.OptimizationPlanResponse:
        run = self.db.query(models.OptimizationRun).filter(models.OptimizationRun.id == run_id).first()
        if not run:
            raise ValueError(f"Optimization run {run_id} not found")

        week_str = run.start_week.isoformat()

        repositioning = []
        for r in run.repositions:
            repositioning.append(
                schemas.RepositioningPlanItem(
                    week=week_str,
                    voyage_leg_id=r.voyage_leg_id,
                    from_location_id=r.voyage_leg.from_port_call.port_id if r.voyage_leg and r.voyage_leg.from_port_call else None,
                    to_location_id=r.voyage_leg.to_port_call.port_id if r.voyage_leg and r.voyage_leg.to_port_call else None,
                    container_type=r.container_type,
                    quantity=r.quantity,
                    cost=50.0 * r.quantity,
                )
            )

        leasing = []
        for l in run.leases:
            leasing.append(
                schemas.LeasingPlanItem(
                    week=week_str,
                    location_id=l.location_id,
                    container_type=l.container_type,
                    quantity=l.quantity,
                    cost=40.0 * l.quantity,
                )
            )

        inventory = []
        for inv in run.inventories:
            inventory.append(
                schemas.InventoryPlanItem(
                    week=week_str,
                    location_id=inv.location_id,
                    container_type=inv.container_type,
                    quantity=inv.quantity,
                )
            )

        demand = []
        for d in run.demands:
            demand.append(
                schemas.DemandPlanItem(
                    week=week_str,
                    location_id=d.location_id,
                    container_type=d.container_type,
                    confirmed_demand=d.confirmed_served + d.confirmed_shortage,
                    confirmed_served=d.confirmed_served,
                    forecast_demand=d.forecast_served + d.forecast_backlog,
                    forecast_served=d.forecast_served,
                    forecast_backlog=d.forecast_backlog,
                    confirmed_shortage=d.confirmed_shortage,
                )
            )

        return schemas.OptimizationPlanResponse(
            run_id=run.id,
            total_cost=float(run.objective_value) if run.objective_value else 0.0,
            repositioning=repositioning,
            leasing=leasing,
            inventory=inventory,
            demand=demand,
        )
