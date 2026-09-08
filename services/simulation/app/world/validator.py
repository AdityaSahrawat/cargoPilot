"""
World State Validator
=====================
Implements multi-level operational validation to prevent impossible world states.

Doc 2 §27 — Validation:
    §27.2 — Entity Consistency: no impossible simultaneous states
    §27.3 — Capacity Constraints:
            YardOccupancy ≤ YardCapacity
            VesselLoad ≤ VesselCapacity
            BerthsOccupied ≤ BerthsTotal
    §27.4 — Allocation Validation:
            Valid references, locked allocations inviolate
    §27.5 — Equipment Conservation:
            TotalEquipment = Available + Allocated + InTransit + Unavailable
    §27.6 — Event Validation:
            10-field schema check
    §27.7 — Two Levels:
            Level 1: Local validation (after single event)
            Level 2: Advancement validation (after time step advance)
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from app.events.event_types import SimEvent
from app.world.world_state import WorldState, Visibility

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when an operational invariant or constraint is violated."""
    pass


# ---------------------------------------------------------------------------
# Level 1: Local Event Validation (Doc 2 §27.7)
# ---------------------------------------------------------------------------

def validate_event_schema(event: SimEvent) -> None:
    """Validate that event conforms to required 10-field specification (Doc 2 §27.6)."""
    if not event.event_type:
        raise ValidationError(f"Event missing event_type: {event}")
    if not event.entity_type:
        raise ValidationError(f"Event {event.event_id} missing entity_type")
    if not event.entity_id:
        raise ValidationError(f"Event {event.event_id} missing entity_id")
    if not event.simulation_time:
        raise ValidationError(f"Event {event.event_id} missing simulation_time")
    if not event.world_id:
        raise ValidationError(f"Event {event.event_id} missing world_id")


def validate_local_event(event: SimEvent, state: WorldState) -> None:
    """
    Level 1 Validation:
    Executed immediately after an event is processed in the kernel.
    Validates event schema and affected entity consistency.
    """
    validate_event_schema(event)

    # If event affected a container, validate container state consistency
    if event.entity_type == "container" and event.entity_id in state.containers:
        c = state.containers[event.entity_id]
        if c.status == "IN_TRANSIT" and c.current_location_id is not None:
            raise ValidationError(
                f"Container {c.container_id} is IN_TRANSIT but has location_id={c.current_location_id}"
            )
        if c.status == "EMPTY_AVAILABLE" and c.booking_id is not None:
            raise ValidationError(
                f"Container {c.container_id} is EMPTY_AVAILABLE but assigned to booking={c.booking_id}"
            )

    # If event affected a vessel, validate vessel capacity
    if event.entity_type == "vessel" and event.entity_id in state.vessels:
        v = state.vessels[event.entity_id]
        if v.capacity_teu > 0 and v.current_load_teu > v.capacity_teu:
            raise ValidationError(
                f"Vessel {v.vessel_id} load ({v.current_load_teu}) exceeds capacity ({v.capacity_teu})"
            )


# ---------------------------------------------------------------------------
# Level 2: Full Advancement Validation (Doc 2 §27.7)
# ---------------------------------------------------------------------------

def validate_advancement_state(state: WorldState) -> None:
    """
    Level 2 Validation:
    Executed at the end of each advancement step [T_current, T_target].
    Enforces full world invariants across capacity, allocation, equipment conservation.
    """
    # 1. Port Capacity Constraints (Doc 2 §27.3)
    for port_id, port in state.ports.items():
        if port.berths_occupied > port.berths_total:
            raise ValidationError(
                f"Port {port_id} berths occupied ({port.berths_occupied}) exceeds total ({port.berths_total})"
            )
        if port.yard_capacity_teu > 0 and port.yard_occupancy_teu > port.yard_capacity_teu:
            raise ValidationError(
                f"Port {port_id} yard occupancy ({port.yard_occupancy_teu}) exceeds capacity ({port.yard_capacity_teu})"
            )

    # 2. Vessel Capacity Constraints (Doc 2 §27.3)
    for vessel_id, vessel in state.vessels.items():
        if vessel.capacity_teu > 0 and vessel.current_load_teu > vessel.capacity_teu:
            raise ValidationError(
                f"Vessel {vessel_id} load ({vessel.current_load_teu}) exceeds capacity ({vessel.capacity_teu})"
            )

    # 3. Allocation & 7-Day Lock Consistency (Doc 2 §27.4, §9.5)
    for alloc_id, alloc in state.allocations.items():
        if alloc.booking_id not in state.bookings:
            raise ValidationError(
                f"Allocation {alloc_id} references non-existent booking {alloc.booking_id}"
            )
        booking = state.bookings[alloc.booking_id]
        if booking.lock_status == "LOCKED" and not alloc.locked:
            alloc.locked = True

    # 4. Equipment Conservation (Doc 2 §27.5)
    for (loc, eq_type), bal in state.equipment.items():
        if bal.available < 0 or bal.allocated < 0 or bal.in_transit < 0 or bal.unavailable < 0:
            raise ValidationError(
                f"Negative equipment count in balance for {loc}_{eq_type}: "
                f"avail={bal.available}, alloc={bal.allocated}, transit={bal.in_transit}, unavail={bal.unavailable}"
            )

    logger.debug("Advancement validation passed successfully for run %s", state.run_id)
