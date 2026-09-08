"""
Leasing Model
=============
Executes container leasing decisions issued by CargoPilot and tracks lease costs.

Doc 2 §12 — Leasing Model:
    §12.1 — Responsibility: CargoPilot decides whether to lease; simulator executes.
    §12.3 — Execution:
            CargoPilot Decision → Lease Order → Start Delay → Equipment Added
    §12.4 — Cost:
            LeaseCost = Q × Rate × Duration
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import LeaseState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §12.4, §28)
# ---------------------------------------------------------------------------

def calculate_lease_cost(
    quantity: int,
    daily_rate: float,
    duration_days: float,
) -> float:
    """
    Calculate total lease cost.
    Doc 2 §12.4:
        LeaseCost = Q × Rate × Duration
    """
    return max(0.0, float(quantity) * daily_rate * duration_days)


# ---------------------------------------------------------------------------
# Leasing Model Class
# ---------------------------------------------------------------------------

class LeasingModel:
    """
    Domain model for executing CargoPilot container lease orders.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def order_lease(
        self,
        lease_id: str,
        location_id: str,
        equipment_type: str,
        quantity: int,
        daily_rate: float,
        duration_days: float,
        sim_time: datetime,
        state: WorldState,
        start_delay_days: Optional[float] = None,
    ) -> Tuple[LeaseState, datetime, SimEvent]:
        """
        Process incoming lease order from CargoPilot.
        Calculates equipment availability timestamp and lease cost.
        """
        if start_delay_days is None:
            try:
                start_delay_days = float(self._reg.get("LEASE_START_DELAY"))
            except KeyError:
                start_delay_days = 1.0

        available_at = sim_time + timedelta(days=start_delay_days)
        cost = calculate_lease_cost(quantity, daily_rate, duration_days)

        lease = LeaseState(
            lease_id=lease_id,
            location_id=location_id,
            equipment_type=equipment_type,
            quantity=quantity,
            daily_rate=daily_rate,
            start_time=sim_time,
            duration_days=duration_days,
            status="PENDING",
            equipment_available_at=available_at,
        )
        state.leases[lease_id] = lease
        state.kpis.total_lease_cost += cost

        logger.info(
            "Lease %s ORDERED: %d × %s at %s (cost=$%.2f, avail at %s)",
            lease_id,
            quantity,
            equipment_type,
            location_id,
            cost,
            available_at.isoformat(),
        )

        event = SimEvent(
            event_type=EventType.LEASE_COST_INCURRED,
            entity_type="lease",
            entity_id=lease_id,
            simulation_time=sim_time,
            source="leasing_model",
            world_id=state.world_id,
            payload={
                "lease_id": lease_id,
                "location_id": location_id,
                "equipment_type": equipment_type,
                "quantity": quantity,
                "total_cost": cost,
                "available_at": available_at.isoformat(),
            },
        )
        return lease, available_at, event

    def activate_leased_equipment(
        self,
        lease: LeaseState,
        sim_time: datetime,
        state: WorldState,
    ) -> SimEvent:
        """
        Add leased equipment into available inventory after start delay.
        Doc 2 §12.3: Equipment Added → Available Equipment
        """
        lease.status = "ACTIVE"
        bal = state.get_equipment(lease.location_id, lease.equipment_type)
        bal.available += lease.quantity

        logger.info(
            "Lease %s ACTIVATED: +%d %s to pool at %s (available now=%d)",
            lease.lease_id,
            lease.quantity,
            lease.equipment_type,
            lease.location_id,
            bal.available,
        )

        return SimEvent(
            event_type=EventType.LEASE_EQUIPMENT_AVAILABLE,
            entity_type="lease",
            entity_id=lease.lease_id,
            simulation_time=sim_time,
            source="leasing_model",
            world_id=state.world_id,
            payload={
                "lease_id": lease.lease_id,
                "location_id": lease.location_id,
                "equipment_type": lease.equipment_type,
                "quantity_added": lease.quantity,
                "pool_available": bal.available,
            },
        )
