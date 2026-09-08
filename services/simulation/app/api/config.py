"""
Simulation Configuration Router
===============================
FastAPI endpoints for inspecting and editing simulation parameters, scenarios, and disruption types.

Doc 2 §24 — Parameters & Configuration
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.config.disruption_types import DisruptionType
from app.config.parameters import ParameterRegistry, SimParameter, get_registry
from app.config.scenario_configs import SCENARIOS, ScenarioConfig, get_scenario

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulation/config", tags=["simulation-config"])


class UpdateParameterRequest(BaseModel):
    value: Any = Field(..., description="New parameter value")
    scope_key: Optional[str] = Field(default=None, description="Scope key override (e.g. port/vessel class)")


@router.get("/parameters", status_code=status.HTTP_200_OK)
async def list_parameters(
    model: Optional[str] = Query(default=None, description="Filter by model name"),
    registry: ParameterRegistry = Depends(get_registry),
) -> List[Dict[str, Any]]:
    """List all configurable simulation parameters."""
    params = registry.all_params()
    if model:
        params = [p for p in params if p.model.lower() == model.lower()]

    return [
        {
            "name": p.name,
            "model": p.model,
            "description": p.description,
            "value": p.value,
            "default": p.default,
            "unit": p.unit,
            "param_type": p.param_type.value,
            "scope": p.scope.value,
            "admin_editable": p.admin_editable,
            "runtime_editable": p.runtime_editable,
        }
        for p in params
    ]


@router.get("/parameters/{name}", status_code=status.HTTP_200_OK)
async def get_parameter(
    name: str,
    scope_key: Optional[str] = Query(default=None),
    registry: ParameterRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Get single parameter details and resolved value."""
    try:
        p = registry.describe(name)
        resolved_val = registry.get(name, scope_key=scope_key)
        return {
            "name": p.name,
            "model": p.model,
            "description": p.description,
            "value": resolved_val,
            "default": p.default,
            "unit": p.unit,
            "min_value": p.min_value,
            "max_value": p.max_value,
            "param_type": p.param_type.value,
            "scope": p.scope.value,
            "admin_editable": p.admin_editable,
            "runtime_editable": p.runtime_editable,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Parameter '{name}' not found")


@router.patch("/parameters/{name}", status_code=status.HTTP_200_OK)
async def update_parameter(
    name: str,
    req: UpdateParameterRequest,
    registry: ParameterRegistry = Depends(get_registry),
) -> Dict[str, Any]:
    """Update parameter value."""
    try:
        registry.set(name, req.value, scope_key=req.scope_key)
        resolved_val = registry.get(name, scope_key=req.scope_key)
        return {
            "message": f"Parameter '{name}' updated successfully",
            "name": name,
            "new_value": resolved_val,
            "scope_key": req.scope_key,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Parameter '{name}' not found")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


@router.get("/scenarios", status_code=status.HTTP_200_OK)
async def list_scenarios() -> List[Dict[str, Any]]:
    """List all available simulation scenarios."""
    return [
        {
            "id": s.scenario_id,
            "name": s.scenario_id,
            "description": s.description,
            "disruptions": [d.disruption_type.value if hasattr(d.disruption_type, "value") else str(d.disruption_type) for d in s.disruptions],
            "parameter_overrides_count": len(s.parameter_overrides),
        }
        for s in SCENARIOS.values()
    ]


@router.get("/scenarios/{scenario_id}", status_code=status.HTTP_200_OK)
async def get_scenario_detail(scenario_id: str) -> Dict[str, Any]:
    """Get full details of a specific scenario configuration."""
    try:
        s = get_scenario(scenario_id)
        return {
            "id": s.scenario_id,
            "name": s.scenario_id,
            "description": s.description,
            "disruptions": [
                {
                    "type": d.disruption_type.value if hasattr(d.disruption_type, "value") else str(d.disruption_type),
                    "start_offset_hours": d.start_offset_hours,
                    "duration_hours": d.duration_hours,
                    "severity": d.severity,
                    "affected_entity_ids": d.affected_entity_ids,
                }
                for d in s.disruptions
            ],
            "parameter_overrides": s.parameter_overrides,
        }
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found")


@router.get("/disruption-types", status_code=status.HTTP_200_OK)
async def list_disruption_types() -> List[Dict[str, str]]:
    """List all supported operational disruption types."""
    return [
        {"type": dt.value, "name": dt.name}
        for dt in DisruptionType
    ]
