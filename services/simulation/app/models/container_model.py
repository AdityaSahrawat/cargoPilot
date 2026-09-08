"""
Container & Equipment Model
============================
Implements individual container unit lifecycle, damage transitions,
maintenance, condition states, and equipment inventory balance integration.

Doc 2 §6 — Container & Equipment Model:
    §6.1 — Container Attributes:
            ID, equipment_type, current_location, status, condition, booking, allocation
    §6.2 — Lifecycle:
            EMPTY_AVAILABLE → ALLOCATED → GATE_OUT → STUFFING → LOADED →
            IN_TRANSIT → DISCHARGED → CUSTOMER → EMPTY → EMPTY_AVAILABLE
    §6.3 — Equipment Types:
            20DC, 40DC, 40HC
    §6.4 — Container Condition:
            GOOD, DAMAGED, MAINTENANCE, UNAVAILABLE
    §6.5 — Damage and Maintenance:
            Damage ~ Bernoulli(p_damage)
            Severity ~ Bernoulli(p_severity) → UNAVAILABLE vs MAINTENANCE
            Repair/Maintenance time → back to GOOD
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.config.parameters import ParameterRegistry
from app.events.event_types import EventType, SimEvent
from app.world.world_state import ContainerState, EquipmentBalance, WorldState

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Valid Lifecycle Transitions (Doc 2 §6.2)
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: Dict[str, Set[str]] = {
    "EMPTY_AVAILABLE": {"ALLOCATED", "MAINTENANCE", "UNAVAILABLE"},
    "ALLOCATED": {"GATE_OUT", "EMPTY_AVAILABLE", "MAINTENANCE", "UNAVAILABLE"},
    "GATE_OUT": {"STUFFING", "MAINTENANCE", "UNAVAILABLE"},
    "STUFFING": {"LOADED", "MAINTENANCE", "UNAVAILABLE"},
    "LOADED": {"IN_TRANSIT", "DISCHARGED", "MAINTENANCE", "UNAVAILABLE"},
    "IN_TRANSIT": {"DISCHARGED", "DAMAGED", "UNAVAILABLE"},
    "DISCHARGED": {"CUSTOMER", "MAINTENANCE", "UNAVAILABLE"},
    "CUSTOMER": {"EMPTY", "DAMAGED", "UNAVAILABLE"},
    "EMPTY": {"EMPTY_AVAILABLE", "MAINTENANCE", "UNAVAILABLE"},
    "MAINTENANCE": {"EMPTY_AVAILABLE", "UNAVAILABLE"},
    "UNAVAILABLE": set(),  # Terminal state unless explicitly overridden
}


# ---------------------------------------------------------------------------
# Pure Probabilistic & Mathematical Functions (Doc 2 §6.5, §3.5)
# ---------------------------------------------------------------------------

def check_damage(
    p_damage: float,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Evaluate container damage using Bernoulli trial.
    Doc 2 §6.5:
        Damage ~ Bernoulli(p_damage)
    """
    if p_damage <= 0.0:
        return False
    if p_damage >= 1.0:
        return True
    r = rng.random() if rng else random.random()
    return r < p_damage


def check_damage_severity(
    p_severity: float,
    rng: Optional[random.Random] = None,
) -> bool:
    """
    Evaluate if damage is severe enough to cause UNAVAILABLE vs repairable MAINTENANCE.
    Doc 2 §6.5:
        Returns True for UNAVAILABLE (terminal/scrap), False for repairable (MAINTENANCE).
    """
    if p_severity <= 0.0:
        return False
    if p_severity >= 1.0:
        return True
    r = rng.random() if rng else random.random()
    return r < p_severity


def calculate_repair_duration_hours(
    mean_days: float,
    rng: Optional[random.Random] = None,
) -> float:
    """
    Calculate repair duration in hours.
    Doc 2 §6.5:
        Uses mean repair days (can incorporate bounded variation).
    """
    return max(1.0, mean_days * 24.0)


def validate_status_transition(current_status: str, next_status: str) -> bool:
    """Validate whether container transition is permitted by lifecycle graph."""
    allowed = VALID_TRANSITIONS.get(current_status, set())
    return next_status in allowed


# ---------------------------------------------------------------------------
# Container Model Class
# ---------------------------------------------------------------------------

