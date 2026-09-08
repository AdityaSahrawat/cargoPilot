"""
Disruption Engine
=================
Coordinates injection, activation, consequence cascade, and termination of
the 6 disruption types without direct world state mutation outside the event system.

Architectural Rule 4:
    All state changes go through the event system.
    inject_disruption() creates an event → event queue → model handler.

Doc 2 §14 — Disruption Models:
    §14.2 — Disruption structure: ID, type, start, end, severity, affected entities
    §14.3 — Active Period vs. Persistent Consequences:
            Disruption window ends, but vessel delays, container backlog,
            and cost penalties remain in WorldState.
    §14.4 — Storm: F_weather = 1 - α_s × s
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.config.disruption_types import DisruptionStatus, DisruptionType
from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.models.port_model import PortModel
from app.models.vessel_model import VesselModel
from app.world.world_state import DisruptionState, WorldState

logger = logging.getLogger(__name__)


class DisruptionEngine:
    """
    Engine for injecting, handling, and ending operational disruptions.

    Follows Doc 2 §1.7:
        Current State + Configuration + Event → State Changes + Generated Events
    """

    def __init__(
        self,
        registry: ParameterRegistry,
        vessel_model: Optional[VesselModel] = None,
        port_model: Optional[PortModel] = None,
    ) -> None:
        self._reg = registry
        self._vessel_model = vessel_model
        self._port_model = port_model

    def build_injection_event(
        self,
        disruption_type: str,
        severity: float,
        duration_hours: float,
        sim_time: datetime,
        affected_entity_ids: Optional[List[str]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
        world_id: str = "world-2",
    ) -> Tuple[SimEvent, str]:
        """
        Build a DISRUPTION_ACTIVATED event for scheduling.
        Architectural Rule 4: inject_disruption creates an event, does not directly mutate state.
        """
        disruption_id = f"DIS-{uuid.uuid4().hex[:8].upper()}"
        affected = affected_entity_ids or []
        overrides = parameter_overrides or {}

        event = SimEvent(
            event_type=EventType.DISRUPTION_ACTIVATED,
            entity_type="disruption",
            entity_id=disruption_id,
            simulation_time=sim_time,
            source="admin_injection",
            world_id=world_id,
            payload={
                "disruption_id": disruption_id,
                "disruption_type": disruption_type,
                "severity": severity,
                "duration_hours": duration_hours,
                "affected_entity_ids": affected,
                "parameter_overrides": overrides,
                "end_time": (sim_time + timedelta(hours=duration_hours)).isoformat(),
            },
        )
        return event, disruption_id

    def handle_disruption_activated(
        self,
        event: SimEvent,
        state: WorldState,
    ) -> List[SimEvent]:
        """
        Handle DISRUPTION_ACTIVATED event:
        1. Adds DisruptionState to state.disruptions
        2. Applies parameter overrides to registry
        3. Cascades consequence events to affected models
        """
        payload = event.payload
        disruption_id = payload.get("disruption_id", event.entity_id)
        d_type = payload.get("disruption_type", DisruptionType.STORM.value)
        severity = float(payload.get("severity", 0.5))
        duration = float(payload.get("duration_hours", 24.0))
        affected_ids = payload.get("affected_entity_ids", [])
        overrides = payload.get("parameter_overrides", {})

        sim_time = event.simulation_time
        end_time = sim_time + timedelta(hours=duration)

        disruption = DisruptionState(
            disruption_id=disruption_id,
            disruption_type=d_type,
            status=DisruptionStatus.ACTIVE.value,
            severity=severity,
            start_time=sim_time,
            end_time=end_time,
            duration_hours=duration,
            affected_entity_ids=affected_ids,
            parameter_overrides=overrides,
            caused_by_event_id=event.event_id,
        )
        state.disruptions.append(disruption)

        # Apply parameter overrides to registry
        for k, v in overrides.items():
            try:
                self._reg.set(k, v)
            except Exception as ex:
                logger.warning("Failed to apply override %s=%s: %s", k, v, ex)

        logger.info(
            "DISRUPTION ACTIVATED: id=%s, type=%s, severity=%.2f, duration=%.1fh",
            disruption_id,
            d_type,
            severity,
            duration,
        )

        consequence_events: List[SimEvent] = []

        # Cascade consequence events based on disruption type
        if d_type == DisruptionType.STORM.value or d_type == "STORM":
            consequence_events.extend(
                self._cascade_storm(disruption, sim_time, state)
            )
        elif d_type == DisruptionType.PORT_STRIKE.value or d_type == "PORT_STRIKE":
            consequence_events.extend(
                self._cascade_port_strike(disruption, sim_time, state)
            )
        elif d_type == DisruptionType.PORT_CONGESTION_EVENT.value or d_type == "PORT_CONGESTION_EVENT":
            consequence_events.extend(
                self._cascade_port_congestion(disruption, sim_time, state)
            )

        return consequence_events

    def handle_disruption_ended(
        self,
        disruption_id: str,
        sim_time: datetime,
        state: WorldState,
    ) -> Tuple[SimEvent, List[SimEvent]]:
        """
        Handle disruption end:
        Doc 2 §14.3:
            Disruption window ends, but its consequences (delays, backlog) remain in WorldState.
        """
        disruption = next((d for d in state.disruptions if d.disruption_id == disruption_id), None)
        if not disruption:
            raise KeyError(f"Disruption {disruption_id} not found in world state")

        disruption.status = DisruptionStatus.ENDED.value

        recovery_events: List[SimEvent] = []

        # If port strike ended, restore port capacity
        if disruption.disruption_type in (DisruptionType.PORT_STRIKE.value, "PORT_STRIKE"):
            for port_id in disruption.affected_entity_ids:
                if port_id in state.ports:
                    port = state.ports[port_id]
                    if self._port_model:
                        self._port_model.apply_strike_end(port)
                    else:
                        port.is_strike_active = False
                        port.strike_capacity_factor = 1.0

                    recovery_events.append(SimEvent(
                        event_type=EventType.PORT_STRIKE_ENDED,
                        entity_type="port",
                        entity_id=port_id,
                        simulation_time=sim_time,
                        source="disruption_engine",
                        world_id=state.world_id,
                    ))

        # End event
        end_event = SimEvent(
            event_type=EventType.DISRUPTION_ENDED,
            entity_type="disruption",
            entity_id=disruption_id,
            simulation_time=sim_time,
            source="disruption_engine",
            world_id=state.world_id,
            payload={
                "disruption_id": disruption_id,
                "disruption_type": disruption.disruption_type,
            },
        )
        logger.info(
            "DISRUPTION ENDED: id=%s, type=%s. Accumulated consequences persist in world state.",
            disruption_id,
            disruption.disruption_type,
        )
        return end_event, recovery_events

    # ------------------------------------------------------------------
    # Cascading consequence helpers (Doc 2 §15)
    # ------------------------------------------------------------------

    def _cascade_storm(
        self,
        disruption: DisruptionState,
        sim_time: datetime,
        state: WorldState,
    ) -> List[SimEvent]:
        """Storm cascades into vessel speed reductions and updated ETAs."""
        events: List[SimEvent] = []
        if not self._vessel_model:
            return events

        # Target vessels explicitly named or all in-transit vessels
        target_vessels = (
            [state.get_vessel(vid) for vid in disruption.affected_entity_ids if vid in state.vessels]
            if disruption.affected_entity_ids
            else [v for v in state.vessels.values() if v.status == "IN_TRANSIT"]
        )

        for v in target_vessels:
            if v.status == "IN_TRANSIT" and v.current_voyage_id:
                voyage = state.voyages.get(v.current_voyage_id)
                if voyage:
                    eta_event, _ = self._vessel_model.handle_weather_change(
                        vessel=v,
                        voyage=voyage,
                        sim_time=sim_time,
                        storm_severity=disruption.severity,
                    )
                    events.append(eta_event)

        return events

    def _cascade_port_strike(
        self,
        disruption: DisruptionState,
        sim_time: datetime,
        state: WorldState,
    ) -> List[SimEvent]:
        """Port strike reduces available berths and increases port turnaround times."""
        events: List[SimEvent] = []
        target_ports = (
            [state.get_port(pid) for pid in disruption.affected_entity_ids if pid in state.ports]
            if disruption.affected_entity_ids
            else list(state.ports.values())
        )

        capacity_factor = max(0.1, 1.0 - disruption.severity)

        for port in target_ports:
            if self._port_model:
                self._port_model.apply_strike_start(port, capacity_factor=capacity_factor)
            else:
                port.is_strike_active = True
                port.strike_capacity_factor = capacity_factor

            events.append(SimEvent(
                event_type=EventType.PORT_STRIKE_STARTED,
                entity_type="port",
                entity_id=port.port_id,
                simulation_time=sim_time,
                source="disruption_engine",
                world_id=state.world_id,
                payload={
                    "port_id": port.port_id,
                    "strike_capacity_factor": capacity_factor,
                },
            ))

        return events

    def _cascade_port_congestion(
        self,
        disruption: DisruptionState,
        sim_time: datetime,
        state: WorldState,
    ) -> List[SimEvent]:
        """Explicit congestion event increases congestion index."""
        events: List[SimEvent] = []
        target_ports = (
            [state.get_port(pid) for pid in disruption.affected_entity_ids if pid in state.ports]
            if disruption.affected_entity_ids
            else list(state.ports.values())
        )
        for port in target_ports:
            # Force severe congestion index
            port.congestion_index = max(port.congestion_index, 1.0 + disruption.severity * 3.0)
            events.append(SimEvent(
                event_type=EventType.PORT_CONGESTION_CHANGED,
                entity_type="port",
                entity_id=port.port_id,
                simulation_time=sim_time,
                source="disruption_engine",
                world_id=state.world_id,
                payload={
                    "port_id": port.port_id,
                    "congestion_index": port.congestion_index,
                },
            ))
        return events
