"""
Simulator-Owned Database Models
=================================
SQLAlchemy ORM models for tables owned exclusively by the simulation engine.

Ownership rules (Doc 2 §25.1):
    SIMULATOR-OWNED (this file):
        simulation_runs, simulation_events, simulation_parameters,
        simulation_snapshots, simulation_outbox,
        vessel_sim_state, port_sim_state, disruptions

    CARGOPILOT-OWNED (services/api, NOT here):
        equipment_assignments, optimization_runs, repositioning decisions

    SHARED READ (services/api schema, simulation reads only):
        vessels, locations, voyages, voyage_legs,
        containers, bookings

The simulation engine NEVER writes to CargoPilot-owned tables.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import SimBase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ---------------------------------------------------------------------------
# 1. SimulationRun — first-class concept (Rule 8)
# ---------------------------------------------------------------------------

class SimulationRun(SimBase):
    """
    A first-class simulation run record.

    Multiple runs can share the same world_id, allowing comparison:
        Run A → NORMAL
        Run B → STORM
        Run C → DEMAND_SPIKE
    using the same initial World 2 dataset.
    """
    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    world_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """Identifier of the initial world dataset (e.g. 'world-2')."""

    scenario_id: Mapped[str] = mapped_column(String(64), nullable=False)
    """Scenario used for this run (e.g. 'NORMAL', 'STORM')."""

    random_seed: Mapped[int] = mapped_column(Integer, nullable=False)
    """Global random seed for reproducibility. Doc 2 §3.2."""

    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    """SHA-256 hash of parameter configuration at run start."""

    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """Virtual clock start time T_sim(0)."""

    current_sim_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """Current virtual clock T_sim — updated after each advancement."""

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="CREATED"
    )
    """CREATED | RUNNING | PAUSED | COMPLETED | RESET | ERROR"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_sim_runs_world_scenario", "world_id", "scenario_id"),
    )


# ---------------------------------------------------------------------------
# 2. SimulationEvent — full event log with 10-field schema (Doc 2 §25.5)
# ---------------------------------------------------------------------------