class ContainerModel:
    """
    Domain model for container lifecycle, damage, and equipment pool balance.

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

    # ------------------------------------------------------------------
    # Lifecycle Transitions (Doc 2 §6.2)
    # ------------------------------------------------------------------

    def transition_status(
        self,
        container: ContainerState,
        next_status: str,
        sim_time: datetime,
        state: WorldState,
        allow_forced: bool = False,
    ) -> SimEvent:
        """
        Transition container to a new lifecycle status.
        Enforces valid state machine transitions unless allow_forced is True.
        """
        if not allow_forced and not validate_status_transition(container.status, next_status):
            raise ValueError(
                f"Invalid container status transition: {container.status} → {next_status} "
                f"for container {container.container_id}"
            )

        old_status = container.status
        container.status = next_status

        event = SimEvent(
            event_type=f"CONTAINER_STATUS_{next_status}",
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "container_id": container.container_id,
                "equipment_type": container.equipment_type,
                "old_status": old_status,
                "new_status": next_status,
                "location_id": container.current_location_id,
                "condition": container.condition,
            },
        )
        logger.debug(
            "Container %s: %s → %s (condition=%s)",
            container.container_id, old_status, next_status, container.condition
        )
        return event

    def allocate_container(
        self,
        container: ContainerState,
        booking_id: str,
        state: WorldState,
        sim_time: datetime,
    ) -> SimEvent:
        """
        Allocate an empty container to a booking.
        Doc 2 §6.2: EMPTY_AVAILABLE → ALLOCATED
        Updates EquipmentBalance at container location.
        """
        if container.status != "EMPTY_AVAILABLE":
            raise ValueError(
                f"Container {container.container_id} is {container.status}, cannot allocate"
            )
        if container.condition != "GOOD":
            raise ValueError(
                f"Container {container.container_id} condition is {container.condition}, not GOOD"
            )

        container.status = "ALLOCATED"
        container.booking_id = booking_id

        # Update local equipment balance
        if container.current_location_id:
            balance = state.get_equipment(container.current_location_id, container.equipment_type)
            balance.available = max(0, balance.available - 1)
            balance.allocated += 1

        return SimEvent(
            event_type=EventType.CONTAINER_GATE_OUT,  # triggers prep for gate out
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "booking_id": booking_id,
                "equipment_type": container.equipment_type,
                "location_id": container.current_location_id,
            },
        )

    def load_on_vessel(
        self,
        container: ContainerState,
        vessel_id: str,
        voyage_id: str,
        state: WorldState,
        sim_time: datetime,
    ) -> SimEvent:
        """
        Load container onto vessel for a voyage.
        Doc 2 §6.2: LOADED → IN_TRANSIT
        """
        container.status = "IN_TRANSIT"
        container.current_voyage_id = voyage_id
        from_loc = container.current_location_id
        container.current_location_id = None

        # Update balance
        if from_loc:
            bal = state.get_equipment(from_loc, container.equipment_type)
            bal.allocated = max(0, bal.allocated - 1)
            bal.in_transit += 1

        return SimEvent(
            event_type=EventType.CONTAINER_LOADED,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "vessel_id": vessel_id,
                "voyage_id": voyage_id,
                "from_location_id": from_loc,
            },
        )

    def discharge_from_vessel(
        self,
        container: ContainerState,
        dest_port_id: str,
        state: WorldState,
        sim_time: datetime,
    ) -> SimEvent:
        """
        Discharge container from vessel at destination port.
        Doc 2 §6.2: IN_TRANSIT → DISCHARGED
        """
        container.status = "DISCHARGED"
        container.current_location_id = dest_port_id
        container.current_voyage_id = None

        return SimEvent(
            event_type=EventType.CONTAINER_DISCHARGED,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "destination_port_id": dest_port_id,
                "booking_id": container.booking_id,
            },
        )

    def return_empty(
        self,
        container: ContainerState,
        location_id: str,
        state: WorldState,
        sim_time: datetime,
    ) -> SimEvent:
        """
        Customer returns empty container to depot/port.
        Doc 2 §6.2: CUSTOMER → EMPTY → EMPTY_AVAILABLE
        Updates equipment pool: available += 1
        """
        container.status = "EMPTY_AVAILABLE"
        container.current_location_id = location_id
        container.booking_id = None
        container.allocation_id = None
        container.available_from = sim_time

        bal = state.get_equipment(location_id, container.equipment_type)
        bal.available += 1

        return SimEvent(
            event_type=EventType.CONTAINER_RETURNED_EMPTY,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "location_id": location_id,
                "equipment_type": container.equipment_type,
            },
        )

    # ------------------------------------------------------------------
    # Damage & Condition Management (Doc 2 §6.5)
    # ------------------------------------------------------------------

    def evaluate_operational_damage(
        self,
        container: ContainerState,
        sim_time: datetime,
        state: WorldState,
    ) -> Optional[SimEvent]:
        """
        Evaluate damage probability during an operational event (handling, loading, transit).
        Doc 2 §6.5:
            Damage ~ Bernoulli(p_damage)
            If damage occurs:
                Severity ~ Bernoulli(p_severity)
                If severe: UNAVAILABLE
                If repairable: DAMAGED → MAINTENANCE → GOOD (scheduled repair)
        """
        try:
            p_damage = float(
                self._reg.get("CONTAINER_DAMAGE_PROBABILITY", scope_key=container.equipment_type)
            )
        except KeyError:
            p_damage = 0.002

        if not check_damage(p_damage, self._rng):
            return None

        try:
            p_severity = float(
                self._reg.get("CONTAINER_DAMAGE_SEVERITY", scope_key=container.equipment_type)
            )
        except KeyError:
            p_severity = 0.10

        is_severe = check_damage_severity(p_severity, self._rng)

        if is_severe:
            container.condition = "UNAVAILABLE"
            container.status = "UNAVAILABLE"
            logger.warning(
                "Container %s suffered SEVERE DAMAGE → UNAVAILABLE",
                container.container_id,
            )
            event_type = EventType.CONTAINER_UNAVAILABLE
            repair_hours = None
        else:
            container.condition = "DAMAGED"
            container.status = "MAINTENANCE"
            try:
                mean_repair_days = float(
                    self._reg.get("CONTAINER_REPAIR_TIME", scope_key=container.equipment_type)
                )
            except KeyError:
                mean_repair_days = 3.0
            repair_hours = calculate_repair_duration_hours(mean_repair_days, self._rng)
            container.available_from = sim_time + timedelta(hours=repair_hours)
            logger.info(
                "Container %s DAMAGED → MAINTENANCE for %.1f hours (ready at %s)",
                container.container_id,
                repair_hours,
                container.available_from.isoformat(),
            )
            event_type = EventType.CONTAINER_DAMAGED

        # If container was in an equipment balance, update it
        if container.current_location_id:
            bal = state.get_equipment(container.current_location_id, container.equipment_type)
            bal.unavailable += 1

        return SimEvent(
            event_type=event_type,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "container_id": container.container_id,
                "equipment_type": container.equipment_type,
                "condition": container.condition,
                "is_severe": is_severe,
                "repair_duration_hours": repair_hours,
                "available_from": container.available_from.isoformat() if container.available_from else None,
            },
        )

    def complete_repair(
        self,
        container: ContainerState,
        sim_time: datetime,
        state: WorldState,
    ) -> SimEvent:
        """
        Complete maintenance or repair for container: condition becomes GOOD,
        and container becomes EMPTY_AVAILABLE.
        Doc 2 §6.5: REPAIR / MAINTENANCE → GOOD
        """
        container.condition = "GOOD"
        container.status = "EMPTY_AVAILABLE"
        container.available_from = sim_time

        if container.current_location_id:
            bal = state.get_equipment(container.current_location_id, container.equipment_type)
            bal.unavailable = max(0, bal.unavailable - 1)
            bal.available += 1

        logger.info(
            "Container %s REPAIRED → GOOD / EMPTY_AVAILABLE at %s",
            container.container_id,
            container.current_location_id,
        )
        return SimEvent(
            event_type=EventType.CONTAINER_REPAIRED,
            entity_type="container",
            entity_id=container.container_id,
            simulation_time=sim_time,
            source="container_model",
            world_id=state.world_id,
            payload={
                "container_id": container.container_id,
                "equipment_type": container.equipment_type,
                "condition": container.condition,
                "location_id": container.current_location_id,
            },
        )
