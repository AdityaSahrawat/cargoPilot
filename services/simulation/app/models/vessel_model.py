"""
Vessel & Voyage Model
=====================
Implements operational vessel movement, effective speed, position continuity,
weather impact, ETA updates, schedule variance, mechanical failure, and port interaction.

Doc 2 §4 — Vessel & Voyage Model:
    §4.4 — Vessel Movement:
            T_travel = D / V_eff
            V_eff = V_base × F_weather × F_operational
    §4.5 — Position Continuity:
            D_remaining = D_route - D_travelled
            T_remaining = D_remaining / V_eff
            (Never restarts voyage from departure port when conditions change)
    §4.6 — Weather Impact:
            F_weather = 1 - α_s × s (where s ∈ [0, 1] is storm severity)
    §4.7 — Arrival & Port Interaction:
            Asks port model for berth (does not independently decide)
    §4.8 — Schedule Variance:
            ScheduleVariance = ActualTime - ScheduledTime
    §4.11 — Configurable Parameters:
            VESSEL_BASE_SPEED_KNOTS, VESSEL_SPEED_VARIATION,
            VESSEL_TURNAROUND_TIME_HOURS, VESSEL_DELAY_PROBABILITY,
            VESSEL_MEAN_TIME_BETWEEN_FAILURES, VESSEL_RECOVERY_TIME_HOURS,
            WEATHER_SPEED_FACTOR, WEATHER_DELAY_PROBABILITY
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.models.port_model import PortModel
from app.world.world_state import (
    PortState,
    VesselState,
    VoyageState,
    WorldState,
    Visibility,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure Mathematical Formulas (Doc 2 §4.4, §4.5, §4.6, §4.8, §28)
# ---------------------------------------------------------------------------

def calculate_effective_speed(
    v_base_knots: float,
    f_weather: float = 1.0,
    f_operational: float = 1.0,
    min_speed_knots: float = 1.0,
) -> float:
    """
    Calculate effective vessel speed.
    Doc 2 §4.4:
        V_eff = V_base × F_weather × F_operational
    """
    speed = v_base_knots * max(0.0, f_weather) * max(0.0, f_operational)
    return max(min_speed_knots, speed) if (f_weather > 0 and f_operational > 0) else 0.0


def calculate_travel_time(
    distance_nm: float,
    effective_speed_knots: float,
) -> float:
    """
    Calculate travel time in hours.
    Doc 2 §4.4:
        T_travel = D / V_eff
    """
    if effective_speed_knots <= 0:
        return float("inf")
    return max(0.0, distance_nm / effective_speed_knots)


def calculate_remaining_travel_time(
    distance_remaining_nm: float,
    effective_speed_knots: float,
) -> float:
    """
    Calculate remaining travel time from current position.
    Doc 2 §4.5:
        T_remaining = D_remaining / V_eff
    """
    return calculate_travel_time(distance_remaining_nm, effective_speed_knots)


def calculate_position_continuity(
    route_distance_nm: float,
    distance_travelled_nm: float,
) -> Tuple[float, float]:
    """
    Calculate position continuity: fraction and remaining distance.
    Doc 2 §4.5:
        D_remaining = D_route - D_travelled
    Returns:
        (position_fraction ∈ [0, 1], distance_remaining_nm ≥ 0)
    """
    if route_distance_nm <= 0:
        return 1.0, 0.0

    clamped_travelled = max(0.0, min(route_distance_nm, distance_travelled_nm))
    d_remaining = max(0.0, route_distance_nm - clamped_travelled)
    fraction = clamped_travelled / route_distance_nm
    return fraction, d_remaining


def calculate_weather_factor(
    base_weather_factor: float = 1.0,
    storm_severity: float = 0.0,
    alpha_s: float = 0.5,
) -> float:
    """
    Weather speed factor under storm conditions.
    Doc 2 §4.6, §14.4:
        F_weather = 1 - α_s × s
    """
    reduction = max(0.0, min(1.0, alpha_s * max(0.0, min(1.0, storm_severity))))
    f_w = base_weather_factor * (1.0 - reduction)
    return max(0.1, min(1.0, f_w))


def calculate_schedule_variance(
    actual_time: datetime,
    scheduled_time: datetime,
) -> float:
    """
    Schedule variance in hours.
    Doc 2 §4.8:
        ScheduleVariance = ActualTime - ScheduledTime
    Positive = delayed, Negative = ahead of schedule.
    """
    diff = actual_time - scheduled_time
    return diff.total_seconds() / 3600.0


# ---------------------------------------------------------------------------
# Vessel Model Class
# ---------------------------------------------------------------------------

class VesselModel:
    """
    Domain model for Vessel & Voyage movement.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        port_model: PortModel,
    ) -> None:
        self._reg = registry
        self._port_model = port_model

    # ------------------------------------------------------------------
    # Speed & Movement
    # ------------------------------------------------------------------

    def get_vessel_base_speed(self, vessel: VesselState) -> float:
        """Lookup base speed from vessel state or registry."""
        if hasattr(vessel, "base_speed_knots") and vessel.base_speed_knots > 0:
            return vessel.base_speed_knots
        if vessel.current_speed_knots and vessel.current_speed_knots > 0:
            return vessel.current_speed_knots
        try:
            return float(self._reg.get("VESSEL_BASE_SPEED_KNOTS"))
        except KeyError:
            return 18.0

    def compute_effective_speed(
        self,
        vessel: VesselState,
        storm_severity: float = 0.0,
        f_operational: float = 1.0,
    ) -> float:
        """Compute V_eff for vessel taking into account weather and operational status."""
        v_base = self.get_vessel_base_speed(vessel)
        f_weather = calculate_weather_factor(
            base_weather_factor=1.0,
            storm_severity=storm_severity,
        )
        # Mechanical failure reduces operational factor to 0 or limp
        if vessel.condition in ("DAMAGED", "UNAVAILABLE"):
            f_operational = 0.0

        return calculate_effective_speed(v_base, f_weather, f_operational)

    # ------------------------------------------------------------------
    # Voyage Lifecycle
    # ------------------------------------------------------------------

    def start_voyage(
        self,
        vessel: VesselState,
        voyage: VoyageState,
        sim_time: datetime,
        storm_severity: float = 0.0,
    ) -> Tuple[SimEvent, float]:
        """
        Depart vessel from origin port on scheduled voyage leg.
        Doc 2 §4.4:
            T_travel = D / V_eff
        Returns:
            (VESSEL_DEPARTED event, travel_time_hours)
        """
        v_eff = self.compute_effective_speed(vessel, storm_severity=storm_severity)
        vessel.current_speed_knots = v_eff

        travel_time_hours = calculate_travel_time(voyage.route_distance_nm, v_eff)

        # Update vessel state
        vessel.status = "IN_TRANSIT"
        vessel.current_voyage_id = voyage.voyage_id
        vessel.current_port_id = None
        vessel.position_fraction = 0.0
        vessel.distance_remaining_nm = voyage.route_distance_nm
        vessel.eta = sim_time + timedelta(hours=travel_time_hours)

        # Update voyage state
        voyage.actual_departure = sim_time
        voyage.estimated_arrival = vessel.eta
        voyage.status = "ACTIVE"

        event = SimEvent(
            event_type=EventType.VESSEL_DEPARTED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id="world-2",
            payload={
                "voyage_id": voyage.voyage_id,
                "origin_port_id": voyage.origin_port_id,
                "destination_port_id": voyage.destination_port_id,
                "route_distance_nm": voyage.route_distance_nm,
                "effective_speed_knots": v_eff,
                "eta": vessel.eta.isoformat(),
                "travel_time_hours": travel_time_hours,
            },
        )
        logger.info(
            "Vessel %s DEPARTED %s → %s (dist=%.0f NM, V_eff=%.1f kn, ETA=%s)",
            vessel.vessel_id,
            voyage.origin_port_id,
            voyage.destination_port_id,
            voyage.route_distance_nm,
            v_eff,
            vessel.eta.isoformat(),
        )
        return event, travel_time_hours

    def arrive_vessel(
        self,
        vessel: VesselState,
        voyage: VoyageState,
        port: PortState,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[SimEvent, Optional[float]]:
        """
        Vessel arrives at destination port.
        Doc 2 §4.7 & §4.9:
            Vessel reaches destination port:
            IN_TRANSIT → ARRIVED → PORT RESOURCE CHECK
            Vessel asks port model for berth.
            If available: status → IN_PORT, schedule turnaround operations.
            If unavailable: status → WAITING_FOR_BERTH, queued.

        Returns:
            (VESSEL_ARRIVED event, turnaround_time_hours if berthed else None)
        """
        vessel.status = "ARRIVED"
        vessel.position_fraction = 1.0
        vessel.distance_remaining_nm = 0.0
        voyage.actual_arrival = sim_time

        # Schedule variance (Doc 2 §4.8)
        if voyage.scheduled_arrival:
            variance = calculate_schedule_variance(sim_time, voyage.scheduled_arrival)
            vessel.schedule_variance_hours = variance
            if variance > 0:
                state.kpis.vessels_delayed += 1
                state.kpis.total_delay_hours += variance

        # Delegate berth allocation to PortModel (Doc 2 §4.9)
        berth_granted = self._port_model.request_berth(port, vessel.vessel_id, state)

        turnaround_hours: Optional[float] = None
        if berth_granted:
            vessel.status = "IN_PORT"
            vessel.current_port_id = port.port_id
            turnaround_hours = self._port_model.calculate_turnaround_time_hours(
                port, vessel, moves_teu=vessel.current_load_teu
            )
        else:
            vessel.status = "WAITING_FOR_BERTH"

        event = SimEvent(
            event_type=EventType.VESSEL_ARRIVED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id=state.world_id,
            payload={
                "voyage_id": voyage.voyage_id,
                "port_id": port.port_id,
                "berth_granted": berth_granted,
                "schedule_variance_hours": vessel.schedule_variance_hours,
                "turnaround_time_hours": turnaround_hours,
            },
        )
        return event, turnaround_hours

    def complete_port_stay(
        self,
        vessel: VesselState,
        port: PortState,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[SimEvent, Optional[str]]:
        """
        Vessel finishes port turnaround operations and unberths.
        Doc 2 §4.9:
            Releases berth at port, which may grant berth to next queued vessel.

        Returns:
            (VESSEL_UNBERTHED event, next_queued_vessel_id)
        """
        vessel.status = "AVAILABLE"
        next_vessel_id = self._port_model.release_berth(port, state)

        event = SimEvent(
            event_type=EventType.VESSEL_UNBERTHED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id=state.world_id,
            payload={
                "port_id": port.port_id,
                "freed_berth_for_vessel": next_vessel_id,
            },
        )
        return event, next_vessel_id

    # ------------------------------------------------------------------
    # Position Continuity & Weather Re-evaluation (Doc 2 §4.5, §4.6)
    # ------------------------------------------------------------------

    def update_vessel_progress(
        self,
        vessel: VesselState,
        voyage: VoyageState,
        elapsed_hours: float,
    ) -> None:
        """
        Update vessel position along voyage route.
        Doc 2 §4.5:
            D_remaining = D_route - D_travelled
        """
        if vessel.status != "IN_TRANSIT" or voyage.route_distance_nm <= 0:
            return

        distance_travelled = (
            vessel.position_fraction * voyage.route_distance_nm
            + vessel.current_speed_knots * elapsed_hours
        )
        fraction, d_remaining = calculate_position_continuity(
            voyage.route_distance_nm, distance_travelled
        )
        vessel.position_fraction = fraction
        vessel.distance_remaining_nm = d_remaining

    def handle_weather_change(
        self,
        vessel: VesselState,
        voyage: VoyageState,
        sim_time: datetime,
        storm_severity: float,
    ) -> Tuple[SimEvent, float]:
        """
        Storm or weather change affects in-transit vessel.
        Doc 2 §4.5, §4.6:
            Recalculates effective speed and remaining travel time from CURRENT position.
            Does NOT restart the voyage from origin port!

        Returns:
            (VESSEL_ETA_UPDATED event, new_remaining_hours)
        """
        new_speed = self.compute_effective_speed(vessel, storm_severity=storm_severity)
        vessel.current_speed_knots = new_speed

        remaining_hours = calculate_remaining_travel_time(
            vessel.distance_remaining_nm, new_speed
        )
        new_eta = sim_time + timedelta(hours=remaining_hours)
        vessel.eta = new_eta
        voyage.estimated_arrival = new_eta

        event = SimEvent(
            event_type=EventType.VESSEL_ETA_UPDATED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id="world-2",
            payload={
                "voyage_id": voyage.voyage_id,
                "storm_severity": storm_severity,
                "new_speed_knots": new_speed,
                "distance_remaining_nm": vessel.distance_remaining_nm,
                "new_eta": new_eta.isoformat(),
                "remaining_hours": remaining_hours,
            },
        )
        logger.info(
            "Vessel %s ETA UPDATED: storm=%.2f, speed=%.1f kn, remaining=%.0f NM, ETA=%s",
            vessel.vessel_id,
            storm_severity,
            new_speed,
            vessel.distance_remaining_nm,
            new_eta.isoformat(),
        )
        return event, remaining_hours

    # ------------------------------------------------------------------
    # Mechanical Failure & Recovery (Doc 2 §4.11, §19, §20)
    # ------------------------------------------------------------------

    def apply_mechanical_failure(
        self,
        vessel: VesselState,
        sim_time: datetime,
    ) -> SimEvent:
        """Trigger mechanical failure on vessel."""
        vessel.condition = "DAMAGED"
        vessel.current_speed_knots = 0.0

        return SimEvent(
            event_type=EventType.VESSEL_MECHANICAL_FAILURE,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id="world-2",
            payload={
                "vessel_id": vessel.vessel_id,
                "condition": vessel.condition,
            },
        )

    def apply_recovery(
        self,
        vessel: VesselState,
        sim_time: datetime,
    ) -> SimEvent:
        """Recover vessel from failure back to operational condition."""
        vessel.condition = "GOOD"
        vessel.current_speed_knots = self.get_vessel_base_speed(vessel)

        return SimEvent(
            event_type=EventType.VESSEL_RECOVERED,
            entity_type="vessel",
            entity_id=vessel.vessel_id,
            simulation_time=sim_time,
            source="vessel_model",
            world_id="world-2",
            payload={
                "vessel_id": vessel.vessel_id,
                "condition": vessel.condition,
                "speed_restored_knots": vessel.current_speed_knots,
            },
        )
