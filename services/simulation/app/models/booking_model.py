"""
Booking Generation Model
========================
Converts generated demand signals into discrete bookings with lifecycle,
cargo ready dates, and cancellation mechanics.

Doc 2 §8 — Booking Generation Model:
    §8.2 — Flow: Demand → Booking Generation → BOOKING_CREATED → Kafka → CargoPilot
    §8.3 — Booking rate per (OD, equipment, time)
    §8.4 — Attributes:
            booking_id, origin, destination, equipment_type, quantity,
            cargo_ready_time, booking_time, status, allocation, lock_status
    §8.5 — Cancellation:
            Cancel ~ Bernoulli(p_cancel)
            Respects operational lock status (unlocked only)
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import BookingState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Probabilistic Functions (Doc 2 §8.5)
# ---------------------------------------------------------------------------

def check_cancellation(
    p_cancel: float,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Evaluate booking cancellation.
    Doc 2 §8.5:
        Cancel ~ Bernoulli(p_cancel)
    """
    if p_cancel <= 0.0:
        return False
    if p_cancel >= 1.0:
        return True
    r = rng.random() if rng else random.random()
    return r < p_cancel


def calculate_cargo_ready_time(
    booking_time: datetime,
    lead_time_days: float = 7.0,
) -> datetime:
    """Calculate cargo ready time from booking creation time."""
    return booking_time + timedelta(days=max(0.5, lead_time_days))


# ---------------------------------------------------------------------------
# Booking Model Class
# ---------------------------------------------------------------------------

class BookingModel:
    """
    Domain model for customer booking generation and cancellation.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        rng: Optional[random.Random] = None,
    ) -> None:
        self._reg = registry
        self._rng = rng or random.Random(42)

    def create_booking_from_demand(
        self,
        origin_port_id: str,
        destination_port_id: str,
        equipment_type: str,
        quantity: int,
        sim_time: datetime,
        state: WorldState,
        voyage_id: Optional[str] = None,
        departure_time: Optional[datetime] = None,
    ) -> Tuple[BookingState, SimEvent]:
        """
        Create a booking from generated demand.
        Doc 2 §8.2, §8.4:
            Writes to WorldState.bookings and generates BOOKING_CREATED event.
        """
        booking_id = f"BK-{uuid.uuid4().hex[:8].upper()}"

        try:
            lead_time_days = float(self._reg.get("BOOKING_LEAD_TIME"))
        except KeyError:
            lead_time_days = 21.0

        cargo_ready_time = calculate_cargo_ready_time(sim_time, lead_time_days=lead_time_days)

        cutoff_time = None
        if departure_time:
            # T_cutoff = T_departure - 7 days (Doc 2 §9.4)
            cutoff_time = departure_time - timedelta(days=7)

        booking = BookingState(
            booking_id=booking_id,
            origin_port_id=origin_port_id,
            destination_port_id=destination_port_id,
            equipment_type=equipment_type,
            quantity=quantity,
            cargo_ready_time=cargo_ready_time,
            booking_time=sim_time,
            status="SUBMITTED",
            lock_status="UNLOCKED",
            voyage_id=voyage_id,
            allocation_id=None,
            cutoff_time=cutoff_time,
        )

        state.bookings[booking_id] = booking
        state.kpis.bookings_created += 1

        event = SimEvent(
            event_type=EventType.BOOKING_CREATED,
            entity_type="booking",
            entity_id=booking_id,
            simulation_time=sim_time,
            source="booking_model",
            world_id=state.world_id,
            payload={
                "booking_id": booking_id,
                "origin_port_id": origin_port_id,
                "destination_port_id": destination_port_id,
                "equipment_type": equipment_type,
                "quantity": quantity,
                "cargo_ready_time": cargo_ready_time.isoformat(),
                "cutoff_time": cutoff_time.isoformat() if cutoff_time else None,
                "status": booking.status,
            },
        )
        logger.info(
            "Booking %s CREATED: %s → %s (%d × %s, ready=%s)",
            booking_id,
            origin_port_id,
            destination_port_id,
            quantity,
            equipment_type,
            cargo_ready_time.isoformat(),
        )
        return booking, event

    def evaluate_cancellation(
        self,
        booking: BookingState,
        sim_time: datetime,
        state: WorldState,
    ) -> Optional[SimEvent]:
        """
        Evaluate stochastic cancellation for an unlocked booking.
        Doc 2 §8.5:
            Cancel ~ Bernoulli(p_cancel)
            Respects lock status: locked or fulfilled bookings cannot be cancelled.
        """
        if booking.lock_status == "LOCKED" or booking.status in ("CANCELLED", "FULFILLED"):
            return None

        try:
            p_cancel = float(self._reg.get("BOOKING_CANCELLATION_PROBABILITY"))
        except KeyError:
            p_cancel = 0.05

        if not check_cancellation(p_cancel, self._rng):
            return None

        booking.status = "CANCELLED"
        state.kpis.bookings_cancelled += 1

        logger.info("Booking %s CANCELLED (p=%.2f)", booking.booking_id, p_cancel)

        return SimEvent(
            event_type=EventType.BOOKING_CANCELLED,
            entity_type="booking",
            entity_id=booking.booking_id,
            simulation_time=sim_time,
            source="booking_model",
            world_id=state.world_id,
            payload={
                "booking_id": booking.booking_id,
                "origin_port_id": booking.origin_port_id,
                "destination_port_id": booking.destination_port_id,
                "quantity": booking.quantity,
            },
        )
