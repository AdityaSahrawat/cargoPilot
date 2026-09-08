"""
Allocation & 7-Day Lock Model
==============================
Observes container allocations (CargoPilot-owned), enforces the strict
7-day freeze cutoff, and guards against locked allocation mutations.

Doc 2 §9 — Allocation & 7-Day Lock Model:
    §9.1 — Responsibility: CargoPilot owns allocation decisions; simulator observes.
    §9.4 — Seven-Day Lock:
            T_cutoff = T_departure - 7 days
            Before cutoff (T < T_cutoff): Modifiable
            At or after cutoff (T ≥ T_cutoff): LOCKED (equality belongs to locked state)
    §9.5 — Locked Invariant:
            Allocation_{t+1} = Allocation_t
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import AllocationState, BookingState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §9.4, §9.5, §28)
# ---------------------------------------------------------------------------

def calculate_lock_cutoff_time(departure_time: datetime, lock_days: float = 7.0) -> datetime:
    """
    Calculate the exact cutoff time for the 7-day lock.
    Doc 2 §9.4:
        T_cutoff = T_departure - 7 days
    """
    return departure_time - timedelta(days=lock_days)


def is_allocation_locked(current_time: datetime, cutoff_time: datetime) -> bool:
    """
    Determine whether allocation is frozen.
    Doc 2 §9.4:
        T ≥ T_cutoff → LOCKED (equality belongs to locked state).
    """
    return current_time >= cutoff_time


# ---------------------------------------------------------------------------
# Allocation Model Class
# ---------------------------------------------------------------------------

class AllocationModel:
    """
    Domain model for observing CargoPilot container allocations and enforcing 7-day lock.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def evaluate_booking_locks(
        self,
        state: WorldState,
        sim_time: datetime,
    ) -> List[SimEvent]:
        """
        Check all active bookings against their departure cutoffs.
        If T_sim ≥ T_cutoff and booking is UNLOCKED:
            Transition to LOCKED
            Emit BOOKING_LOCKED event
        """
        events: List[SimEvent] = []

        for booking_id, booking in state.bookings.items():
            if booking.lock_status == "LOCKED":
                continue
            if booking.status in ("CANCELLED", "FULFILLED"):
                continue

            if booking.cutoff_time and is_allocation_locked(sim_time, booking.cutoff_time):
                booking.lock_status = "LOCKED"
                logger.info(
                    "Booking %s LOCKED at %s (cutoff was %s)",
                    booking_id,
                    sim_time.isoformat(),
                    booking.cutoff_time.isoformat(),
                )

                # Also lock associated allocation if present
                if booking.allocation_id and booking.allocation_id in state.allocations:
                    alloc = state.allocations[booking.allocation_id]
                    alloc.locked = True
                    alloc.status = "LOCKED"

                event = SimEvent(
                    event_type=EventType.BOOKING_LOCKED,
                    entity_type="booking",
                    entity_id=booking_id,
                    simulation_time=sim_time,
                    source="allocation_model",
                    world_id=state.world_id,
                    payload={
                        "booking_id": booking_id,
                        "voyage_id": booking.voyage_id,
                        "cutoff_time": booking.cutoff_time.isoformat(),
                        "locked_at": sim_time.isoformat(),
                    },
                )
                events.append(event)

        return events

    def observe_cargo_pilot_allocation(
        self,
        booking_id: str,
        container_id: str,
        voyage_id: str,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[AllocationState, SimEvent]:
        """
        Record an allocation decision issued by CargoPilot.
        Validates that booking is NOT currently locked.
        """
        if booking_id not in state.bookings:
            raise KeyError(f"Booking {booking_id} not found in world state")

        booking = state.bookings[booking_id]
        if booking.lock_status == "LOCKED":
            raise ValueError(
                f"Violation of 7-day lock: Booking {booking_id} is LOCKED; cannot modify allocation!"
            )

        allocation_id = f"AL-{booking_id}"
        alloc = AllocationState(
            allocation_id=allocation_id,
            booking_id=booking_id,
            container_id=container_id,
            voyage_id=voyage_id,
            status="ALLOCATED",
            locked=False,
        )
        state.allocations[allocation_id] = alloc
        booking.allocation_id = allocation_id
        booking.status = "ALLOCATED"

        event = SimEvent(
            event_type=EventType.ALLOCATION_COMMITTED,
            entity_type="allocation",
            entity_id=allocation_id,
            simulation_time=sim_time,
            source="cargo_pilot",
            world_id=state.world_id,
            payload={
                "allocation_id": allocation_id,
                "booking_id": booking_id,
                "container_id": container_id,
                "voyage_id": voyage_id,
            },
        )
        return alloc, event
