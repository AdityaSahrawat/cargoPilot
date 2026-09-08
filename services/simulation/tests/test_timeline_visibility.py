"""
Unit tests for Forecasting (Doc 2 §16), Visibility (Doc 2 §17), and Timeline (Doc 2 §18).
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.forecasting_model import ForecastingModel, calculate_forecast_value
from app.models.visibility_model import (
    VisibilityModel,
    calculate_observation_time,
    calculate_ingestion_time,
)
from app.models.timeline_model import TimelineModel, calculate_milestone_time
from app.world.world_state import VesselState, VoyageState, Visibility, WorldState


def test_calculate_forecast_value():
    """Doc 2 §16.3: D̂_{t+k} = Base * Trend * Seasonality + Noise."""
    val = calculate_forecast_value(
        base_forecast=10.0,
        trend_factor=1.0,
        seasonal_factor=1.0,
        noise_sigma=0.0,
        deterministic=True,
    )
    assert val == 10.0


def test_forecasting_from_history():
    """Test forecasting from historical observations without leakage."""
    registry = ParameterRegistry()
    model = ForecastingModel(registry)

    sim_time = datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    # Populate 5 days of history: 8, 9, 10, 11, 12 -> mean = 10.0
    for day in range(5):
        state.demand.historical_demand[("CNSHA", "USLAX", "40HC", day)] = 8.0 + day

    forecast, event = model.generate_demand_forecast(
        origin_port_id="CNSHA",
        destination_port_id="USLAX",
        equipment_type="40HC",
        horizon_days=7,
        sim_time=sim_time,
        state=state,
        deterministic=True,
    )
    assert len(forecast) == 7
    # Mean of history is 10.0 -> each day forecast should be 10.0
    for day_str, val in forecast.items():
        assert val == 10.0
    assert event.event_type == "FORECAST_UPDATED"


def test_three_timestamp_pipeline():
    """Doc 2 §17.2, §17.3: Occurrence → Observation → Ingestion."""
    t_occ = datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc)
    t_obs = calculate_observation_time(t_occ, info_delay_hours=0.5)
    t_ing = calculate_ingestion_time(t_obs, ingestion_delay_hours=0.1)

    assert t_obs == datetime(2026, 9, 1, 10, 30, tzinfo=timezone.utc)
    assert t_ing == datetime(2026, 9, 1, 10, 36, tzinfo=timezone.utc)


def test_visibility_gating_and_position_publishing():
    """Doc 2 §17.2: Publishing promotes visibility to KNOWN_TO_CARGOPILOT."""
    registry = ParameterRegistry()
    model = VisibilityModel(registry)

    sim_time = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=sim_time, world_id="world-2")

    vessel = VesselState(
        vessel_id="V001",
        status="IN_TRANSIT",
        eta_visibility=Visibility.INTERNAL_SIMULATION_KNOWN,
        current_speed_knots=20.0,
    )
    state.vessels["V001"] = vessel

    events = model.publish_vessel_positions(sim_time, state)
    assert len(events) == 1
    assert events[0].event_type == "VESSEL_POSITION_PUBLISHED"
    assert vessel.eta_visibility == Visibility.KNOWN_TO_CARGOPILOT


def test_operational_timeline_milestones_and_dynamic_shift():
    """
    Doc 2 §18.2, §18.4, §18.5:
    Milestones derived from departure time.
    When departure changes, future unlocked milestones shift accordingly.
    """
    registry = ParameterRegistry()
    model = TimelineModel(registry)

    sim_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    departure = sim_time + timedelta(days=10)  # Day 10

    # Build initial milestones
    milestones = model.build_voyage_milestones("VY001", departure)
    assert "SI_CUTOFF" in milestones
    assert "VGM_CUTOFF" in milestones
    assert "EMPTY_RELEASE" in milestones

    # SI_CUTOFF is departure - 48h (Day 8 00:00)
    assert milestones["SI_CUTOFF"].target_time == departure - timedelta(hours=48)

    # Departure is delayed by 24h (Day 11)
    new_departure = departure + timedelta(hours=24)
    updated = model.recalculate_on_departure_change(milestones, new_departure, sim_time)
    assert len(updated) > 0

    # SI_CUTOFF shifted to Day 9 00:00 (new_departure - 48h)
    assert milestones["SI_CUTOFF"].target_time == new_departure - timedelta(hours=48)
