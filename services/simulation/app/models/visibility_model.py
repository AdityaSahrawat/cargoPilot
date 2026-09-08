"""
Information & Visibility Model
==============================
Implements the 3-timestamp observability pipeline and visibility gating.

Doc 2 §17 — Information / Visibility Model:
    §17.2 — Three Timestamps:
            Occurrence Time, Observation Time, Ingestion Time
    §17.3 — Delays:
            T_observation = T_occurrence + D_information
            T_ingestion   = T_observation + D_ingestion
Architectural Rule 3:
    Future entities carry Visibility:
        INTERNAL_SIMULATION_KNOWN → KNOWN_TO_CARGOPILOT
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import VesselState, VoyageState, Visibility, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §17.3, §28)
# ---------------------------------------------------------------------------

def calculate_observation_time(
    occurrence_time: datetime,
    info_delay_hours: float = 0.5,
) -> datetime:
    """Doc 2 §17.3: T_observation = T_occurrence + D_information"""
    return occurrence_time + timedelta(hours=max(0.0, info_delay_hours))


def calculate_ingestion_time(
    observation_time: datetime,
    ingestion_delay_hours: float = 0.1,
) -> datetime:
    """Doc 2 §17.3: T_ingestion = T_observation + D_ingestion"""
    return observation_time + timedelta(hours=max(0.0, ingestion_delay_hours))


# ---------------------------------------------------------------------------
# Visibility Model Class
# ---------------------------------------------------------------------------

class VisibilityModel:
    """
    Domain model for information propagation delays and visibility gating.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(self, registry: ParameterRegistry) -> None:
        self._reg = registry

    def publish_vessel_positions(
        self,
        sim_time: datetime,
        state: WorldState,
    ) -> List[SimEvent]:
        """
        Evaluate and publish vessel positions to CargoPilot.
        Transitions vessel ETA visibility to KNOWN_TO_CARGOPILOT.
        Emits VESSEL_POSITION_PUBLISHED.
        """
        events: List[SimEvent] = []

        for vessel_id, vessel in state.vessels.items():
            if vessel.status in ("IN_TRANSIT", "ARRIVED", "WAITING_FOR_BERTH", "IN_PORT"):
                vessel.eta_visibility = Visibility.KNOWN_TO_CARGOPILOT

                event = SimEvent(
                    event_type=EventType.VESSEL_POSITION_PUBLISHED,
                    entity_type="vessel",
                    entity_id=vessel_id,
                    simulation_time=sim_time,
                    source="visibility_model",
                    world_id=state.world_id,
                    payload={
                        "vessel_id": vessel_id,
                        "status": vessel.status,
                        "position_fraction": vessel.position_fraction,
                        "distance_remaining_nm": vessel.distance_remaining_nm,
                        "current_speed_knots": vessel.current_speed_knots,
                        "eta": vessel.eta.isoformat() if vessel.eta else None,
                        "schedule_variance_hours": vessel.schedule_variance_hours,
                    },
                )
                events.append(event)

        return events

    def gate_future_voyage_visibility(
        self,
        sim_time: datetime,
        state: WorldState,
        planning_horizon_days: float = 28.0,
    ) -> List[SimEvent]:
        """
        Gate visibility of future scheduled voyages:
        Voyages departing within planning_horizon_days transition from
        INTERNAL_SIMULATION_KNOWN → KNOWN_TO_CARGOPILOT.
        """
        events: List[SimEvent] = []
        horizon_end = sim_time + timedelta(days=planning_horizon_days)

        for voyage_id, voyage in state.voyages.items():
            if voyage.visibility == Visibility.INTERNAL_SIMULATION_KNOWN:
                if voyage.scheduled_departure <= horizon_end:
                    voyage.visibility = Visibility.KNOWN_TO_CARGOPILOT
                    logger.info(
                        "Voyage %s visibility promoted to KNOWN_TO_CARGOPILOT (dep=%s)",
                        voyage_id,
                        voyage.scheduled_departure.isoformat(),
                    )
        return events
