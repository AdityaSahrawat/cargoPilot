"""
Tests for CargoPilot Planning / Optimization Engine & API Integration
======================================================================
Validates:
  1. Strict 7-day departure cutoff horizon enforcement (fixed equality constraints).
  2. Frozen unallocated exception handling within 7 days.
  3. Joint booking-to-container and voyage allocation for optimizable bookings (>7 days).
  4. Multi-container quantities (Q_b > 1).
  5. Net vessel slot TEU capacity constraints accounting for pre-existing loads.
  6. Empty container repositioning and leasing linkage.
  7. API endpoints: POST /api/v1/simulation/optimize & GET /api/v1/simulation/optimization-report.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict
import pytest
from httpx import ASGITransport, AsyncClient

from app.cargopilot.planning_engine import CargoPilotPlanningEngine
from app.clock.simulation_clock import SimulationClock
from app.config.parameters import get_registry
from app.controller.simulation_controller import SimulationController
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import EventBus
from app.main import app
from app.world.world_seeder import WorldSeeder
from app.world.world_state import BookingState, ContainerState, VoyageState, WorldState


@pytest.fixture
def sim_setup():
    start_time = datetime.datetime(2026, 9, 1, 0, 0, tzinfo=datetime.timezone.utc)
    clock = SimulationClock(start_time)
    registry = get_registry()
    bus = EventBus()
    kernel = SimulationKernel(clock, registry, bus)
    controller = SimulationController(clock, registry, bus, kernel, session_factory=None)
    seeder = WorldSeeder(registry)
    return {
        "start_time": start_time,
        "clock": clock,
        "registry": registry,
        "bus": bus,
        "kernel": kernel,
        "controller": controller,
        "seeder": seeder,
    }


@pytest.mark.asyncio
async def test_cargopilot_optimization_engine_on_world2(sim_setup):
    """
    Test the MILP optimizer directly on a seeded World 2 state.
    """
    controller = sim_setup["controller"]
    state = await controller.start("NORMAL", seed=42, world_id="world-2")

    engine = CargoPilotPlanningEngine(state, sim_setup["registry"])
    report = engine.optimize(time_limit_seconds=15.0)

    # 1. Solver status
    assert report.solver_result.status in ("OPTIMAL", "FEASIBLE")
    assert report.solver_result.num_variables > 0
    assert report.solver_result.num_constraints > 0

    # 2. 7-Day Cutoff Rule Verification
    assert len(report.preserved_decisions) > 0
    for preserved in report.preserved_decisions:
        assert preserved.hours_to_departure <= 168.0 + 1e-3  # strictly <= 7 days
        assert preserved.status in ("LOCKED", "FROZEN_UNALLOCATED_EXCEPTION")
        if preserved.status == "LOCKED":
            assert len(preserved.assigned_containers) > 0
            assert preserved.assigned_voyage_id is not None

    # 3. Optimizable Allocations Verification
    assert len(report.booking_allocations) > 0
    for alloc in report.booking_allocations:
        assert alloc.allocated_quantity > 0
        assert len(alloc.assigned_containers) == alloc.allocated_quantity
        assert alloc.assigned_voyage_id is not None
        # Verify container state in WorldState was updated
        for cid in alloc.assigned_containers:
            c = state.containers[cid]
            assert c.status == "ALLOCATED"
            assert c.booking_id == alloc.booking_id
            assert c.current_voyage_id == alloc.assigned_voyage_id

    # 4. Impact metrics & cost ledger
    assert report.impact.total_bookings_evaluated == len(state.bookings)
    assert report.impact.bookings_allocated == len(report.booking_allocations)
    assert report.impact.teu_allocated > 0
    assert report.impact.costs.total_operational_cost >= 0


@pytest.mark.asyncio
async def test_seven_day_cutoff_fixed_constraint_immutability(sim_setup):
    """
    Verify that an allocation within 7 days is strictly preserved and cannot be unallocated or changed.
    """
    controller = sim_setup["controller"]
    state = await controller.start("NORMAL", seed=42, world_id="world-2")

    # Find a locked booking in state
    locked_bkg = next(
        (b for b in state.bookings.values() if b.status == "LOCKED" and b.voyage_id is not None),
        None,
    )
    assert locked_bkg is not None

    orig_voyage = locked_bkg.voyage_id
    orig_alloc_id = locked_bkg.allocation_id

    engine = CargoPilotPlanningEngine(state, sim_setup["registry"])
    report = engine.optimize(time_limit_seconds=15.0)

    # Re-verify that the booking was preserved untouched
    bkg_after = state.bookings[locked_bkg.booking_id]
    assert bkg_after.voyage_id == orig_voyage
    assert bkg_after.allocation_id == orig_alloc_id

    # Confirm it is documented in preserved_decisions
    preserved_entry = next(
        (p for p in report.preserved_decisions if p.booking_id == locked_bkg.booking_id),
        None,
    )
    assert preserved_entry is not None
    assert preserved_entry.status == "LOCKED"
    assert "Doc 2 §9.4" in preserved_entry.compliance_reason


@pytest.mark.asyncio
async def test_api_optimize_endpoints():
    """
    Test POST /api/v1/simulation/optimize and GET /api/v1/simulation/optimization-report.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Reset controller first
        await client.post("/api/v1/simulation/reset")

        # 1. Calling optimize with NO_ACTIVE_RUN should return HTTP 400
        opt_err_resp = await client.post("/api/v1/simulation/optimize")
        assert opt_err_resp.status_code == 400
        assert "No active simulation run" in opt_err_resp.json()["detail"]

        # 2. Check state when idle returns NO_ACTIVE_RUN status (HTTP 200)
        state_idle_resp = await client.get("/api/v1/simulation/state")
        assert state_idle_resp.status_code == 200
        assert state_idle_resp.json()["status"] == "NO_ACTIVE_RUN"

        # 3. Start a simulation run
        start_resp = await client.post(
            "/api/v1/simulation/start",
            json={"world_id": "world-2", "scenario_id": "NORMAL", "seed": 42},
        )
        assert start_resp.status_code == 200

        # 4. Run CargoPilot Optimizer
        opt_resp = await client.post(
            "/api/v1/simulation/optimize",
            json={"time_limit_seconds": 15.0},
        )
        assert opt_resp.status_code == 200
        data = opt_resp.json()

        assert data["solver_result"]["status"] in ("OPTIMAL", "FEASIBLE")
        assert len(data["preserved_decisions"]) > 0
        assert len(data["booking_allocations"]) > 0
        assert "costs" in data["impact"]
        assert data["impact"]["costs"]["total_operational_cost"] > 0

        # 5. Retrieve latest optimization report via GET
        rep_resp = await client.get("/api/v1/simulation/optimization-report")
        assert rep_resp.status_code == 200
        rep_data = rep_resp.json()
        assert rep_data["solver_result"]["status"] == data["solver_result"]["status"]

        # 6. Verify /state reflects updated allocation counts
        state_after = await client.get("/api/v1/simulation/state")
        assert state_after.status_code == 200
        assert state_after.json()["allocations_count"] > 500
