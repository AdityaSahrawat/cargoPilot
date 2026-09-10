"""
Simulation Controller
=====================
Stateful controller coordinating the discrete event execution engine,
domain models, parameter overrides, and REST / API interaction.

Architectural Rules enforced:
    Rule 1 — PostgreSQL authoritative persistence (state flushed at step end)
    Rule 2 — DB ownership boundaries respected
    Rule 3 — Visibility gating (INTERNAL_SIMULATION_KNOWN → KNOWN_TO_CARGOPILOT)
    Rule 4 — All mutations pass through event system (inject_disruption creates event)
    Rule 5 — Transactional outbox for Kafka consistency

Doc 1 §5, Doc 2 §29.5
"""
from __future__ import annotations

import asyncio
import copy
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock.simulation_clock import SimulationClock
from app.config.disruption_types import DisruptionType
from app.config.parameters import ParameterRegistry
from app.config.scenario_configs import get_scenario
from app.db.sim_models import WorldBaseline
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.events.event_types import EventType, SimEvent
from app.models.allocation_model import AllocationModel
from app.models.backlog_model import BacklogModel
from app.models.booking_model import BookingModel
from app.models.container_model import ContainerModel
from app.models.cost_model import CostModel
from app.models.demand_model import DemandModel
from app.models.disruption_engine import DisruptionEngine
from app.models.equipment_model import EquipmentModel
from app.models.failure_model import FailureModel
from app.models.forecasting_model import ForecastingModel
from app.models.import_return_model import ImportReturnModel
from app.models.leasing_model import LeasingModel
from app.models.port_model import PortModel
from app.models.recovery_model import RecoveryModel
from app.models.repositioning_model import RepositioningModel
from app.models.timeline_model import TimelineModel
from app.models.vessel_model import VesselModel
from app.models.visibility_model import VisibilityModel
from app.world.validator import validate_advancement_state, validate_local_event
from app.world.world_seeder import WorldSeeder, compute_travel_time_hours, stable_world_seed
from app.world.world_state import WorldState

logger = logging.getLogger(__name__)


class SimulationStatus:
    IDLE = "IDLE"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"


