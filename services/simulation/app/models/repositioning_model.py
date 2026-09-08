"""
Repositioning Model
===================
Executes empty container repositioning movements between surplus and deficit ports.

Doc 2 §13 — Repositioning Model:
    §13.2 — Responsibility: CargoPilot decides; simulator executes.
    §13.3 — Execution Flow:
            Decision → Source Inventory Decrease → In Transit → Transit Time → Destination Inventory Increase
    §13.4 — Parameters & Cost:
            RepositioningCost = Quantity × CostPerContainer
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import RepositioningState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §13.4, §28)
# ---------------------------------------------------------------------------

def calculate_repositioning_cost(
    quantity: int,
    cost_per_container: float,
) -> float:
    """
    Calculate repositioning cost.
    Doc 2 §13.4, §28:
        RepositioningCost = Quantity × CostPerContainer
    """
    return max(0.0, float(quantity) * cost_per_container)


# ---------------------------------------------------------------------------
# Repositioning Model Class
# ---------------------------------------------------------------------------

class RepositioningModel:
    """
    Domain model for executing CargoPilot empty repositioning movements.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def dispatch_repositioning(
        self,
        reposition_id: str,
        source_location_id: str,
        destination_location_id: str,
        equipment_type: str,
        quantity: int,
        transit_days: float,
        cost_per_container: float,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[RepositioningState, datetime, SimEvent]:
        """
        Dispatch empty repositioning movement from source location.
        Decreases source available inventory, places into in_transit.
        """
        src_bal = state.get_equipment(source_location_id, equipment_type)
        if src_bal.available < quantity:
            logger.warning(
                "Repositioning order %s: source %s has only %d available, requested %d",
                reposition_id,
                source_location_id,
                src_bal.available,
                quantity,
            )

        src_bal.available = max(0, src_bal.available - quantity)
        src_bal.in_transit += quantity

        eta = sim_time + timedelta(days=max(0.5, transit_days))
        cost = calculate_repositioning_cost(quantity, cost_per_container)
        state.kpis.total_repositioning_cost += cost

        order = RepositioningState(
            reposition_id=reposition_id,
            source_location_id=source_location_id,
            destination_location_id=destination_location_id,
            equipment_type=equipment_type,
            quantity=quantity,
            departure_time=sim_time,
            estimated_arrival=eta,
            status="IN_TRANSIT",
        )
        state.repositioning_orders[reposition_id] = order

        logger.info(
            "Repositioning %s DISPATCHED: %d × %s from %s → %s (ETA=%s, cost=$%.2f)",
            reposition_id,
            quantity,
            equipment_type,
            source_location_id,
            destination_location_id,
            eta.isoformat(),
            cost,
        )

        event = SimEvent(
            event_type=EventType.REPOSITIONING_DISPATCHED,
            entity_type="repositioning",
            entity_id=reposition_id,
            simulation_time=sim_time,
            source="repositioning_model",
            world_id=state.world_id,
            payload={
                "reposition_id": reposition_id,
                "source_location_id": source_location_id,
                "destination_location_id": destination_location_id,
                "equipment_type": equipment_type,
                "quantity": quantity,
                "estimated_arrival": eta.isoformat(),
                "cost": cost,
            },
        )
        return order, eta, event

    def complete_repositioning(
        self,
        order: RepositioningState,
        sim_time: datetime,
        state: WorldState,
    ) -> SimEvent:
        """
        Complete repositioning: removes from in_transit, adds to destination available pool.
        Doc 2 §13.3: Destination Inventory Increase
        """
        order.status = "COMPLETED"

        src_bal = state.get_equipment(order.source_location_id, order.equipment_type)
        src_bal.in_transit = max(0, src_bal.in_transit - order.quantity)

        dest_bal = state.get_equipment(order.destination_location_id, order.equipment_type)
        dest_bal.available += order.quantity

        logger.info(
            "Repositioning %s COMPLETED: +%d %s at destination %s (available now=%d)",
            order.reposition_id,
            order.quantity,
            order.equipment_type,
            order.destination_location_id,
            dest_bal.available,
        )

        return SimEvent(
            event_type=EventType.REPOSITIONING_COMPLETED,
            entity_type="repositioning",
            entity_id=order.reposition_id,
            simulation_time=sim_time,
            source="repositioning_model",
            world_id=state.world_id,
            payload={
                "reposition_id": order.reposition_id,
                "destination_location_id": order.destination_location_id,
                "equipment_type": order.equipment_type,
                "quantity": order.quantity,
                "pool_available": dest_bal.available,
            },
        )
