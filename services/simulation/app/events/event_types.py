"""
Simulation Event Types
=======================
Defines all event types flowing through the simulation engine.

Doc 2 §25.5 — 10-field event schema:
    event_id, event_type, entity_type, entity_id,
    simulation_time, occurrence_time, source,
    world_id, payload, caused_by_event_id

Doc 2 §2.5 — Same-time event priority (10 levels):
    1. External/disruption activation
    2. Vessel movement/arrival
    3. Port/resource state changes
    4. Cargo/container operational events
    5. Demand generation
    6. Booking generation
    7. Information/forecast updates
    8. CargoPilot decision events
    9. Cost/accounting events
    10. Persistence/event publication

Directional flows:
    Simulation → CargoPilot: booking, vessel, port, container, disruption events
    CargoPilot → Simulation: allocation, repositioning, lease decision events
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Event Priority (Doc 2 §2.5)
# ---------------------------------------------------------------------------

class EventPriority(IntEnum):
    """
    10-level same-time event priority.
    Lower integer = processed first when timestamps are equal.
    Ensures deterministic reproducible ordering.
    """
    DISRUPTION_ACTIVATION = 1
    VESSEL_MOVEMENT = 2
    PORT_RESOURCE = 3
    CONTAINER_OPERATIONAL = 4
    DEMAND_GENERATION = 5
    BOOKING_GENERATION = 6
    INFORMATION_FORECAST = 7
    CARGOPILOT_DECISION = 8
    COST_ACCOUNTING = 9
    PERSISTENCE_PUBLICATION = 10


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

class EventType:
    """
    All simulation event type string constants.

    Grouped by source and direction:
        SIM_TO_CP: Simulation Engine → CargoPilot API
        CP_TO_SIM: CargoPilot API → Simulation Engine
        INTERNAL:  Internal simulation events (not published externally)
    """

    # --- Vessel events (priority 2) ---
    VESSEL_DEPARTED = "VESSEL_DEPARTED"
    VESSEL_ARRIVED = "VESSEL_ARRIVED"
    VESSEL_DELAYED = "VESSEL_DELAYED"
    VESSEL_BERTHED = "VESSEL_BERTHED"
    VESSEL_UNBERTHED = "VESSEL_UNBERTHED"
    VESSEL_ETA_UPDATED = "VESSEL_ETA_UPDATED"
    VESSEL_SPEED_CHANGED = "VESSEL_SPEED_CHANGED"
    VESSEL_MECHANICAL_FAILURE = "VESSEL_MECHANICAL_FAILURE"
    VESSEL_RECOVERED = "VESSEL_RECOVERED"

    # --- Port events (priority 3) ---
    PORT_CONGESTION_CHANGED = "PORT_CONGESTION_CHANGED"
    BERTH_OCCUPIED = "BERTH_OCCUPIED"
    BERTH_RELEASED = "BERTH_RELEASED"
    PORT_STRIKE_STARTED = "PORT_STRIKE_STARTED"
    PORT_STRIKE_ENDED = "PORT_STRIKE_ENDED"
    PORT_CLOSED = "PORT_CLOSED"
    PORT_REOPENED = "PORT_REOPENED"

    # --- Container events (priority 4) ---
    CONTAINER_GATE_IN = "CONTAINER_GATE_IN"
    CONTAINER_GATE_OUT = "CONTAINER_GATE_OUT"
    CONTAINER_LOADED = "CONTAINER_LOADED"
    CONTAINER_DISCHARGED = "CONTAINER_DISCHARGED"
    CONTAINER_DAMAGED = "CONTAINER_DAMAGED"
    CONTAINER_UNDER_MAINTENANCE = "CONTAINER_UNDER_MAINTENANCE"
    CONTAINER_REPAIRED = "CONTAINER_REPAIRED"
    CONTAINER_UNAVAILABLE = "CONTAINER_UNAVAILABLE"
    CONTAINER_RETURNED_EMPTY = "CONTAINER_RETURNED_EMPTY"
    EQUIPMENT_SHORTAGE_DETECTED = "EQUIPMENT_SHORTAGE_DETECTED"
    EQUIPMENT_SURPLUS_DETECTED = "EQUIPMENT_SURPLUS_DETECTED"

    # --- Demand events (priority 5) ---
    DEMAND_GENERATED = "DEMAND_GENERATED"
    DEMAND_SPIKE_STARTED = "DEMAND_SPIKE_STARTED"
    DEMAND_SPIKE_ENDED = "DEMAND_SPIKE_ENDED"

    # --- Booking events (priority 6) ---
    BOOKING_CREATED = "BOOKING_CREATED"
    BOOKING_CONFIRMED = "BOOKING_CONFIRMED"
    BOOKING_CANCELLED = "BOOKING_CANCELLED"
    BOOKING_MODIFIED = "BOOKING_MODIFIED"
    BOOKING_LOCKED = "BOOKING_LOCKED"
    """Emitted when T_sim ≥ T_departure - 7 days. Allocation freezes."""
    BOOKING_FULFILLED = "BOOKING_FULFILLED"

    # --- Forecast / information events (priority 7) ---
    FORECAST_UPDATED = "FORECAST_UPDATED"
    VESSEL_POSITION_PUBLISHED = "VESSEL_POSITION_PUBLISHED"
    """Transitions vessel ETA from INTERNAL_SIMULATION_KNOWN → KNOWN_TO_CARGOPILOT."""
    PORT_STATUS_PUBLISHED = "PORT_STATUS_PUBLISHED"

    # --- CargoPilot decision events (priority 8) ---
    ALLOCATION_COMMITTED = "ALLOCATION_COMMITTED"
    """CargoPilot → Simulation. Container allocated to booking."""
    ALLOCATION_LOCKED = "ALLOCATION_LOCKED"
    """CargoPilot acknowledges 7-day freeze."""
    REPOSITIONING_DISPATCHED = "REPOSITIONING_DISPATCHED"
    """CargoPilot → Simulation. Empty repositioning ordered."""
    LEASE_ORDERED = "LEASE_ORDERED"
    """CargoPilot → Simulation. Container lease ordered."""
    REPOSITIONING_COMPLETED = "REPOSITIONING_COMPLETED"
    LEASE_EQUIPMENT_AVAILABLE = "LEASE_EQUIPMENT_AVAILABLE"

    # --- Disruption events (priority 1) ---
    DISRUPTION_ACTIVATED = "DISRUPTION_ACTIVATED"
    DISRUPTION_ENDED = "DISRUPTION_ENDED"
    STORM_STARTED = "STORM_STARTED"
    STORM_ENDED = "STORM_ENDED"

    # --- Cost / accounting events (priority 9) ---
    DELAY_COST_INCURRED = "DELAY_COST_INCURRED"
    STORAGE_COST_INCURRED = "STORAGE_COST_INCURRED"
    LEASE_COST_INCURRED = "LEASE_COST_INCURRED"
    REPOSITIONING_COST_INCURRED = "REPOSITIONING_COST_INCURRED"
    SHORTAGE_PENALTY_INCURRED = "SHORTAGE_PENALTY_INCURRED"

    # --- Internal simulation events (not published externally) ---
    SIMULATION_STARTED = "SIMULATION_STARTED"
    SIMULATION_PAUSED = "SIMULATION_PAUSED"
    SIMULATION_RESUMED = "SIMULATION_RESUMED"
    SIMULATION_RESET = "SIMULATION_RESET"
    STEP_COMPLETED = "STEP_COMPLETED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


# Priority lookup table
EVENT_PRIORITY: Dict[str, EventPriority] = {
    # Disruption activation (1)
    EventType.DISRUPTION_ACTIVATED: EventPriority.DISRUPTION_ACTIVATION,
    EventType.DISRUPTION_ENDED: EventPriority.DISRUPTION_ACTIVATION,
    EventType.STORM_STARTED: EventPriority.DISRUPTION_ACTIVATION,
    EventType.STORM_ENDED: EventPriority.DISRUPTION_ACTIVATION,
    EventType.PORT_CLOSED: EventPriority.DISRUPTION_ACTIVATION,
    EventType.PORT_STRIKE_STARTED: EventPriority.DISRUPTION_ACTIVATION,
    # Vessel movement (2)
    EventType.VESSEL_DEPARTED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_ARRIVED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_DELAYED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_BERTHED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_UNBERTHED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_ETA_UPDATED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_SPEED_CHANGED: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_MECHANICAL_FAILURE: EventPriority.VESSEL_MOVEMENT,
    EventType.VESSEL_RECOVERED: EventPriority.VESSEL_MOVEMENT,
    # Port / resource (3)
    EventType.PORT_CONGESTION_CHANGED: EventPriority.PORT_RESOURCE,
    EventType.BERTH_OCCUPIED: EventPriority.PORT_RESOURCE,
    EventType.BERTH_RELEASED: EventPriority.PORT_RESOURCE,
    EventType.PORT_REOPENED: EventPriority.PORT_RESOURCE,
    EventType.PORT_STRIKE_ENDED: EventPriority.PORT_RESOURCE,
    # Container operational (4)
    EventType.CONTAINER_GATE_IN: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_GATE_OUT: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_LOADED: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_DISCHARGED: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_DAMAGED: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_UNDER_MAINTENANCE: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_REPAIRED: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_UNAVAILABLE: EventPriority.CONTAINER_OPERATIONAL,
    EventType.CONTAINER_RETURNED_EMPTY: EventPriority.CONTAINER_OPERATIONAL,
    EventType.EQUIPMENT_SHORTAGE_DETECTED: EventPriority.CONTAINER_OPERATIONAL,
    EventType.EQUIPMENT_SURPLUS_DETECTED: EventPriority.CONTAINER_OPERATIONAL,
    # Demand (5)
    EventType.DEMAND_GENERATED: EventPriority.DEMAND_GENERATION,
    EventType.DEMAND_SPIKE_STARTED: EventPriority.DEMAND_GENERATION,
    EventType.DEMAND_SPIKE_ENDED: EventPriority.DEMAND_GENERATION,
    # Booking (6)
    EventType.BOOKING_CREATED: EventPriority.BOOKING_GENERATION,
    EventType.BOOKING_CONFIRMED: EventPriority.BOOKING_GENERATION,
    EventType.BOOKING_CANCELLED: EventPriority.BOOKING_GENERATION,
    EventType.BOOKING_MODIFIED: EventPriority.BOOKING_GENERATION,
    EventType.BOOKING_LOCKED: EventPriority.BOOKING_GENERATION,
    EventType.BOOKING_FULFILLED: EventPriority.BOOKING_GENERATION,
    # Forecast / information (7)
    EventType.FORECAST_UPDATED: EventPriority.INFORMATION_FORECAST,
    EventType.VESSEL_POSITION_PUBLISHED: EventPriority.INFORMATION_FORECAST,
    EventType.PORT_STATUS_PUBLISHED: EventPriority.INFORMATION_FORECAST,
    # CargoPilot decisions (8)
    EventType.ALLOCATION_COMMITTED: EventPriority.CARGOPILOT_DECISION,
    EventType.ALLOCATION_LOCKED: EventPriority.CARGOPILOT_DECISION,
    EventType.REPOSITIONING_DISPATCHED: EventPriority.CARGOPILOT_DECISION,
    EventType.LEASE_ORDERED: EventPriority.CARGOPILOT_DECISION,
    EventType.REPOSITIONING_COMPLETED: EventPriority.CARGOPILOT_DECISION,
    EventType.LEASE_EQUIPMENT_AVAILABLE: EventPriority.CARGOPILOT_DECISION,
    # Cost (9)
    EventType.DELAY_COST_INCURRED: EventPriority.COST_ACCOUNTING,
    EventType.STORAGE_COST_INCURRED: EventPriority.COST_ACCOUNTING,
    EventType.LEASE_COST_INCURRED: EventPriority.COST_ACCOUNTING,
    EventType.REPOSITIONING_COST_INCURRED: EventPriority.COST_ACCOUNTING,
    EventType.SHORTAGE_PENALTY_INCURRED: EventPriority.COST_ACCOUNTING,
    # Persistence (10)
    EventType.STEP_COMPLETED: EventPriority.PERSISTENCE_PUBLICATION,
    EventType.SIMULATION_STARTED: EventPriority.PERSISTENCE_PUBLICATION,
    EventType.SIMULATION_PAUSED: EventPriority.PERSISTENCE_PUBLICATION,
    EventType.SIMULATION_RESUMED: EventPriority.PERSISTENCE_PUBLICATION,
    EventType.SIMULATION_RESET: EventPriority.PERSISTENCE_PUBLICATION,
    EventType.VALIDATION_FAILED: EventPriority.PERSISTENCE_PUBLICATION,
}



# ---------------------------------------------------------------------------
# Event dataclass (in-process representation)
# ---------------------------------------------------------------------------

@dataclass
class SimEvent:
    """
    In-process simulation event.

    Matches the 10-field schema from Doc 2 §25.5.
    This is the in-process representation; persistence uses SimulationEvent ORM model.
    """
    event_type: str
    entity_type: str
    entity_id: str
    simulation_time: datetime
    source: str
    world_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: uuid.UUID = field(default_factory=uuid.uuid4)
    occurrence_time: Optional[datetime] = None
    caused_by_event_id: Optional[uuid.UUID] = None
    run_id: Optional[uuid.UUID] = None

    def __post_init__(self) -> None:
        if self.occurrence_time is None:
            self.occurrence_time = self.simulation_time

    @property
    def priority(self) -> EventPriority:
        """Return the event's processing priority (Doc 2 §2.5)."""
        return EVENT_PRIORITY.get(self.event_type, EventPriority.PERSISTENCE_PUBLICATION)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to the 10-field schema for DB persistence."""
        return {
            "event_id": str(self.event_id),
            "event_type": self.event_type,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "simulation_time": self.simulation_time.isoformat(),
            "occurrence_time": self.occurrence_time.isoformat() if self.occurrence_time else None,
            "source": self.source,
            "world_id": self.world_id,
            "payload": self.payload,
            "caused_by_event_id": str(self.caused_by_event_id) if self.caused_by_event_id else None,
        }
