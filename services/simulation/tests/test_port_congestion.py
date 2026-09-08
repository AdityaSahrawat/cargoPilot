"""
Unit tests for Port & Terminal Model and Nonlinear Congestion (Doc 2 §5).
"""
import pytest
from datetime import datetime, timezone
from uuid import uuid4

from app.config.parameters import ParameterRegistry
from app.models.port_model import (
    PortModel,
    calculate_utilization,
    calculate_congestion_factor,
    calculate_handling_time,
    calculate_effective_berths,
)
from app.world.world_state import PortState, VesselState, WorldState


def test_resource_utilization():
    """Doc 2 §5.4: U = ResourceUsage / ResourceCapacity."""
    assert calculate_utilization(usage=0, capacity=10) == 0.0
    assert calculate_utilization(usage=5, capacity=10) == 0.5
    assert calculate_utilization(usage=10, capacity=10) == 1.0
    assert calculate_utilization(usage=12, capacity=10) == 1.2
    assert calculate_utilization(usage=0, capacity=0) == 0.0


def test_nonlinear_congestion_formula():
    """
    Doc 2 §5.5:
        For U ≤ U_c: F_cong = 1.0
        For U > U_c: F_cong = 1 + α * ((U - U_c) / (1 - U_c))^β
    """
    uc = 0.80
    alpha = 2.0
    beta = 2.0

    # Below threshold -> no congestion
    assert calculate_congestion_factor(0.50, uc, alpha, beta) == 1.0
    assert calculate_congestion_factor(0.80, uc, alpha, beta) == 1.0

    # Midway between threshold and max capacity: U = 0.90
    # normalized = (0.90 - 0.80) / (1.0 - 0.80) = 0.50
    # F_cong = 1.0 + 2.0 * (0.50)^2 = 1.0 + 2.0 * 0.25 = 1.50
    f_cong_90 = calculate_congestion_factor(0.90, uc, alpha, beta)
    assert pytest.approx(f_cong_90, rel=1e-3) == 1.50

    # At full capacity: U = 1.00
    # normalized = (1.0 - 0.80) / 0.20 = 1.0
    # F_cong = 1.0 + 2.0 * (1.0)^2 = 3.00
    f_cong_100 = calculate_congestion_factor(1.00, uc, alpha, beta)
    assert pytest.approx(f_cong_100, rel=1e-3) == 3.00


def test_handling_time_multiplier():
    """Doc 2 §5.5: T_handling = T_base * F_congestion."""
    base_time = 10.0  # hours
    f_cong = 1.50
    assert calculate_handling_time(base_time, f_cong) == 15.0


def test_berth_fifo_queue_management():
    """Doc 2 §4.9, §5.2: Berth allocation and FIFO queueing."""
    registry = ParameterRegistry()
    port_model = PortModel(registry)

    start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
    state = WorldState(run_id=uuid4(), simulation_time=start_time, world_id="world-2")

    port = PortState(
        port_id="NLRTM",
        unlocode="NLRTM",
        berths_total=2,
        berths_occupied=0,
        vessel_queue=[],
    )
    state.ports["NLRTM"] = port

    # 1. First vessel requests berth -> Granted
    assert port_model.request_berth(port, "V001", state) is True
    assert port.berths_occupied == 1
    assert port_model.get_berths_available(port) == 1

    # 2. Second vessel requests berth -> Granted
    assert port_model.request_berth(port, "V002", state) is True
    assert port.berths_occupied == 2
    assert port_model.get_berths_available(port) == 0

    # 3. Third and fourth vessels arrive -> Enqueued in FIFO order
    assert port_model.request_berth(port, "V003", state) is False
    assert port_model.request_berth(port, "V004", state) is False
    assert port.vessel_queue == ["V003", "V004"]
    assert port.berths_occupied == 2

    # 4. First berth is released -> Immediately allocated to V003 (FIFO)
    next_vessel = port_model.release_berth(port, state)
    assert next_vessel == "V003"
    assert port.vessel_queue == ["V004"]
    assert port.berths_occupied == 2

    # 5. Second berth is released -> Allocated to V004 (FIFO)
    next_vessel = port_model.release_berth(port, state)
    assert next_vessel == "V004"
    assert port.vessel_queue == []
    assert port.berths_occupied == 2

    # 6. Another release -> Queue is empty, berths_occupied drops to 1
    next_vessel = port_model.release_berth(port, state)
    assert next_vessel is None
    assert port.berths_occupied == 1


def test_port_strike_and_closure():
    """Doc 2 §5.2, §14.5: Strike reduces capacity; closure drops capacity to 0."""
    berths_total = 10

    # Normal conditions
    assert calculate_effective_berths(berths_total) == 10

    # 50% capacity strike
    assert calculate_effective_berths(berths_total, is_strike_active=True, strike_capacity_factor=0.5) == 5

    # Complete closure
    assert calculate_effective_berths(berths_total, is_closed=True) == 0
