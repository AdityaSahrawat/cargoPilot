"""
World State
============
In-process working representation of S(t) — the simulation world state.

Architectural Rule 2 (from implementation plan):
    PostgreSQL is the single authoritative persistent source of truth.
    WorldState is a working cache for the current simulation step only.

    PostgreSQL
        ↓ load at step start
    WorldState  (in-process cache)
        ↓ simulation executes
    WorldState changes
        ↓ persist after step
    PostgreSQL

WorldState is NOT a second database.
After each advancement step, all changes are written back to PostgreSQL.

Architectural Rule 3 — Visibility:
    Future entities carry a visibility flag:
        INTERNAL_SIMULATION_KNOWN   — simulator knows internally
        KNOWN_TO_CARGOPILOT         — published via Kafka / DB write

Doc 2 §1.3:
    S(t) = { P(t), V(t), Y(t), C(t), B(t), D(t), E(t), L(t), A(t), R(t) }
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

class Visibility(str, Enum):
    """
    Governs whether future simulation knowledge has been published to CargoPilot.

    Architectural Rule 3:
        Simulator may know V100 arrives Day 8 (INTERNAL_SIMULATION_KNOWN).
        CargoPilot only receives that ETA after VESSEL_ETA_UPDATED is published.

    Advancement validation checks no INTERNAL_SIMULATION_KNOWN entity was
    accidentally leaked to Kafka.
    """
    INTERNAL_SIMULATION_KNOWN = "INTERNAL_SIMULATION_KNOWN"
    KNOWN_TO_CARGOPILOT = "KNOWN_TO_CARGOPILOT"


# ---------------------------------------------------------------------------
# Per-entity state dataclasses
# ---------------------------------------------------------------------------

@dataclass
class VesselState:
    """
    Runtime vessel state. Simulator-owned.
    Static attributes (name, class, capacity) come from services/api vessels table.

    Doc 2 §4.2
    """
    vessel_id: str
    status: str          # AVAILABLE|SCHEDULED|IN_TRANSIT|ARRIVED|WAITING_FOR_BERTH|IN_PORT|DEPARTED|DELAYED|UNAVAILABLE
    name: str = ""                     # Human-readable vessel name, e.g. "MV Ever Quantum"
    current_voyage_id: Optional[str] = None
    current_port_id: Optional[str] = None
    origin_port_id: Optional[str] = None
    """Origin port of the current active voyage leg (for map interpolation)."""
    destination_port_id: Optional[str] = None
    """Destination port of the current active voyage leg (for map interpolation)."""
    position_fraction: float = 0.0
    """Fraction of current voyage leg completed: 0.0 → 1.0"""
    distance_remaining_nm: float = 0.0
    current_speed_knots: float = 18.0
    base_speed_knots: Optional[float] = None
    eta: Optional[datetime] = None
    eta_visibility: Visibility = Visibility.INTERNAL_SIMULATION_KNOWN
    schedule_variance_hours: float = 0.0
    """ScheduleVariance = ActualTime - ScheduledTime. Positive = delayed. Doc 2 §4.8"""
    current_load_teu: float = 0.0
    capacity_teu: float = 0.0
    condition: str = "GOOD"            # GOOD | DAMAGED | MAINTENANCE | UNAVAILABLE
    next_failure_at: Optional[float] = None
    """SimPy time (hours since start) of next scheduled mechanical failure."""

    def __post_init__(self) -> None:
        if self.base_speed_knots is None:
            self.base_speed_knots = self.current_speed_knots


@dataclass
class PortState:
    """
    Runtime port state. Simulator-owned.
    Static attributes (name, UNLOCODE, coordinates) come from services/api locations table.

    Doc 2 §5.1
    """
    port_id: str
    unlocode: str
    name: str = ""                     # Human-readable port name, e.g. "Shanghai"
    latitude: float = 0.0             # WGS-84 latitude for map rendering
    longitude: float = 0.0            # WGS-84 longitude for map rendering
    berths_total: int = 4
    berths_occupied: int = 0
    vessel_queue: List[str] = field(default_factory=list)
    """Queue of vessel_ids waiting for a berth (FIFO)."""
    yard_capacity_teu: int = 10000
    yard_occupancy_teu: float = 0.0
    congestion_index: float = 0.0
    """
    F_cong from Doc 2 §5.5:
        F_cong = 1 when U ≤ U_c
        F_cong = 1 + α × ((U - U_c)/(1 - U_c))^β when U > U_c
    """
    is_strike_active: bool = False
    strike_capacity_factor: float = 1.0
    is_closed: bool = False

    @property
    def berths_available(self) -> int:
        return max(0, self.berths_total - self.berths_occupied)

    @property
    def yard_utilization(self) -> float:
        if self.yard_capacity_teu <= 0:
            return 0.0
        return self.yard_occupancy_teu / self.yard_capacity_teu


@dataclass
class VoyageState:
    """
    A scheduled voyage (a single leg from origin to destination).

    Future voyages beyond the current planning window are tagged
    INTERNAL_SIMULATION_KNOWN until published per the visibility model.

    Doc 2 §4.3, §4.10
    """
    voyage_id: str
    vessel_id: str
    origin_port_id: str
    destination_port_id: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    actual_departure: Optional[datetime] = None
    estimated_arrival: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    status: str = "SCHEDULED"     # SCHEDULED | ACTIVE | COMPLETED | CANCELLED
    route_distance_nm: float = 0.0
    capacity_teu: float = 0.0
    booked_teu: float = 0.0
    remaining_turnaround_hours: float = 0.0
    visibility: Visibility = Visibility.INTERNAL_SIMULATION_KNOWN


@dataclass
class ContainerState:
    """
    Individual container unit lifecycle state.

    Doc 2 §6.1, §6.2
    """
    container_id: str
    equipment_type: str           # 20DC | 40DC | 40HC
    status: str                   # EMPTY_AVAILABLE | ALLOCATED | GATE_OUT | STUFFING |
                                  # LOADED | IN_TRANSIT | DISCHARGED | CUSTOMER | EMPTY
    condition: str = "GOOD"       # GOOD | DAMAGED | MAINTENANCE | UNAVAILABLE
    current_location_id: Optional[str] = None
    current_voyage_id: Optional[str] = None
    booking_id: Optional[str] = None
    allocation_id: Optional[str] = None
    available_from: Optional[datetime] = None
    """T_sim when this container becomes available (after repair/maintenance/return)."""


@dataclass
class BookingState:
    """
    Booking created by the simulation demand model.

    Doc 2 §8.4, §9
    """
    booking_id: str
    origin_port_id: str
    destination_port_id: str
    equipment_type: str
    quantity: int
    cargo_ready_time: datetime
    booking_time: datetime
    status: str = "SUBMITTED"     # SUBMITTED | CONFIRMED | ALLOCATED | CANCELLED | FULFILLED
    lock_status: str = "UNLOCKED"  # UNLOCKED | LOCKED
    voyage_id: Optional[str] = None
    allocation_id: Optional[str] = None
    cutoff_time: Optional[datetime] = None
    """T_cutoff = T_departure - 7 days. At or after cutoff → LOCKED. Doc 2 §9.4"""


@dataclass
class EquipmentBalance:
    """
    Equipment availability balance per (location, equipment_type).

    Doc 2 §11:
        Shortage = max(0, Required - Available)
        Surplus  = max(0, Available - Target)
        Deficit  = max(0, Target - Available)
    """
    location_id: str
    equipment_type: str
    available: int = 0
    allocated: int = 0
    in_transit: int = 0
    unavailable: int = 0
    target: int = 0
    """Target inventory level (safety stock)."""

    @property
    def total(self) -> int:
        return self.available + self.allocated + self.in_transit + self.unavailable

    @property
    def shortage(self) -> int:
        required = self.allocated  # simplification: required = currently allocated
        return max(0, required - self.available)

    @property
    def surplus(self) -> int:
        return max(0, self.available - self.target)

    @property
    def deficit(self) -> int:
        return max(0, self.target - self.available)


@dataclass
class DisruptionState:
    """
    Active or historical disruption.

    Doc 2 §14.2, §14.3:
        Active period vs. persistent consequences.
        A disruption can end while its consequences remain in world state.
    """
    disruption_id: str
    disruption_type: str          # DisruptionType enum value
    status: str = "ACTIVE"        # SCHEDULED | ACTIVE | ENDED
    severity: float = 0.5
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    duration_hours: Optional[float] = None
    affected_entity_ids: List[str] = field(default_factory=list)
    """Empty = all eligible entities."""
    parameter_overrides: Dict[str, Any] = field(default_factory=dict)
    caused_by_event_id: Optional[UUID] = None


@dataclass
class LeaseState:
    """Active lease agreement (CargoPilot-owned decision, simulator executes)."""
    lease_id: str
    location_id: str
    equipment_type: str
    quantity: int
    daily_rate: float
    start_time: datetime
    duration_days: float
    status: str = "PENDING"       # PENDING | ACTIVE | COMPLETED
    equipment_available_at: Optional[datetime] = None


@dataclass
class RepositioningState:
    """Active repositioning movement (CargoPilot-owned decision, simulator executes)."""
    reposition_id: str
    source_location_id: str
    destination_location_id: str
    equipment_type: str
    quantity: int
    departure_time: datetime
    estimated_arrival: datetime
    status: str = "IN_TRANSIT"    # IN_TRANSIT | COMPLETED


@dataclass
class AllocationState:
    """
    Container allocation (CargoPilot-owned). Simulator observes only.
    Simulator does NOT write to equipment_assignments.

    Doc 2 §9.1
    """
    allocation_id: str
    booking_id: str
    container_id: str
    voyage_id: str
    status: str = "ALLOCATED"     # ALLOCATED | MODIFIABLE | LOCKED | COMPLETED
    locked: bool = False


@dataclass
class BacklogState:
    """
    Operational backlog for a resource (port, vessel, etc.).

    Doc 2 §21:
        Backlog_{t+1} = Backlog_t + Arrivals - Completed,  Backlog ≥ 0
    """
    resource_id: str
    resource_type: str            # PORT | VESSEL
    backlog_count: int = 0


@dataclass
class DemandState:
    """
    Active demand signals per OD pair and equipment type.
    Updated each time the demand model fires (every DEMAND_GENERATION_INTERVAL hours).

    Doc 2 §7
    """
    # (origin_port_id, destination_port_id, equipment_type) → demand count for current period
    current_demand: Dict[Tuple[str, str, str], float] = field(default_factory=dict)
    historical_demand: Dict[Tuple[str, str, str, int], float] = field(default_factory=dict)
    """Key: (origin, destination, equipment_type, day_offset) → demand volume."""


@dataclass
class KPIAccumulator:
    """
    Running KPI totals for the simulation run.

    Doc 2 §22 — Cost Models
    """
    total_delay_hours: float = 0.0
    total_delay_cost: float = 0.0
    total_lease_cost: float = 0.0
    total_repositioning_cost: float = 0.0
    total_storage_cost: float = 0.0
    total_shortage_penalty: float = 0.0
    total_disruption_cost: float = 0.0
    total_recovery_cost: float = 0.0
    vessels_delayed: int = 0
    bookings_created: int = 0
    bookings_fulfilled: int = 0
    bookings_cancelled: int = 0
    equipment_shortages: int = 0

    @property
    def total_cost(self) -> float:
        return (
            self.total_delay_cost
            + self.total_lease_cost
            + self.total_repositioning_cost
            + self.total_storage_cost
            + self.total_shortage_penalty
            + self.total_disruption_cost
            + self.total_recovery_cost
        )


# ---------------------------------------------------------------------------
# World State — S(t)
# ---------------------------------------------------------------------------

@dataclass
class WorldState:
    """
    In-process working cache for one simulation step.

    Represents S(t) = { P(t), V(t), Y(t), C(t), B(t), D(t), E(t), L(t), A(t), R(t) }
    per Doc 2 §1.3.

    Lifecycle per step:
        1. Loaded from PostgreSQL at step start (world_seeder or persistence layer)
        2. Mutated by domain model handlers during SimPy execution
        3. All changes persisted to PostgreSQL at step end
        4. Events written to simulation_events + outbox

    This is NOT the authoritative state — PostgreSQL is.
    """
    run_id: UUID
    simulation_time: datetime
    world_id: str
    world_baseline_id: Optional[str] = None

    # P(t) — Port state (simulator-owned)
    ports: Dict[str, PortState] = field(default_factory=dict)

    # V(t) — Vessel state (simulator-owned)
    vessels: Dict[str, VesselState] = field(default_factory=dict)

    # Y(t) — Voyage state (simulator-owned, may include INTERNAL_SIMULATION_KNOWN)
    voyages: Dict[str, VoyageState] = field(default_factory=dict)

    # C(t) — Container state (simulator-owned for status/location fields)
    containers: Dict[str, ContainerState] = field(default_factory=dict)

    # B(t) — Booking state (simulator creates, CargoPilot allocates)
    bookings: Dict[str, BookingState] = field(default_factory=dict)

    # D(t) — Demand state
    demand: DemandState = field(default_factory=DemandState)

    # E(t) — Equipment balance per (location_id, equipment_type)
    equipment: Dict[Tuple[str, str], EquipmentBalance] = field(default_factory=dict)

    # L(t) — Lease state (CargoPilot-owned decisions, simulator reads)
    leases: Dict[str, LeaseState] = field(default_factory=dict)

    # A(t) — Allocation state (CargoPilot-owned, simulator reads only)
    allocations: Dict[str, AllocationState] = field(default_factory=dict)

    # Repositioning orders (CargoPilot-owned, simulator executes movement)
    repositioning_orders: Dict[str, RepositioningState] = field(default_factory=dict)

    # R(t) — Disruption/scenario state
    disruptions: List[DisruptionState] = field(default_factory=list)

    # Backlog per resource
    backlog: Dict[str, BacklogState] = field(default_factory=dict)

    # KPIs accumulated for this run
    kpis: KPIAccumulator = field(default_factory=KPIAccumulator)

    # Events emitted during the current step (flushed to DB after step)
    step_events: List[Any] = field(default_factory=list)
    """Populated from EventBus.flush_step_log() at step end."""

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def get_vessel(self, vessel_id: str) -> VesselState:
        if vessel_id not in self.vessels:
            raise KeyError(f"Vessel '{vessel_id}' not found in world state.")
        return self.vessels[vessel_id]

    def get_port(self, port_id: str) -> PortState:
        if port_id not in self.ports:
            raise KeyError(f"Port '{port_id}' not found in world state.")
        return self.ports[port_id]

    def get_equipment(self, location_id: str, equipment_type: str) -> EquipmentBalance:
        key = (location_id, equipment_type)
        if key not in self.equipment:
            self.equipment[key] = EquipmentBalance(
                location_id=location_id,
                equipment_type=equipment_type,
            )
        return self.equipment[key]

    @property
    def active_disruptions(self) -> List[DisruptionState]:
        return [d for d in self.disruptions if d.status == "ACTIVE"]
