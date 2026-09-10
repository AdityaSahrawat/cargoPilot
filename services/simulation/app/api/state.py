"""
Simulation State Router
=======================
FastAPI endpoints for inspecting world state, entities, KPIs, and recent event history.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.control import get_controller
from app.controller.simulation_controller import SimulationController
from app.db.database import get_db_session
from app.db.sim_models import SimulationEvent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/simulation", tags=["simulation-state"])


@router.get("/status", status_code=status.HTTP_200_OK)
async def get_status(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Return current execution status, simulation time, and run metadata."""
    return controller.get_status()


@router.get("/state", status_code=status.HTTP_200_OK)
async def get_full_state(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Return top-level counts and summary of the active world state."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return {
        "run_id": str(state.run_id),
        "baseline_id": state.world_baseline_id,
        "world_id": state.world_id,
        "simulation_time": state.simulation_time.isoformat(),
        "vessels_count": len(state.vessels),
        "ports_count": len(state.ports),
        "voyages_count": len(state.voyages),
        "containers_count": len(state.containers),
        "bookings_count": len(state.bookings),
        "leases_count": len(state.leases),
        "equipment_balances_count": len(state.equipment),
        "demand_forecast_count": len(state.demand.current_demand),
        "active_disruptions_count": len(state.active_disruptions),
        "kpis": {
            "total_cost": state.kpis.total_cost,
            "vessels_delayed": state.kpis.vessels_delayed,
            "delay_hours": state.kpis.total_delay_hours,
            "equipment_shortages": state.kpis.equipment_shortages,
        },
    }


@router.get("/state/vessels", status_code=status.HTTP_200_OK)
async def get_vessels(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return state of all vessels."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "vessel_id": v.vessel_id,
            "name": v.name,
            "status": v.status,
            "current_voyage_id": v.current_voyage_id,
            "current_port_id": v.current_port_id,
            "origin_port_id": v.origin_port_id,
            "destination_port_id": v.destination_port_id,
            "position_fraction": v.position_fraction,
            "distance_remaining_nm": v.distance_remaining_nm,
            "current_speed_knots": v.current_speed_knots,
            "eta": v.eta.isoformat() if v.eta else None,
            "schedule_variance_hours": v.schedule_variance_hours,
            "condition": v.condition,
        }
        for v in state.vessels.values()
    ]


@router.get("/state/ports", status_code=status.HTTP_200_OK)
async def get_ports(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return state of all ports, including congestion and berth queues."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "port_id": p.port_id,
            "unlocode": p.unlocode,
            "name": p.name,
            "latitude": p.latitude,
            "longitude": p.longitude,
            "berths_total": p.berths_total,
            "berths_occupied": p.berths_occupied,
            "berths_available": p.berths_available,
            "vessel_queue_count": len(p.vessel_queue),
            "vessel_queue": p.vessel_queue,
            "congestion_index": p.congestion_index,
            "is_strike_active": p.is_strike_active,
            "is_closed": p.is_closed,
        }
        for p in state.ports.values()
    ]


@router.get("/state/containers", status_code=status.HTTP_200_OK)
async def get_containers(
    limit: int = Query(default=100, le=1000),
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return list of container states up to limit."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    containers = list(state.containers.values())[:limit]
    return [
        {
            "container_id": c.container_id,
            "equipment_type": c.equipment_type,
            "status": c.status,
            "condition": c.condition,
            "location_id": c.current_location_id,
            "voyage_id": c.current_voyage_id,
            "booking_id": c.booking_id,
        }
        for c in containers
    ]


@router.get("/state/bookings", status_code=status.HTTP_200_OK)
async def get_bookings(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return list of active bookings."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "booking_id": b.booking_id,
            "origin_port_id": b.origin_port_id,
            "destination_port_id": b.destination_port_id,
            "equipment_type": b.equipment_type,
            "quantity": b.quantity,
            "status": b.status,
            "lock_status": b.lock_status,
            "cutoff_time": b.cutoff_time.isoformat() if b.cutoff_time else None,
        }
        for b in state.bookings.values()
    ]


@router.get("/state/disruptions", status_code=status.HTTP_200_OK)
async def get_disruptions(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return all active and historical disruptions for current run."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "disruption_id": d.disruption_id,
            "disruption_type": d.disruption_type,
            "status": d.status,
            "severity": d.severity,
            "start_time": d.start_time.isoformat() if d.start_time else None,
            "end_time": d.end_time.isoformat() if d.end_time else None,
            "affected_entity_ids": d.affected_entity_ids,
        }
        for d in state.disruptions
    ]


