from typing import List
from sqlalchemy.orm import Session

from app.db import models, schemas


class WorldValidator:
    """Enforces mathematical invariants and consistency rules on CargoPilot plans."""

    def __init__(self, db: Session):
        self.db = db

    def validate_plan_capacity(self, plan: schemas.OptimizationPlanResponse):
        """Invariant 1: Repositioning quantity + booked capacity <= Leg total capacity."""
        for item in plan.repositioning:
            leg = self.db.query(models.VoyageLeg).filter(models.VoyageLeg.id == item.voyage_leg_id).first()
            if leg:
                total_loaded = leg.booked_capacity + item.quantity
                assert total_loaded <= leg.total_capacity, (
                    f"Capacity Invariant Violated on Leg {leg.id}: "
                    f"booked ({leg.booked_capacity}) + repo ({item.quantity}) > total ({leg.total_capacity})"
                )

    def validate_non_negative_quantities(self, plan: schemas.OptimizationPlanResponse):
        """Invariant 2: Quantities in repositioning, leasing, inventory, and demand must be non-negative."""
        for item in plan.repositioning:
            assert item.quantity >= 0, f"Negative repositioning quantity: {item.quantity}"
        for item in plan.leasing:
            assert item.quantity >= 0, f"Negative leasing quantity: {item.quantity}"
        for item in plan.inventory:
            assert item.quantity >= 0, f"Negative inventory quantity: {item.quantity}"
        for item in plan.demand:
            assert item.confirmed_served >= 0 and item.forecast_served >= 0

    def validate_container_assignments(self):
        """Invariant 3: No single container has multiple active unreleased assignments."""
        active_assignments = (
            self.db.query(models.EquipmentAssignment)
            .filter(models.EquipmentAssignment.released_at.is_(None))
            .all()
        )
        assigned_containers = set()
        for assign in active_assignments:
            assert assign.container_id not in assigned_containers, (
                f"Single Assignment Invariant Violated: Container {assign.container_id} has multiple active assignments"
            )
            assigned_containers.add(assign.container_id)
