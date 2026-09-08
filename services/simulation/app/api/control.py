"""
Simulation Control Router
=========================
FastAPI endpoints for lifecycle management, time advancement, and disruption injection.

Doc 1 §5, Doc 2 §2.2
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.clock.simulation_clock import SimulationClock
from app.config.parameters import get_registry
from app.controller.simulation_controller import SimulationController
from app.db.database import AsyncSessionLocal
from app.engine.simulation_kernel import SimulationKernel
from app.events.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation-control"])

# ---------------------------------------------------------------------------
# Singleton Controller Provider
# ---------------------------------------------------------------------------

_controller: Optional[SimulationController] = None


def get_controller() -> SimulationController:
    global _controller
    if _controller is None:
        start_time = datetime(2026, 9, 1, 0, 0, tzinfo=timezone.utc)
        clock = SimulationClock(start_time)
        registry = get_registry()
        bus = get_event_bus()
        kernel = SimulationKernel(clock, registry, bus)
        _controller = SimulationController(
            clock=clock,
            registry=registry,
            event_bus=bus,
            kernel=kernel,
            session_factory=AsyncSessionLocal,
        )
    return _controller


def set_controller(controller: SimulationController) -> None:
    global _controller
    _controller = controller


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------

class StartRequest(BaseModel):
    scenario_id: str = Field(default="NORMAL", description="Scenario identifier")
    seed: int = Field(default=42, description="RNG seed")
    start_time: Optional[datetime] = Field(default=None, description="Starting T_sim")
    world_id: str = Field(default="world-2", description="World environment identifier")


class AdvanceRequest(BaseModel):
    delta_hours: float = Field(
        default=24.0,
        gt=0.0,
        le=24.0,
        description="Time advancement in simulated hours (0 < Δt ≤ 24h per Doc 2 §2.2)",
    )


class InjectDisruptionRequest(BaseModel):
    disruption_type: str = Field(..., description="Disruption type e.g. STORM, PORT_STRIKE")
    severity: float = Field(default=0.5, ge=0.0, le=1.0, description="Severity [0, 1]")
    duration_hours: float = Field(default=24.0, gt=0.0, description="Disruption active duration")
    affected_entity_ids: Optional[List[str]] = Field(default=None, description="Target entity IDs")
    parameter_overrides: Optional[Dict[str, Any]] = Field(default=None, description="Parameter overrides")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start", status_code=status.HTTP_200_OK)
async def start_simulation(
    req: StartRequest,
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Initialize or start a simulation run."""
    try:
        state = await controller.start(
            scenario_id=req.scenario_id,
            seed=req.seed,
            start_time=req.start_time,
            world_id=req.world_id,
        )
        return {
            "message": "Simulation started successfully",
            "run_id": str(state.run_id),
            "simulation_time": state.simulation_time.isoformat(),
            "world_id": state.world_id,
            "scenario_id": req.scenario_id,
            "ports_count": len(state.ports),
            "vessels_count": len(state.vessels),
        }
    except Exception as ex:
        logger.exception("Failed to start simulation")
        raise HTTPException(status_code=400, detail=str(ex))


@router.post("/advance", status_code=status.HTTP_200_OK)
async def advance_simulation(
    req: AdvanceRequest,
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Advance the simulation clock by Δt (0 < Δt ≤ 24h)."""
    try:
        state, events = await controller.advance(req.delta_hours)
        return {
            "message": f"Simulation advanced by {req.delta_hours} hours",
            "simulation_time": state.simulation_time.isoformat(),
            "events_emitted": len(events),
            "kpis": {
                "total_cost": state.kpis.total_cost,
                "vessels_delayed": state.kpis.vessels_delayed,
                "delay_hours": state.kpis.total_delay_hours,
            },
        }
    except Exception as ex:
        logger.exception("Failed to advance simulation")
        raise HTTPException(status_code=400, detail=str(ex))


@router.post("/pause", status_code=status.HTTP_200_OK)
async def pause_simulation(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, str]:
    """Pause running simulation."""
    await controller.pause()
    return {"message": "Simulation paused"}


@router.post("/resume", status_code=status.HTTP_200_OK)
async def resume_simulation(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, str]:
    """Resume paused simulation."""
    await controller.resume()
    return {"message": "Simulation resumed"}


@router.post("/reset", status_code=status.HTTP_200_OK)
async def reset_simulation(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, str]:
    """Reset simulation to idle."""
    await controller.reset()
    return {"message": "Simulation reset to IDLE"}


@router.post("/inject-disruption", status_code=status.HTTP_202_ACCEPTED)
async def inject_disruption(
    req: InjectDisruptionRequest,
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, str]:
    """Inject an operational disruption via the event queue (Rule 4)."""
    try:
        dis_id = await controller.inject_disruption(
            disruption_type=req.disruption_type,
            severity=req.severity,
            duration_hours=req.duration_hours,
            affected_entity_ids=req.affected_entity_ids,
            parameter_overrides=req.parameter_overrides,
        )
        return {
            "message": "Disruption scheduled successfully",
            "disruption_id": dis_id,
        }
    except Exception as ex:
        logger.exception("Failed to inject disruption")
        raise HTTPException(status_code=400, detail=str(ex))
