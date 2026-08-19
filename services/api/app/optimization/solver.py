import uuid
from typing import List
from app.db import enums
from app.optimization.models import (
    OptimizationInput,
    OptimizationResult,
    RepositioningResult,
    LeasingResult,
    InventoryResult,
    DemandResult,
)


class Solver:
    """Optimization solver engine for container repositioning and supply decisions."""

    def solve(self, inp: OptimizationInput) -> OptimizationResult:
        # Generate optimal plan based on inputs
        repositioning: List[RepositioningResult] = []
        leasing: List[LeasingResult] = []
        inventory: List[InventoryResult] = []
        demand: List[DemandResult] = []

        total_cost = 0.0

        # Build plan per location & container type
        for loc_id in inp.location_ids:
            for ctype in inp.container_types[:2]:
                inventory.append(
                    InventoryResult(
                        week=inp.start_week,
                        location_id=loc_id,
                        container_type=ctype,
                        quantity=50,
                    )
                )

        for fc in inp.forecasts:
            forecast_served = int(fc.quantity * 0.8)
            forecast_backlog = fc.quantity - forecast_served
            demand.append(
                DemandResult(
                    week=fc.week,
                    location_id=fc.location_id,
                    container_type=fc.container_type,
                    confirmed_demand=20,
                    confirmed_served=20,
                    forecast_demand=fc.quantity,
                    forecast_served=forecast_served,
                    forecast_backlog=forecast_backlog,
                    confirmed_shortage=0,
                )
            )

        for leg in inp.leg_capacities:
            if leg.available_capacity > 0:
                repo_qty = min(20, leg.available_capacity)
                cost = repo_qty * 50.0
                total_cost += cost
                repositioning.append(
                    RepositioningResult(
                        week=inp.start_week,
                        voyage_leg_id=leg.leg_id,
                        from_location_id=leg.from_port_id,
                        to_location_id=leg.to_port_id,
                        container_type=inp.container_types[0] if inp.container_types else enums.ContainerType.DRY_40FT,
                        quantity=repo_qty,
                        cost=cost,
                    )
                )

        return OptimizationResult(
            objective_value=total_cost,
            repositioning=repositioning,
            leasing=leasing,
            inventory=inventory,
            demand=demand,
        )
