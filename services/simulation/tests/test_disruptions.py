"""
Unit tests for Disruptions (Doc 2 §14), Failure (Doc 2 §19), and Recovery (Doc 2 §20).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.disruption_types import DisruptionStatus, DisruptionType
from app.config.parameters import ParameterRegistry
from app.models.disruption_engine import DisruptionEngine
from app.models.failure_model import FailureModel, draw_time_to_failure_hours
from app.models.port_model import PortModel
from app.models.recovery_model import RecoveryModel, calculate_recovery_timestamp
from app.models.vessel_model import VesselModel
from app.world.world_state import PortState, VesselState, VoyageState, WorldState


def test_draw_time_to_failure():
    """Doc 2 §19.3: Time-to-failure draw."""
    mtbf = 720.0  # hours
    assert draw_time_to_failure_hours(mtbf, deterministic=True) == 720.0


def test_storm_disruption_cascade_and_persistence():
    """
    Doc 2 §14.3, §14.4:
    Storm causes speed reduction and ETA update.
    When storm ends, the storm is inactive but the delay persists!
    """
    registry = ParameterRegistry()
    port_model = PortModel(registry)
    vessel_model = VesselModel(registry, port_model)
    engine = DisruptionEngine(registry, vessel_model=vessel_model, port_model=port_model)

    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=start_time, world_id="world-2")

    # Setup vessel and active voyage
    vessel = VesselState(
        vessel_id="V001",
        status="IN_TRANSIT",
        current_voyage_id="VY001",
        current_speed_knots=20.0,
        distance_remaining_nm=1000.0,
        position_fraction=0.0,
    )
    state.vessels["V001"] = vessel

    voyage = VoyageState(
        voyage_id="VY001",
        vessel_id="V001",
        origin_port_id="SGSIN",
        destination_port_id="CNSHA",
        scheduled_departure=start_time,
        scheduled_arrival=start_time + timedelta(hours=50),
        route_distance_nm=1000.0,
    )
    state.voyages["VY001"] = voyage

    # 1. Inject storm event
    inj_event, dis_id = engine.build_injection_event(
        disruption_type=DisruptionType.STORM.value,
        severity=0.8,  # severe storm
        duration_hours=24.0,
        sim_time=start_time,
        affected_entity_ids=["V001"],
    )
    assert inj_event.event_type == "DISRUPTION_ACTIVATED"

    # 2. Activate storm -> Cascades into speed reduction & ETA change
    cascade_events = engine.handle_disruption_activated(inj_event, state)
    assert len(cascade_events) == 1
    assert cascade_events[0].event_type == "VESSEL_ETA_UPDATED"

    # Effective speed was 20 * (1 - 0.5 * 0.8) = 20 * 0.6 = 12 knots
    assert pytest.approx(vessel.current_speed_knots, rel=1e-3) == 12.0
    # Remaining travel time = 1000 / 12 = 83.33 hours -> ETA delayed!
    expected_eta = start_time + timedelta(hours=1000.0 / 12.0)
    assert vessel.eta == expected_eta

    # 3. Storm ends after 24 hours (Doc 2 §14.3: Persistent Consequences)
    storm_end_time = start_time + timedelta(hours=24)
    end_event, _ = engine.handle_disruption_ended(dis_id, storm_end_time, state)
    assert end_event.event_type == "DISRUPTION_ENDED"
    disruption = state.disruptions[0]
    assert disruption.status == DisruptionStatus.ENDED.value
    # The vessel's delayed ETA remains delayed!
    assert vessel.eta == expected_eta


def test_port_strike_disruption():
    """Doc 2 §14.5: Port strike reduces capacity, then ends and restores capacity."""
    registry = ParameterRegistry()
    port_model = PortModel(registry)
    engine = DisruptionEngine(registry, port_model=port_model)

    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=start_time, world_id="world-2")

    port = PortState(port_id="FRLEH", unlocode="FRLEH", berths_total=10, berths_occupied=0)
    state.ports["FRLEH"] = port

    # 1. Inject strike with severity 0.6 -> capacity factor 0.4 (4 berths usable)
    inj_event, dis_id = engine.build_injection_event(
        disruption_type=DisruptionType.PORT_STRIKE.value,
        severity=0.6,
        duration_hours=48.0,
        sim_time=start_time,
        affected_entity_ids=["FRLEH"],
    )
    engine.handle_disruption_activated(inj_event, state)
    assert port.is_strike_active is True
    assert port.strike_capacity_factor == pytest.approx(0.4, rel=1e-3)
    assert port_model.get_berths_available(port) == 4

    # 2. Strike ends after 48h -> Restores capacity
    end_time = start_time + timedelta(hours=48)
    engine.handle_disruption_ended(dis_id, end_time, state)
    assert port.is_strike_active is False
    assert port_model.get_berths_available(port) == 10


def test_failure_and_recovery_cycle():
    """Doc 2 §19, §20: Mechanical failure and recovery."""
    registry = ParameterRegistry()
    registry.set("VESSEL_RECOVERY_TIME_HOURS", 48.0)
    port_model = PortModel(registry)
    vessel_model = VesselModel(registry, port_model)

    fail_model = FailureModel(registry)
    rec_model = RecoveryModel(registry, vessel_model=vessel_model)

    sim_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    vessel = VesselState(vessel_id="V002", status="IN_TRANSIT", current_speed_knots=18.0)
    state.vessels["V002"] = vessel

    # 1. Failure triggers
    fail_event = fail_model.trigger_vessel_failure(vessel, sim_time, state)
    assert vessel.condition == "DAMAGED"
    assert vessel.current_speed_knots == 0.0

    # 2. Schedule recovery
    rec_time, rec_hours = rec_model.schedule_vessel_recovery(vessel, sim_time)
    assert rec_hours == 48.0
    assert rec_time == sim_time + timedelta(hours=48)

    # 3. Execute recovery at rec_time
    rec_event, _ = rec_model.execute_vessel_recovery(vessel, rec_time, state)
    assert vessel.condition == "GOOD"
    assert vessel.current_speed_knots == 18.0
    assert rec_event.event_type == "VESSEL_RECOVERED"
