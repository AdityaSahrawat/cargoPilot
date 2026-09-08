"""
Recovery Model
==============
Executes operational recovery following failures or disruptions.

Doc 2 §20 — Recovery Models:
    §20.1 — Recovery restores operational capability; does NOT reverse past accumulated delays/costs.
    §20.2 — Recovery Flow: Failure → Unavailable → Recovery Process → Available
    §20.3 — Recovery Time:
            T_recovery = T_failure + Duration_recovery
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.models.vessel_model import VesselModel
from app.world.world_state import VesselState, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §20.3)
# ---------------------------------------------------------------------------

def calculate_recovery_timestamp(
    failure_time: datetime,
    recovery_duration_hours: float,
) -> datetime:
    """
    Calculate timestamp when recovery completes.
    Doc 2 §20.3:
        T_recovery = T_failure + Duration_recovery
    """
    return failure_time + timedelta(hours=max(0.5, recovery_duration_hours))


# ---------------------------------------------------------------------------
# Recovery Model Class
# ---------------------------------------------------------------------------

class RecoveryModel:
    """
    Domain model for scheduling and executing operational recovery.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        vessel_model: Optional[VesselModel] = None,
    ) -> None:
        self._reg = registry
        self._vessel_model = vessel_model

    def schedule_vessel_recovery(
        self,
        vessel: VesselState,
        failure_time: datetime,
    ) -> Tuple[datetime, float]:
        """
        Calculate recovery time for a failed vessel.
        Uses VESSEL_RECOVERY_TIME_HOURS.
        """
        try:
            rec_hours = float(self._reg.get("VESSEL_RECOVERY_TIME_HOURS"))
        except KeyError:
            rec_hours = 48.0

        recovery_time = calculate_recovery_timestamp(failure_time, rec_hours)
        return recovery_time, rec_hours

    def execute_vessel_recovery(
        self,
        vessel: VesselState,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[SimEvent, Optional[SimEvent]]:
        """
        Execute recovery for a vessel:
        1. Condition → GOOD
        2. Speed restored
        3. Recalculate ETA from current position (if in-transit)
        4. Emit VESSEL_RECOVERED (and VESSEL_ETA_UPDATED if applicable)
        """
        vessel.condition = "GOOD"

        if self._vessel_model:
            base_speed = self._vessel_model.get_vessel_base_speed(vessel)
        else:
            try:
                base_speed = float(self._reg.get("VESSEL_BASE_SPEED_KNOTS"))
            except KeyError:
                base_speed = 18.0

        vessel.current_speed_knots = base_speed

        rec_event = SimEvent(
            event_type=EventType.VESSEL_RECOVERED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="recovery_model",
            world_id=state.world_id,
            payload={
                "vessel_id": vessel.vessel_id,
                "restored_speed_knots": base_speed,
            },
        )
        logger.info(
            "Vessel %s RECOVERED at %s (speed restored to %.1f kn)",
            vessel.vessel_id,
            sim_time.isoformat(),
            base_speed,
        )

        eta_event: Optional[SimEvent] = None

        # If in-transit, recalculate remaining voyage time
        if vessel.status == "IN_TRANSIT" and vessel.current_voyage_id:
            voyage = state.voyages.get(vessel.current_voyage_id)
            if voyage:
                if self._vessel_model:
                    eta_event, _ = self._vessel_model.handle_weather_change(
                        vessel=vessel,
                        voyage=voyage,
                        sim_time=sim_time,
                        storm_severity=0.0,
                    )

        return rec_event, eta_event