@router.get("/state/kpis", status_code=status.HTTP_200_OK)
async def get_kpis(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Return complete KPI and cost accumulator values."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    kpis = state.kpis
    return {
        "total_cost": kpis.total_cost,
        "total_delay_cost": kpis.total_delay_cost,
        "total_lease_cost": kpis.total_lease_cost,
        "total_repositioning_cost": kpis.total_repositioning_cost,
        "total_storage_cost": kpis.total_storage_cost,
        "total_shortage_penalty": kpis.total_shortage_penalty,
        "total_disruption_cost": kpis.total_disruption_cost,
        "total_delay_hours": kpis.total_delay_hours,
        "vessels_delayed": kpis.vessels_delayed,
        "bookings_created": kpis.bookings_created,
        "bookings_fulfilled": kpis.bookings_fulfilled,
        "bookings_cancelled": kpis.bookings_cancelled,
        "equipment_shortages": kpis.equipment_shortages,
    }


@router.get("/state/voyages", status_code=status.HTTP_200_OK)
async def get_voyages(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return state of all voyages."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "voyage_id": vy.voyage_id,
            "vessel_id": vy.vessel_id,
            "origin_port_id": vy.origin_port_id,
            "destination_port_id": vy.destination_port_id,
            "scheduled_departure": vy.scheduled_departure.isoformat() if vy.scheduled_departure else None,
            "scheduled_arrival": vy.scheduled_arrival.isoformat() if vy.scheduled_arrival else None,
            "actual_departure": vy.actual_departure.isoformat() if vy.actual_departure else None,
            "estimated_arrival": vy.estimated_arrival.isoformat() if vy.estimated_arrival else None,
            "actual_arrival": vy.actual_arrival.isoformat() if vy.actual_arrival else None,
            "status": vy.status,
            "route_distance_nm": vy.route_distance_nm,
            "capacity_teu": vy.capacity_teu,
            "booked_teu": vy.booked_teu,
        }
        for vy in state.voyages.values()
    ]


@router.get("/state/demand", status_code=status.HTTP_200_OK)
async def get_demand(
    controller: SimulationController = Depends(get_controller),
) -> Dict[str, Any]:
    """Return active demand forecast and signals."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    current = [
        {
            "origin_port_id": k[0],
            "destination_port_id": k[1],
            "equipment_type": k[2],
            "forecast_units": v,
        }
        for k, v in state.demand.current_demand.items()
    ]
    historical = [
        {
            "origin_port_id": k[0],
            "destination_port_id": k[1],
            "equipment_type": k[2],
            "day_offset": k[3],
            "volume": v,
        }
        for k, v in list(state.demand.historical_demand.items())[:50]
    ]
    return {
        "current_demand": current,
        "historical_demand": historical,
        "total_demand_forecast": sum(item["forecast_units"] for item in current),
    }


@router.get("/state/leases", status_code=status.HTTP_200_OK)
async def get_leases(
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return all equipment lease agreements."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    return [
        {
            "lease_id": l.lease_id,
            "location_id": l.location_id,
            "equipment_type": l.equipment_type,
            "quantity": l.quantity,
            "daily_rate": l.daily_rate,
            "start_time": l.start_time.isoformat() if l.start_time else None,
            "duration_days": l.duration_days,
            "status": l.status,
            "equipment_available_at": l.equipment_available_at.isoformat() if l.equipment_available_at else None,
        }
        for l in state.leases.values()
    ]


@router.get("/state/equipment", status_code=status.HTTP_200_OK)
async def get_equipment(
    limit: int = Query(default=200, le=1000),
    controller: SimulationController = Depends(get_controller),
) -> List[Dict[str, Any]]:
    """Return equipment balances by location and equipment type."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    balances = list(state.equipment.values())[:limit]
    return [
        {
            "location_id": eq.location_id,
            "equipment_type": eq.equipment_type,
            "available": eq.available,
            "allocated": eq.allocated,
            "in_transit": eq.in_transit,
            "unavailable": eq.unavailable,
            "target": eq.target,
            "total": eq.total,
            "shortage": eq.shortage,
            "surplus": eq.surplus,
            "deficit": eq.deficit,
        }
        for eq in balances
    ]


@router.get("/state/events", status_code=status.HTTP_200_OK)
async def get_recent_events(
    limit: int = Query(default=20, le=100),
    controller: SimulationController = Depends(get_controller),
    db: AsyncSession = Depends(get_db_session),
) -> List[Dict[str, Any]]:
    """Return the most recent simulation events for the current run, ordered by simulation_time DESC."""
    state = controller.state
    if not state:
        raise HTTPException(status_code=404, detail="No active simulation run")

    run_id = state.run_id

    result = await db.execute(
        select(SimulationEvent)
        .where(SimulationEvent.run_id == run_id)
        .order_by(desc(SimulationEvent.simulation_time))
        .limit(limit)
    )
    events = result.scalars().all()

    return [
        {
            "event_id": str(e.event_id),
            "event_type": e.event_type,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "simulation_time": e.simulation_time.isoformat(),
            "source": e.source,
            "payload": e.payload or {},
            "caused_by_event_id": str(e.caused_by_event_id) if e.caused_by_event_id else None,
        }
        for e in events
    ]