class SimulationEvent(SimBase):
    """
    Immutable event record. Every state-changing event is written here.

    10-field schema (Doc 2 §25.5):
        event_id, event_type, entity_type, entity_id,
        simulation_time, occurrence_time, source,
        world_id, payload, caused_by_event_id
    """
    __tablename__ = "simulation_events"

    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    simulation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    """T_sim at which this event was processed."""

    occurrence_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """When the event actually occurred in simulation time (may differ due to visibility delay)."""

    source: Mapped[str] = mapped_column(String(64), nullable=False)
    """'simulation-engine' | 'cargopilot' | 'admin'"""

    world_id: Mapped[str] = mapped_column(String(64), nullable=False)

    payload: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    caused_by_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    """Links to parent event enabling causal chain tracing. Doc 2 §25.5."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_sim_events_run_time", "run_id", "simulation_time"),
        Index("ix_sim_events_type_entity", "event_type", "entity_id"),
    )


# ---------------------------------------------------------------------------
# 3. SimulationParameter — runtime parameter values per scope
# ---------------------------------------------------------------------------

class SimulationParameter(SimBase):
    """
    Stores the effective value of each parameter for a simulation run,
    including any scope-specific overrides and runtime changes.

    Runtime parameter changes (Doc 2 §24.3):
        Admin change → PostgreSQL → simulation observes →
        affected future events recalculated. Past events unchanged.
    """
    __tablename__ = "simulation_parameters"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parameter_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    """Port ID, vessel class, route ID, etc. None = global."""
    value_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    """Stored as JSON to support any value type."""
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("run_id", "parameter_name", "scope_key",
                         name="uq_sim_param_run_name_scope"),
    )


# ---------------------------------------------------------------------------
# 4. SimulationSnapshot — periodic WorldState snapshots
# ---------------------------------------------------------------------------

class SimulationSnapshot(SimBase):
    """
    Periodic snapshots of world state for debugging and replay.
    Written at the end of each advancement step.
    """
    __tablename__ = "simulation_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    simulation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    snapshot_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_sim_snapshot_run_time", "run_id", "simulation_time"),
    )


# ---------------------------------------------------------------------------
# 5. SimulationOutbox — transactional outbox for Kafka (Rule 5)
# ---------------------------------------------------------------------------

class SimulationOutbox(SimBase):
    """
    Transactional outbox for reliable Kafka publication.

    Pattern (Doc 2 §25, Rule 5):
        Single DB transaction:
            1. State change
            2. INSERT into outbox
        PostgreSQL COMMIT
        Background publisher reads outbox → Kafka → marks published

    This ensures PostgreSQL and Kafka never permanently disagree.
    If Kafka fails after commit, the outbox row retries on next step.
    """
    __tablename__ = "simulation_outbox"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    kafka_topic: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    """Null = pending. Set when successfully published to Kafka."""

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_outbox_unpublished", "published_at", "created_at"),
    )


# ---------------------------------------------------------------------------
# 6. VesselSimState — simulator-owned vessel runtime state
# ---------------------------------------------------------------------------

class VesselSimState(SimBase):
    """
    Simulator-owned runtime state for each vessel.

    Separates dynamic simulation fields (position, speed, ETA) from
    the static vessel attributes in services/api 'vessels' table.

    Ownership: Simulation writes. CargoPilot reads.
    """
    __tablename__ = "vessel_sim_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    vessel_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    """References services/api vessels.id (UUID as string)."""

    status: Mapped[str] = mapped_column(String(32), nullable=False)
    """AVAILABLE | SCHEDULED | IN_TRANSIT | ARRIVED | WAITING_FOR_BERTH |
       IN_PORT | DEPARTED | DELAYED | UNAVAILABLE"""

    current_voyage_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    current_port_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    position_fraction: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    """Fraction of current leg completed: 0.0 (at origin) → 1.0 (at destination)."""

    distance_remaining_nm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    current_speed_knots: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    eta: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    """Estimated arrival at next port. INTERNAL_SIMULATION_KNOWN by default."""

    eta_visibility: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INTERNAL_SIMULATION_KNOWN"
    )
    """INTERNAL_SIMULATION_KNOWN | KNOWN_TO_CARGOPILOT"""

    schedule_variance_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """ScheduleVariance = ActualTime - ScheduledTime. Positive = delayed."""

    current_load_teu: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    condition: Mapped[str] = mapped_column(String(32), nullable=False, default="GOOD")

    simulation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    """T_sim when this state was last written."""

    __table_args__ = (
        UniqueConstraint("run_id", "vessel_id", name="uq_vessel_sim_run"),
        Index("ix_vessel_sim_run_status", "run_id", "status"),
    )


# ---------------------------------------------------------------------------
# 7. PortSimState — simulator-owned port runtime state
# ---------------------------------------------------------------------------

class PortSimState(SimBase):
    """
    Simulator-owned runtime state for each port.

    Separates simulation dynamics (congestion, berths) from
    static port attributes in services/api 'locations' table.

    Ownership: Simulation writes. CargoPilot reads.
    """
    __tablename__ = "port_sim_state"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    port_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    """References services/api locations.id (UUID as string)."""

    berths_total: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    berths_occupied: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    yard_capacity_teu: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    yard_occupancy_teu: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    vessel_queue_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    """Number of vessels waiting for a berth."""

    congestion_index: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    """
    Derived congestion factor F_cong from Doc 2 §5.5:
    F_cong = 1 when U ≤ U_c
    F_cong = 1 + α × ((U - U_c)/(1 - U_c))^β when U > U_c
    Stored for visibility to CargoPilot.
    """

    is_strike_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    strike_capacity_factor: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    simulation_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("run_id", "port_id", name="uq_port_sim_run"),
        Index("ix_port_sim_run_congestion", "run_id", "congestion_index"),
    )


# ---------------------------------------------------------------------------
# 8. DisruptionRecord — active and historical disruptions
# ---------------------------------------------------------------------------

class DisruptionRecord(SimBase):
    """
    Tracks all disruptions (active window and ended).

    Note: A disruption can end while its consequences persist in world state.
    Doc 2 §14.3: active period vs. persistent consequences.

    Disruptions are only created through the event system.
    inject_disruption() creates a DISRUPTION_ACTIVATED event → handler creates this record.
    """
    __tablename__ = "disruptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("simulation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    disruption_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    """DisruptionType enum value: STORM | PORT_STRIKE | etc."""

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="SCHEDULED")
    """SCHEDULED | ACTIVE | ENDED"""

    severity: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    """Severity s ∈ [0,1]. Used in F_weather = 1 - α_s × s for storms."""

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    affected_entity_ids: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    """List of vessel/port IDs affected. null = all eligible entities."""

    behavior_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    """Parameter overrides and behavioral modifiers active during this disruption."""

    caused_by_event_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    """Event that created this disruption record."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_disruptions_run_type", "run_id", "disruption_type"),
        Index("ix_disruptions_run_status", "run_id", "status"),
    )
