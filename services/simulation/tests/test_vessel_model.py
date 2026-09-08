"""
Unit tests for Vessel & Voyage Model (Doc 2 §4).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.port_model import PortModel
from app.models.vessel_model import (
    VesselModel,
    calculate_effective_speed,
    calculate_travel_time,
    calculate_remaining_travel_time,
    calculate_position_continuity,
    calculate_weather_factor,
    calculate_schedule_variance,
)
from app.world.world_state import PortState, VesselState, VoyageState, WorldState


def test_effective_speed_and_travel_time():
    """Doc 2 §4.4: T_travel = D / V_eff, V_eff = V_base * F_weather * F_operational."""
    v_base = 20.0
    f_weather = 1.0
    f_operational = 1.0
    v_eff = calculate_effective_speed(v_base, f_weather, f_operational)
    assert v_eff == 20.0

    distance = 1000.0  # NM
    t_travel = calculate_travel_time(distance, v_eff)
    assert t_travel == 50.0  # hours


def test_weather_factor_reduction():
    """Doc 2 §4.6, §14.4: F_weather = 1 - alpha_s * s."""
    # Calm weather (severity = 0)
    assert calculate_weather_factor(base_weather_factor=1.0, storm_severity=0.0, alpha_s=0.5) == 1.0

    # Moderate storm (severity = 0.6)
    # F_w = 1.0 * (1 - 0.5 * 0.6) = 0.70
    assert pytest.approx(calculate_weather_factor(1.0, 0.6, 0.5), rel=1e-3) == 0.70

    # Severe storm (severity = 1.0)
    # F_w = 1.0 * (1 - 0.5 * 1.0) = 0.50
    assert pytest.approx(calculate_weather_factor(1.0, 1.0, 0.5), rel=1e-3) == 0.50


def test_position_continuity_and_storm_cascade():
    """
    Doc 2 §4.5: Position continuity.
    When a storm hits midway, calculations MUST use current position (D_remaining),
    not restart from origin!
    """
    total_distance = 2000.0  # NM
    v_base = 20.0  # knots
    initial_travel_time = calculate_travel_time(total_distance, v_base)  # 100 hours

    # Vessel travels 800 NM (40 hours at 20 knots)
    distance_travelled = 800.0
    fraction, d_remaining = calculate_position_continuity(total_distance, distance_travelled)
    assert fraction == 0.40
    assert d_remaining == 1200.0

    # Storm hits at this moment (severity = 0.8)
    f_weather = calculate_weather_factor(1.0, storm_severity=0.8, alpha_s=0.5)
    # F_weather = 1.0 - 0.5 * 0.8 = 0.60
    assert pytest.approx(f_weather, rel=1e-3) == 0.60
    v_eff = calculate_effective_speed(v_base, f_weather)
    assert pytest.approx(v_eff, rel=1e-3) == 12.0  # knots

    # Remaining time must be D_remaining / V_eff = 1200 / 12 = 100 hours
    t_remaining = calculate_remaining_travel_time(d_remaining, v_eff)
    assert pytest.approx(t_remaining, rel=1e-3) == 100.0

    # Total trip duration = 40 (past) + 100 (remaining) = 140 hours (delayed by 40 hours)
    total_time = 40.0 + t_remaining
    assert pytest.approx(total_time, rel=1e-3) == 140.0


def test_schedule_variance():
    """Doc 2 §4.8: ScheduleVariance = ActualTime - ScheduledTime."""
    scheduled = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    
    # 4 hours late
    actual_delayed = scheduled + timedelta(hours=4)
    assert calculate_schedule_variance(actual_delayed, scheduled) == 4.0

    # 2 hours early
    actual_early = scheduled - timedelta(hours=2)
    assert calculate_schedule_variance(actual_early, scheduled) == -2.0


def test_vessel_voyage_lifecycle_with_port_berth():
    """Test vessel departure, arrival, and berthing flow."""
    registry = ParameterRegistry()
    port_model = PortModel(registry)
    vessel_model = VesselModel(registry, port_model)

    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=start_time, world_id="world-2")

    # Setup port with 1 berth
    port = PortState(port_id="CNSHA", unlocode="CNSHA", berths_total=1, berths_occupied=0)
    state.ports["CNSHA"] = port

    # Setup vessel and voyage
    vessel = VesselState(vessel_id="V001", status="AVAILABLE", current_speed_knots=20.0)
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

    # 1. Depart
    dep_event, travel_time = vessel_model.start_voyage(vessel, voyage, start_time)
    assert vessel.status == "IN_TRANSIT"
    assert travel_time == 50.0
    assert vessel.eta == start_time + timedelta(hours=50)

    # 2. Arrive when berth is available
    arrival_time = start_time + timedelta(hours=50)
    arr_event, turnaround = vessel_model.arrive_vessel(vessel, voyage, port, arrival_time, state)
    assert vessel.status == "IN_PORT"
    assert port.berths_occupied == 1
    assert turnaround is not None
    assert turnaround > 0

    # 3. Complete stay (unberth)
    dep_time = arrival_time + timedelta(hours=turnaround)
    unberth_event, next_vessel = vessel_model.complete_port_stay(vessel, port, dep_time, state)
    assert vessel.status == "AVAILABLE"
    assert port.berths_occupied == 0
    assert next_vessel is None


def test_vessel_queueing_when_no_berth():
    """Test that second vessel arriving at full port queues and waits."""
    registry = ParameterRegistry()
    port_model = PortModel(registry)
    vessel_model = VesselModel(registry, port_model)

    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=start_time, world_id="world-2")

    # Port with only 1 berth
    port = PortState(port_id="CNSHA", unlocode="CNSHA", berths_total=1, berths_occupied=0)
    state.ports["CNSHA"] = port

    # Vessel 1 is already in port
    v1 = VesselState(vessel_id="V001", status="AVAILABLE")
    state.vessels["V001"] = v1
    vy1 = VoyageState(
        voyage_id="VY001", vessel_id="V001", origin_port_id="SGSIN",
        destination_port_id="CNSHA", scheduled_departure=start_time,
        scheduled_arrival=start_time, route_distance_nm=100,
    )
    vessel_model.arrive_vessel(v1, vy1, port, start_time, state)
    assert port.berths_occupied == 1
    assert v1.status == "IN_PORT"

    # Vessel 2 arrives -> must queue
    v2 = VesselState(vessel_id="V002", status="AVAILABLE")
    state.vessels["V002"] = v2
    vy2 = VoyageState(
        voyage_id="VY002", vessel_id="V002", origin_port_id="SGSIN",
        destination_port_id="CNSHA", scheduled_departure=start_time,
        scheduled_arrival=start_time, route_distance_nm=100,
    )
    arr_event2, turnaround2 = vessel_model.arrive_vessel(v2, vy2, port, start_time, state)
    assert v2.status == "WAITING_FOR_BERTH"
    assert turnaround2 is None
    assert port.vessel_queue == ["V002"]

    # When Vessel 1 unberths, berth goes to Vessel 2!
    unberth_ev, next_v = vessel_model.complete_port_stay(v1, port, start_time + timedelta(hours=12), state)
    assert next_v == "V002"
    assert port.berths_occupied == 1
    assert len(port.vessel_queue) == 0


def test_mechanical_failure_and_recovery():
    """Doc 2 §19, §20: Mechanical failure stops speed, recovery restores it."""
    registry = ParameterRegistry()
    port_model = PortModel(registry)
    vessel_model = VesselModel(registry, port_model)

    sim_time = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    vessel = VesselState(vessel_id="V001", status="IN_TRANSIT", current_speed_knots=18.0)

    # Trigger failure
    fail_event = vessel_model.apply_mechanical_failure(vessel, sim_time)
    assert vessel.condition == "DAMAGED"
    assert vessel.current_speed_knots == 0.0

    # Recover
    rec_time = sim_time + timedelta(hours=48)
    rec_event = vessel_model.apply_recovery(vessel, rec_time)
    assert vessel.condition == "GOOD"
    assert vessel.current_speed_knots == 18.0