class SimulationController:
    """
    Central stateful controller for the CargoPilot simulation service.
    """

    def __init__(
        self,
        clock: SimulationClock,
        registry: ParameterRegistry,
        event_bus: EventBus,
        kernel: SimulationKernel,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
    ) -> None:
        self._clock = clock
        self._base_reg = registry
        self._reg = registry.clone()
        self._bus = event_bus
        self._kernel = kernel
        self._session_factory = session_factory

        self._lock = asyncio.Lock()
        self._status = SimulationStatus.IDLE
        self._state: Optional[WorldState] = None
        self._scenario_id: str = "normal"
        self._seed: int = 42
        self._rng = random.Random(42)

        # Baseline in-memory fallback cache: (world_id, version) -> (serialized_dict, baseline_id)
        self._baselines_cache: Dict[Tuple[str, str], Tuple[Dict[str, Any], UUID]] = {}

        # Instantiate domain models
        self._init_domain_models(self._reg, self._rng)

        # Register validators on kernel
        self._kernel.register_local_validator(validate_local_event)
        self._kernel.register_advancement_validator(validate_advancement_state)

        # Register event handlers on kernel
        self._register_event_handlers()

        logger.info("SimulationController initialized")

    def _init_domain_models(self, reg: ParameterRegistry, rng: random.Random) -> None:
        """Initialize domain models with the run-specific parameter registry."""
        self._port_model = PortModel(reg)
        self._vessel_model = VesselModel(reg, self._port_model)
        self._container_model = ContainerModel(reg, rng)
        self._demand_model = DemandModel(reg, rng)
        self._booking_model = BookingModel(reg, rng)
        self._allocation_model = AllocationModel(reg)
        self._import_return_model = ImportReturnModel(reg, rng)
        self._equipment_model = EquipmentModel(reg)
        self._leasing_model = LeasingModel(reg)
        self._repositioning_model = RepositioningModel(reg)
        self._disruption_engine = DisruptionEngine(
            reg, vessel_model=self._vessel_model, port_model=self._port_model
        )
        self._failure_model = FailureModel(reg, rng)
        self._recovery_model = RecoveryModel(reg, vessel_model=self._vessel_model)
        self._forecasting_model = ForecastingModel(reg, rng)
        self._visibility_model = VisibilityModel(reg)
        self._timeline_model = TimelineModel(reg)
        self._backlog_model = BacklogModel(reg)
        self._cost_model = CostModel(reg)

    # ------------------------------------------------------------------
    # Handler Registration
    # ------------------------------------------------------------------

    def _register_event_handlers(self) -> None:
        """Wire model logic to kernel event types."""
        # Vessel arrival
        def on_vessel_arrived(event: SimEvent, state: WorldState) -> None:
            vessel_id = event.entity_id
            vessel = state.get_vessel(vessel_id)
            if not vessel.current_voyage_id:
                return
            voyage = state.voyages.get(vessel.current_voyage_id)
            if not voyage:
                return
            port = state.get_port(voyage.destination_port_id)

            _, turnaround = self._vessel_model.arrive_vessel(
                vessel, voyage, port, event.simulation_time, state
            )
            if turnaround is not None:
                unberth_time = self._kernel.current_simpy_time + turnaround
                unberth_event = SimEvent(
                    event_type=EventType.VESSEL_UNBERTHED,
                    entity_type="vessel",
                    entity_id=vessel_id,
                    simulation_time=event.simulation_time + timedelta(hours=turnaround),
                    source="vessel_model",
                    world_id=state.world_id,
                    payload={"port_id": port.port_id, "voyage_id": voyage.voyage_id},
                )
                self._kernel.schedule(unberth_event, at_simpy_time=unberth_time)

        # Vessel unberthing
        def on_vessel_unberth(event: SimEvent, state: WorldState) -> None:
            vessel_id = event.entity_id
            vessel = state.get_vessel(vessel_id)
            port_id = event.payload.get("port_id") or vessel.current_port_id
            if not port_id or port_id not in state.ports:
                return
            port = state.get_port(port_id)
            _, next_vessel_id = self._vessel_model.complete_port_stay(
                vessel, port, event.simulation_time, state
            )
            if next_vessel_id and next_vessel_id in state.vessels:
                # Queued vessel now berths
                next_v = state.get_vessel(next_vessel_id)
                next_v.status = "IN_PORT"
                next_v.current_port_id = port.port_id
                t_around = self._port_model.calculate_turnaround_time_hours(port, next_v)
                unberth_at = self._kernel.current_simpy_time + t_around
                nxt_unberth = SimEvent(
                    event_type=EventType.VESSEL_UNBERTHED,
                    entity_type="vessel",
                    entity_id=next_vessel_id,
                    simulation_time=event.simulation_time + timedelta(hours=t_around),
                    source="vessel_model",
                    world_id=state.world_id,
                    payload={"port_id": port.port_id},
                )
                self._kernel.schedule(nxt_unberth, at_simpy_time=unberth_at)

        # Berth released (frees berth, unqueues waiting vessel if any)
        def on_berth_released(event: SimEvent, state: WorldState) -> None:
            port_id = event.payload.get("port_id") or event.entity_id
            if port_id not in state.ports:
                return
            port = state.get_port(port_id)
            if port.berths_occupied > 0:
                port.berths_occupied -= 1
            if port.vessel_queue:
                next_vessel_id = port.vessel_queue.pop(0)
                if next_vessel_id in state.vessels:
                    port.berths_occupied += 1
                    next_v = state.get_vessel(next_vessel_id)
                    next_v.status = "IN_PORT"
                    next_v.current_port_id = port.port_id
                    t_around = self._port_model.calculate_turnaround_time_hours(port, next_v)
                    unberth_at = self._kernel.current_simpy_time + t_around
                    nxt_unberth = SimEvent(
                        event_type=EventType.VESSEL_UNBERTHED,
                        entity_type="vessel",
                        entity_id=next_vessel_id,
                        simulation_time=event.simulation_time + timedelta(hours=t_around),
                        source="vessel_model",
                        world_id=state.world_id,
                        payload={"port_id": port.port_id},
                    )
                    self._kernel.schedule(nxt_unberth, at_simpy_time=unberth_at)

        # Demand generation batch
        def on_demand_generated(event: SimEvent, state: WorldState) -> None:
            # Reschedule next demand batch at +12h
            next_at = self._kernel.current_simpy_time + 12.0
            self._kernel.schedule(
                SimEvent(
                    event_type=EventType.DEMAND_GENERATED,
                    entity_type="demand",
                    entity_id="system",
                    simulation_time=event.simulation_time + timedelta(hours=12.0),
                    source="demand_model",
                    world_id=state.world_id,
                ),
                at_simpy_time=next_at,
            )

        # Booking cutoff locks check
        def on_booking_cutoff_check(event: SimEvent, state: WorldState) -> None:
            next_at = self._kernel.current_simpy_time + 24.0
            self._kernel.schedule(
                SimEvent(
                    event_type=EventType.BOOKING_LOCKED,
                    entity_type="booking",
                    entity_id="system",
                    simulation_time=event.simulation_time + timedelta(hours=24.0),
                    source="allocation_model",
                    world_id=state.world_id,
                ),
                at_simpy_time=next_at,
            )

        # Disruption activation
        def on_disruption_activated(event: SimEvent, state: WorldState) -> None:
            consequences = self._disruption_engine.handle_disruption_activated(event, state)
            for c_event in consequences:
                self._kernel.schedule_now(c_event, state)

            duration = float(event.payload.get("duration_hours", 24.0))
            dis_id = event.payload.get("disruption_id", event.entity_id)
            end_simpy_time = self._kernel.current_simpy_time + duration
            end_event = SimEvent(
                event_type=EventType.DISRUPTION_ENDED,
                entity_type="disruption",
                entity_id=dis_id,
                simulation_time=event.simulation_time + timedelta(hours=duration),
                source="disruption_engine",
                world_id=state.world_id,
                payload={"disruption_id": dis_id},
            )
            self._kernel.schedule(end_event, at_simpy_time=end_simpy_time)

        # Disruption ended
        def on_disruption_ended(event: SimEvent, state: WorldState) -> None:
            dis_id = event.payload.get("disruption_id", event.entity_id)
            _, recoveries = self._disruption_engine.handle_disruption_ended(
                dis_id, event.simulation_time, state
            )
            for r_event in recoveries:
                self._kernel.schedule_now(r_event, state)

        # Mechanical failure
        def on_mechanical_failure(event: SimEvent, state: WorldState) -> None:
            vessel = state.get_vessel(event.entity_id)
            self._vessel_model.apply_mechanical_failure(vessel, event.simulation_time)
            rec_dt, rec_hours = self._recovery_model.schedule_vessel_recovery(
                vessel, event.simulation_time
            )
            rec_event = SimEvent(
                event_type=EventType.VESSEL_RECOVERED,
                entity_type="vessel",
                entity_id=vessel.vessel_id,
                simulation_time=rec_dt,
                source="recovery_model",
                world_id=state.world_id,
            )
            self._kernel.schedule(
                rec_event, at_simpy_time=self._kernel.current_simpy_time + rec_hours
            )

        # Mechanical recovery
        def on_vessel_recovered(event: SimEvent, state: WorldState) -> None:
            vessel = state.get_vessel(event.entity_id)
            self._recovery_model.execute_vessel_recovery(
                vessel, event.simulation_time, state
            )

        self._kernel.register_handler(EventType.VESSEL_ARRIVED, on_vessel_arrived)
        self._kernel.register_handler(EventType.VESSEL_UNBERTHED, on_vessel_unberth)
        self._kernel.register_handler(EventType.BERTH_RELEASED, on_berth_released)
        self._kernel.register_handler(EventType.DEMAND_GENERATED, on_demand_generated)
        self._kernel.register_handler(EventType.BOOKING_LOCKED, on_booking_cutoff_check)
        self._kernel.register_handler(EventType.DISRUPTION_ACTIVATED, on_disruption_activated)
        self._kernel.register_handler(EventType.DISRUPTION_ENDED, on_disruption_ended)
        self._kernel.register_handler(EventType.VESSEL_MECHANICAL_FAILURE, on_mechanical_failure)
        self._kernel.register_handler(EventType.VESSEL_RECOVERED, on_vessel_recovered)

    # ------------------------------------------------------------------
    # Baseline Management
    # ------------------------------------------------------------------

    async def ensure_world_baseline(
        self,
        world_id: str = "world-2",
        seeder_version: str = "v1",
        baseline_time: Optional[datetime] = None,
        force_reseed: bool = False,
    ) -> Dict[str, Any]:
        """
        Ensure an immutable baseline exists for (world_id, seeder_version).
        If force_reseed=True, creates a new version timestamped so previous baselines are preserved.
        """
        sim_start = baseline_time or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        seeder = WorldSeeder(self._base_reg)

        # 1. Check DB first if not forcing reseed
        if not force_reseed and self._session_factory:
            try:
                async with self._session_factory() as session:
                    stmt = (
                        select(WorldBaseline)
                        .where(WorldBaseline.world_id == world_id)
                        .where(WorldBaseline.seeder_version == seeder_version)
                        .order_by(desc(WorldBaseline.created_at))
                        .limit(1)
                    )
                    res = await session.execute(stmt)
                    row = res.scalar_one_or_none()
                    if row:
                        return {
                            "baseline_id": str(row.id),
                            "world_id": row.world_id,
                            "seeder_version": row.seeder_version,
                            "world_seed": row.world_seed,
                            "entity_counts": row.entity_counts,
                            "created": False,
                        }
            except Exception as ex:
                logger.warning("Error checking world_baselines DB table: %s", ex)

        # Check memory cache if not force_reseed
        cache_key = (world_id, seeder_version)
        if not force_reseed and cache_key in self._baselines_cache:
            data, b_id = self._baselines_cache[cache_key]
            return {
                "baseline_id": str(b_id),
                "world_id": world_id,
                "seeder_version": seeder_version,
                "created": False,
            }

        # Build new immutable baseline
        actual_version = seeder_version
        if force_reseed:
            actual_version = f"{seeder_version}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        base_state = seeder.build_baseline(
            world_id=world_id,
            seeder_version=actual_version,
            baseline_time=sim_start,
        )
        baseline_id = uuid.uuid4()
        world_seed = stable_world_seed(world_id, actual_version)
        serialized = seeder.serialize_baseline(base_state)
        entity_counts = {
            "ports": len(base_state.ports),
            "vessels": len(base_state.vessels),
            "voyages": len(base_state.voyages),
            "containers": len(base_state.containers),
            "bookings": len(base_state.bookings),
            "allocations": len(base_state.allocations),
            "equipment": len(base_state.equipment),
        }

        # Save to PostgreSQL
        if self._session_factory:
            try:
                async with self._session_factory() as session:
                    db_baseline = WorldBaseline(
                        id=baseline_id,
                        world_id=world_id,
                        seeder_version=actual_version,
                        world_seed=world_seed,
                        baseline_time=sim_start,
                        entity_counts=entity_counts,
                        baseline_json=serialized,
                    )
                    session.add(db_baseline)
                    await session.commit()
            except Exception as ex:
                logger.warning("Could not persist WorldBaseline to DB (caching in memory): %s", ex)

        # Cache in memory
        self._baselines_cache[(world_id, actual_version)] = (serialized, baseline_id)
        if not force_reseed:
            self._baselines_cache[cache_key] = (serialized, baseline_id)

        return {
            "baseline_id": str(baseline_id),
            "world_id": world_id,
            "seeder_version": actual_version,
            "world_seed": world_seed,
            "entity_counts": entity_counts,
            "created": True,
        }

    async def _load_baseline(
        self, world_id: str, baseline_id: Optional[str] = None
    ) -> Tuple[WorldState, UUID]:
        """Load and deserialize from world_baselines table or memory cache."""
        seeder = WorldSeeder(self._base_reg)

        if self._session_factory:
            try:
                async with self._session_factory() as session:
                    if baseline_id:
                        stmt = select(WorldBaseline).where(WorldBaseline.id == uuid.UUID(baseline_id))
                    else:
                        stmt = (
                            select(WorldBaseline)
                            .where(WorldBaseline.world_id == world_id)
                            .order_by(desc(WorldBaseline.created_at))
                            .limit(1)
                        )
                    res = await session.execute(stmt)
                    row = res.scalar_one_or_none()
                    if row:
                        state = seeder.deserialize_baseline(row.baseline_json, baseline_id=row.id)
                        return state, row.id
            except Exception as ex:
                logger.warning("Could not load WorldBaseline from DB: %s", ex)

        # Check memory cache
        if baseline_id:
            for (w_id, v), (data, b_id) in self._baselines_cache.items():
                if str(b_id) == baseline_id:
                    state = seeder.deserialize_baseline(data, baseline_id=b_id)
                    return state, b_id

        for (w_id, v), (data, b_id) in self._baselines_cache.items():
            if w_id == world_id:
                state = seeder.deserialize_baseline(data, baseline_id=b_id)
                return state, b_id

        # Fallback: create baseline on the fly
        res = await self.ensure_world_baseline(world_id=world_id)
        b_uuid = uuid.UUID(res["baseline_id"])
        data, _ = self._baselines_cache[(world_id, res["seeder_version"])]
        state = seeder.deserialize_baseline(data, baseline_id=b_uuid)
        return state, b_uuid

    def _clone_baseline(
        self,
        baseline: WorldState,
        baseline_id: UUID,
        run_id: UUID,
    ) -> WorldState:
        """Deep copy of WorldState with new run_id and tagged world_baseline_id."""
        cloned = copy.deepcopy(baseline)
        cloned.run_id = run_id
        cloned.world_baseline_id = str(baseline_id)
        return cloned

    def _init_event_queue(self, state: WorldState, sim_start: datetime) -> None:
        """Populate discrete event queue from WorldState operational snapshot."""
        # 1. Vessels
        for vessel in state.vessels.values():
            if vessel.status == "IN_TRANSIT" and vessel.current_voyage_id:
                voyage = state.voyages.get(vessel.current_voyage_id)
                if voyage and voyage.estimated_arrival:
                    hours_until = (voyage.estimated_arrival - sim_start).total_seconds() / 3600.0
                    if hours_until >= 0:
                        self._kernel.schedule(
                            SimEvent(
                                event_type=EventType.VESSEL_ARRIVED,
                                entity_type="vessel",
                                entity_id=vessel.vessel_id,
                                simulation_time=voyage.estimated_arrival,
                                source="vessel_model",
                                world_id=state.world_id,
                                payload={"port_id": voyage.destination_port_id, "voyage_id": voyage.voyage_id},
                            ),
                            at_simpy_time=hours_until,
                        )

            elif vessel.status == "IN_PORT" and vessel.current_voyage_id:
                voyage = state.voyages.get(vessel.current_voyage_id)
                turnaround = voyage.remaining_turnaround_hours if (voyage and voyage.remaining_turnaround_hours > 0) else 12.0
                unberth_time = sim_start + timedelta(hours=turnaround)
                self._kernel.schedule(
                    SimEvent(
                        event_type=EventType.VESSEL_UNBERTHED,
                        entity_type="vessel",
                        entity_id=vessel.vessel_id,
                        simulation_time=unberth_time,
                        source="vessel_model",
                        world_id=state.world_id,
                        payload={"port_id": vessel.current_port_id, "voyage_id": vessel.current_voyage_id},
                    ),
                    at_simpy_time=turnaround,
                )

            elif vessel.status == "SCHEDULED" and vessel.current_voyage_id:
                voyage = state.voyages.get(vessel.current_voyage_id)
                if voyage and voyage.scheduled_departure:
                    hours_until = (voyage.scheduled_departure - sim_start).total_seconds() / 3600.0
                    if hours_until >= 0:
                        self._kernel.schedule(
                            SimEvent(
                                event_type=EventType.VESSEL_DEPARTED,
                                entity_type="vessel",
                                entity_id=vessel.vessel_id,
                                simulation_time=voyage.scheduled_departure,
                                source="vessel_model",
                                world_id=state.world_id,
                                payload={"port_id": voyage.origin_port_id, "voyage_id": voyage.voyage_id},
                            ),
                            at_simpy_time=hours_until,
                        )

        # 2. Port Occupancy / Resource Event: KRPUS berth freed at T+14h (resolving V006 WAITING_FOR_BERTH)
        self._kernel.schedule(
            SimEvent(
                event_type=EventType.BERTH_RELEASED,
                entity_type="port",
                entity_id="KRPUS",
                simulation_time=sim_start + timedelta(hours=14.0),
                source="port_model",
                world_id=state.world_id,
                payload={"port_id": "KRPUS"},
            ),
            at_simpy_time=14.0,
        )

        # 3. Recurring Events
        self._kernel.schedule(
            SimEvent(
                event_type=EventType.DEMAND_GENERATED,
                entity_type="demand",
                entity_id="system",
                simulation_time=sim_start + timedelta(hours=12.0),
                source="demand_model",
                world_id=state.world_id,
            ),
            at_simpy_time=12.0,
        )
        self._kernel.schedule(
            SimEvent(
                event_type=EventType.BOOKING_LOCKED,
                entity_type="booking",
                entity_id="system",
                simulation_time=sim_start + timedelta(hours=24.0),
                source="allocation_model",
                world_id=state.world_id,
            ),
            at_simpy_time=24.0,
        )

    # ------------------------------------------------------------------
    # Control API Methods
    # ------------------------------------------------------------------

    async def start(
        self,
        scenario_id: str = "normal",
        seed: int = 42,
        start_time: Optional[datetime] = None,
        world_id: str = "world-2",
        baseline_id: Optional[str] = None,
    ) -> WorldState:
        """Start or initialize a simulation run from an immutable baseline."""
        async with self._lock:
            self._scenario_id = scenario_id
            self._seed = seed
            self._rng = random.Random(seed)

            sim_start = start_time or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
            run_id = uuid.uuid4()

            # 1. Reset clock and kernel
            self._kernel.reset(sim_start)

            # 2. Scenario configuration isolation (global defaults never mutated)
            scenario = get_scenario(scenario_id)
            overrides = scenario.parameter_overrides if scenario else {}
            self._reg, resolved_params, config_hash = self._base_reg.resolve_for_run(overrides)
            self._init_domain_models(self._reg, self._rng)

            # 3. Ensure baseline exists & load it
            await self.ensure_world_baseline(world_id=world_id, baseline_time=sim_start)
            base_state, actual_baseline_id = await self._load_baseline(world_id, baseline_id)

            # 4. Clone baseline for this run
            state = self._clone_baseline(base_state, actual_baseline_id, run_id)
            state.simulation_time = sim_start

            # 5. Schedule disruptions from scenario
            if scenario and scenario.disruptions:
                for d in scenario.disruptions:
                    dis_event = SimEvent(
                        event_type=EventType.DISRUPTION_ACTIVATED,
                        entity_type="disruption",
                        entity_id=f"DIS-{scenario_id}-{d.disruption_type.value}",
                        simulation_time=sim_start + timedelta(hours=d.start_offset_hours),
                        source="scenario_config",
                        world_id=world_id,
                        payload={
                            "disruption_type": d.disruption_type.value,
                            "severity": d.severity,
                            "duration_hours": d.duration_hours,
                            "affected_entity_ids": d.affected_entity_ids,
                            "parameter_overrides": getattr(d, "parameter_overrides", {}),
                        },
                    )
                    self._kernel.schedule(dis_event, at_simpy_time=d.start_offset_hours)

            # 6. Init discrete event queue from operational snapshot
            self._init_event_queue(state, sim_start)

            # 7. Persist run to DB if session factory is available
            if self._session_factory:
                try:
                    async with self._session_factory() as session:
                        seeder = WorldSeeder(self._reg)
                        await seeder.persist_run(
                            session=session,
                            run_id=run_id,
                            world_id=world_id,
                            scenario_id=scenario_id,
                            random_seed=seed,
                            start_time=sim_start,
                            config_hash=config_hash,
                            baseline_id=actual_baseline_id,
                        )
                        await session.flush()
                        await seeder.persist_vessel_states(session, run_id, state)
                        await seeder.persist_port_states(session, run_id, state)
                        await session.commit()
                except Exception as ex:
                    logger.warning("Could not persist initial run to DB: %s", ex)

            self._state = state
            self._status = SimulationStatus.RUNNING
            logger.info("Simulation run %s started (scenario=%s, baseline=%s)", run_id, scenario_id, actual_baseline_id)
            return self._state

    async def advance(self, delta_hours: float) -> Tuple[WorldState, List[SimEvent]]:
        """
        Advance the simulation clock by delta_hours.
        Doc 2 §2.2: 0 < delta_hours ≤ 24h
        """
        async with self._lock:
            if not self._state or self._status != SimulationStatus.RUNNING:
                raise RuntimeError("Simulation is not running. Call start() first.")

            # Update progress of all in-transit vessels
            for v in self._state.vessels.values():
                if v.status == "IN_TRANSIT" and v.current_voyage_id:
                    voyage = self._state.voyages.get(v.current_voyage_id)
                    if voyage:
                        self._vessel_model.update_vessel_progress(v, voyage, delta_hours)

            # Advance kernel discrete event queue
            updated_state, events = self._kernel.advance(self._state, delta_hours)

            # Check 7-day cutoff locks (Doc 2 §9.4)
            lock_events = self._allocation_model.evaluate_booking_locks(
                self._state, self._clock.now
            )
            events.extend(lock_events)

            # Publish updated vessel positions (Doc 2 §17)
            pos_events = self._visibility_model.publish_vessel_positions(
                self._clock.now, self._state
            )
            events.extend(pos_events)

            return updated_state, events

    async def pause(self) -> None:
        async with self._lock:
            self._status = SimulationStatus.PAUSED
            logger.info("Simulation paused")

    async def resume(self) -> None:
        async with self._lock:
            self._status = SimulationStatus.RUNNING
            logger.info("Simulation resumed")

    async def reset(self) -> None:
        async with self._lock:
            self._status = SimulationStatus.IDLE
            self._state = None
            logger.info("Simulation reset")

    async def inject_disruption(
        self,
        disruption_type: str,
        severity: float,
        duration_hours: float,
        affected_entity_ids: Optional[List[str]] = None,
        parameter_overrides: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Inject an operational disruption.
        Rule 4: Schedules DISRUPTION_ACTIVATED event on kernel; no direct state mutation.
        """
        async with self._lock:
            if not self._state:
                raise RuntimeError("Cannot inject disruption: no active simulation run")

            event, dis_id = self._disruption_engine.build_injection_event(
                disruption_type=disruption_type,
                severity=severity,
                duration_hours=duration_hours,
                sim_time=self._clock.now,
                affected_entity_ids=affected_entity_ids,
                parameter_overrides=parameter_overrides,
                world_id=self._state.world_id,
            )
            self._kernel.schedule_now(event, self._state)
            return dis_id

    def get_status(self) -> Dict[str, Any]:
        return {
            "status": self._status,
            "scenario_id": self._scenario_id,
            "simulation_time": self._clock.now.isoformat() if self._clock else None,
            "simpy_time_hours": self._kernel.current_simpy_time if self._kernel else 0.0,
            "run_id": str(self._state.run_id) if self._state else None,
            "world_baseline_id": self._state.world_baseline_id if self._state else None,
            "pending_events": self._kernel.pending_event_count if self._kernel else 0,
        }

    @property
    def state(self) -> Optional[WorldState]:
        return self._state
