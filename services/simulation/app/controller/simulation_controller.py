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
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.clock.simulation_clock import SimulationClock
from app.config.disruption_types import DisruptionType
from app.config.parameters import ParameterRegistry
from app.config.scenario_configs import get_scenario
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
from app.world.world_seeder import WorldSeeder, compute_travel_time_hours
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
        self._reg = registry
        self._bus = event_bus
        self._kernel = kernel
        self._session_factory = session_factory

        self._lock = asyncio.Lock()
        self._status = SimulationStatus.IDLE
        self._state: Optional[WorldState] = None
        self._scenario_id: str = "normal"
        self._seed: int = 42
        self._rng = random.Random(42)

        # Instantiate domain models
        self._port_model = PortModel(self._reg)
        self._vessel_model = VesselModel(self._reg, self._port_model)
        self._container_model = ContainerModel(self._reg, self._rng)
        self._demand_model = DemandModel(self._reg, self._rng)
        self._booking_model = BookingModel(self._reg, self._rng)
        self._allocation_model = AllocationModel(self._reg)
        self._import_return_model = ImportReturnModel(self._reg, self._rng)
        self._equipment_model = EquipmentModel(self._reg)
        self._leasing_model = LeasingModel(self._reg)
        self._repositioning_model = RepositioningModel(self._reg)
        self._disruption_engine = DisruptionEngine(
            self._reg, vessel_model=self._vessel_model, port_model=self._port_model
        )
        self._failure_model = FailureModel(self._reg, self._rng)
        self._recovery_model = RecoveryModel(self._reg, vessel_model=self._vessel_model)
        self._forecasting_model = ForecastingModel(self._reg, self._rng)
        self._visibility_model = VisibilityModel(self._reg)
        self._timeline_model = TimelineModel(self._reg)
        self._backlog_model = BacklogModel(self._reg)
        self._cost_model = CostModel(self._reg)

        # Register validators on kernel
        self._kernel.register_local_validator(validate_local_event)
        self._kernel.register_advancement_validator(validate_advancement_state)

        # Register event handlers on kernel
        self._register_event_handlers()

        logger.info("SimulationController initialized")

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
                # Schedule unberthing at event.simulation_time + turnaround
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
                # Queued vessel now berths!
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

        # Disruption activation
        def on_disruption_activated(event: SimEvent, state: WorldState) -> None:
            consequences = self._disruption_engine.handle_disruption_activated(event, state)
            for c_event in consequences:
                self._kernel.schedule_now(c_event, state)

            # Schedule DISRUPTION_ENDED event
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
            # Schedule recovery
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
        self._kernel.register_handler(EventType.DISRUPTION_ACTIVATED, on_disruption_activated)
        self._kernel.register_handler(EventType.DISRUPTION_ENDED, on_disruption_ended)
        self._kernel.register_handler(EventType.VESSEL_MECHANICAL_FAILURE, on_mechanical_failure)
        self._kernel.register_handler(EventType.VESSEL_RECOVERED, on_vessel_recovered)

    # ------------------------------------------------------------------
    # Control API Methods
    # ------------------------------------------------------------------

    async def start(
        self,
        scenario_id: str = "normal",
        seed: int = 42,
        start_time: Optional[datetime] = None,
        world_id: str = "world-2",
    ) -> WorldState:
        """Start or initialize a simulation run."""
        async with self._lock:
            self._scenario_id = scenario_id
            self._seed = seed
            self._rng = random.Random(seed)

            sim_start = start_time or datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
            run_id = uuid.uuid4()

            # Reset clock and kernel
            self._kernel.reset(sim_start)

            # Apply scenario parameter overrides
            scenario = get_scenario(scenario_id)
            if scenario:
                self._reg.apply_scenario_overrides(scenario.parameter_overrides)

            # Build initial WorldState via Seeder
            seeder = WorldSeeder(self._reg)
            self._state = seeder.build_world_state(
                run_id=run_id,
                world_id=world_id,
                start_time=sim_start,
            )

            self._status = SimulationStatus.RUNNING
            logger.info("Simulation run %s started (scenario=%s)", run_id, scenario_id)
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
            "pending_events": self._kernel.pending_event_count if self._kernel else 0,
        }

    @property
    def state(self) -> Optional[WorldState]:
        return self._state
