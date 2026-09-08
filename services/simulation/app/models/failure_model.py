"""
Failure & Exception Models
===========================
Implements time-to-event failure scheduling and state transitions.

Doc 2 §19 — Failure & Exception Models:
    §19.2 — Failure Principle:
            Failure causes a state transition and downstream consequences.
    §19.3 — Time-to-event model:
            Uses exponential distribution rather than per-hour polling.
            Δt ~ Exponential(1 / MTBF)
"""
from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import VesselState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Probabilistic Functions (Doc 2 §3.3, §19.3)
# ---------------------------------------------------------------------------

def draw_time_to_failure_hours(
    mtbf_hours: float,
    rng: Optional[random.Random] = None,
    deterministic: bool = False,
) -> float:
    """
    Draw inter-arrival time to next failure from Exponential(1 / MTBF).
    Doc 2 §3.3, §19.3:
        Time-to-event scheduling rather than per-hour Bernoulli polling.
    """
    if mtbf_hours <= 0:
        return 24.0

    if deterministic:
        return mtbf_hours

    if rng is None:
        rng = random.Random()

    # Exp(λ) where λ = 1/MTBF -> mean = MTBF
    # Scipy/Python: rng.expovariate(1.0 / mtbf_hours)
    try:
        val = rng.expovariate(1.0 / mtbf_hours)
    except ZeroDivisionError:
        val = mtbf_hours

    return max(1.0, float(val))


# ---------------------------------------------------------------------------
# Failure Model Class
# ---------------------------------------------------------------------------

class FailureModel:
    """
    Domain model for scheduling and triggering operational failures.

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

    def schedule_next_vessel_failure(
        self,
        vessel: VesselState,
        current_simpy_time: float,
        deterministic: bool = False,
    ) -> float:
        """
        Schedule the SimPy timestamp of next mechanical failure for vessel.
        Uses time-to-event model from VESSEL_MEAN_TIME_BETWEEN_FAILURES.
        """
        try:
            mtbf = float(self._reg.get("VESSEL_MEAN_TIME_BETWEEN_FAILURES"))
        except KeyError:
            mtbf = 720.0

        delta_hours = draw_time_to_failure_hours(mtbf, self._rng, deterministic=deterministic)
        failure_time = current_simpy_time + delta_hours
        vessel.next_failure_at = failure_time

        logger.debug(
            "Vessel %s: Next mechanical failure scheduled in %.1f hours (at T+%.1fh)",
            vessel.vessel_id,
            delta_hours,
            failure_time,
        )
        return failure_time

    def trigger_vessel_failure(
        self,
        vessel: VesselState,
        sim_time: datetime,
        state: WorldState,
    ) -> SimEvent:
        """
        Execute mechanical failure on vessel:
        Transition condition → DAMAGED, speed → 0.
        Doc 2 §19.2: Mechanical Failure → Vessel Unavailable
        """
        vessel.condition = "DAMAGED"
        vessel.current_speed_knots = 0.0

        logger.warning(
            "Vessel %s MECHANICAL FAILURE triggered at %s",
            vessel.vessel_id,
            sim_time.isoformat(),
        )

        return SimEvent(
            event_type=EventType.VESSEL_MECHANICAL_FAILURE,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="failure_model",
            world_id=state.world_id,
            payload={
                "vessel_id": vessel.vessel_id,
                "condition": vessel.condition,
            },
        )
