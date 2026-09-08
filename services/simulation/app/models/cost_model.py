"""
Cost Accounting Model
=====================
Computes and accumulates simulation operational costs, ensuring compatibility
with CargoPilot's MILP optimization objective function.

Doc 2 §22 — Cost Models:
    §22.2 — TotalCost = ∑ Cost_i
    §22.3 — DelayCost = DelayDuration × CostPerHour
    §22.4 — LeaseCost = Quantity × Rate × Duration
    §22.5 — RepositioningCost = Quantity × CostPerContainer
    §22.6 — StorageCost = ContainerCount × Days × CostPerDay
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import KPIAccumulator, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §22.2 - §22.6, §28)
# ---------------------------------------------------------------------------

def calculate_delay_cost(delay_hours: float, cost_per_hour: float) -> float:
    """Doc 2 §22.3: DelayCost = DelayDuration × CostPerHour"""
    return max(0.0, delay_hours * cost_per_hour)


def calculate_storage_cost(container_count: int, days: float, cost_per_day: float) -> float:
    """Doc 2 §22.6: StorageCost = ContainerCount × Days × CostPerDay"""
    return max(0.0, float(container_count) * days * cost_per_day)


def calculate_shortage_cost(shortage_count: int, cost_per_container: float) -> float:
    """Doc 2 §22.7: ShortageCost = ShortageCount × CostPerContainer"""
    return max(0.0, float(shortage_count) * cost_per_container)


# ---------------------------------------------------------------------------
# Cost Model Class
# ---------------------------------------------------------------------------

class CostModel:
    """
    Domain model for accumulating operational costs and emitting accounting events.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def record_delay_cost(
        self,
        vessel_id: str,
        delay_hours: float,
        sim_time: datetime,
        state: WorldState,
    ) -> Optional[SimEvent]:
        """Record vessel delay cost."""
        if delay_hours <= 0:
            return None

        try:
            rate = float(self._reg.get("VESSEL_DELAY_COST_PER_HOUR"))
        except KeyError:
            rate = 1500.0

        cost = calculate_delay_cost(delay_hours, rate)
        state.kpis.total_delay_cost += cost

        logger.info(
            "Vessel %s DELAY COST: %.1fh × $%.2f/h = $%.2f",
            vessel_id,
            delay_hours,
            rate,
            cost,
        )

        return SimEvent(
            event_type=EventType.DELAY_COST_INCURRED,
            entity_type="vessel",
            entity_id=vessel_id,
            simulation_time=sim_time,
            source="cost_model",
            world_id=state.world_id,
            payload={
                "vessel_id": vessel_id,
                "delay_hours": delay_hours,
                "rate_per_hour": rate,
                "cost": cost,
            },
        )

    def record_storage_cost(
        self,
        location_id: str,
        container_count: int,
        days: float,
        sim_time: datetime,
        state: WorldState,
    ) -> Optional[SimEvent]:
        """Record container yard storage cost."""
        if container_count <= 0 or days <= 0:
            return None

        try:
            rate = float(self._reg.get("STORAGE_COST_PER_DAY"))
        except KeyError:
            rate = 25.0

        cost = calculate_storage_cost(container_count, days, rate)
        state.kpis.total_storage_cost += cost

        return SimEvent(
            event_type=EventType.STORAGE_COST_INCURRED,
            entity_type="port",
            entity_id=location_id,
            simulation_time=sim_time,
            source="cost_model",
            world_id=state.world_id,
            payload={
                "location_id": location_id,
                "container_count": container_count,
                "days": days,
                "rate_per_day": rate,
                "cost": cost,
            },
        )

    def record_shortage_penalty(
        self,
        location_id: str,
        equipment_type: str,
        shortage_count: int,
        sim_time: datetime,
        state: WorldState,
    ) -> Optional[SimEvent]:
        """Record penalty incurred from equipment shortage."""
        if shortage_count <= 0:
            return None

        try:
            penalty_rate = float(self._reg.get("SHORTAGE_COST_PER_CONTAINER"))
        except KeyError:
            penalty_rate = 500.0

        penalty = calculate_shortage_cost(shortage_count, penalty_rate)
        state.kpis.total_shortage_penalty += penalty

        return SimEvent(
            event_type=EventType.SHORTAGE_PENALTY_INCURRED,
            entity_type="equipment",
            entity_id=f"{location_id}_{equipment_type}",
            simulation_time=sim_time,
            source="cost_model",
            world_id=state.world_id,
            payload={
                "location_id": location_id,
                "equipment_type": equipment_type,
                "shortage_count": shortage_count,
                "penalty_per_container": penalty_rate,
                "total_penalty": penalty,
            },
        )
