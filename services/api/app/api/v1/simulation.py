from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.db.database import get_test_db
from app.db.enums import ContainerType
from app.test_worlds.world_1.db_seeder import load_world_1_from_db
from app.test_worlds.world_1.fixtures import get_world_1_dataset
from app.test_worlds.world_2.fixtures_v2 import get_world_2_dataset
from app.optimization.milp_solver import CargoPilotMILPSolver
from app.simulation.daily_engine import DailySimulationEngine
from app.validation.data_validator import CargoPilotValidator

router = APIRouter()


@router.get("/world-1/summary")
def get_world_1_summary(db: Session = Depends(get_test_db)):
    """Returns live ground-truth metadata dynamically loaded from cargo_pilot_test.db."""
    data = load_world_1_from_db(db)
    return {
        "world_id": "WORLD-01",
        "name": "Mathematical Validation World (4 Ports, 6 Voyages, 40 Days)",
        "horizon_days": data.horizon_days,
        "ports": [
            {
                "unlocode": p.unlocode,
                "name": p.name,
                "country": p.country,
                "capacity_teu": p.storage_capacity_teu,
                "safety_stock_teu": p.safety_stock_teu,
                "devanning_lead_time_days": p.devanning_lead_time_days,
            }
            for p in data.ports.values()
        ],
        "vessels": [
            {
                "imo_number": v.imo_number,
                "name": v.name,
                "capacity_teu": v.container_capacity_teu,
                "deadweight_mt": v.deadweight_capacity_mt,
            }
            for v in data.vessels
        ],
        "voyage_legs": [
            {
                "leg_id": l.leg_id,
                "voyage_number": l.voyage_number,
                "vessel_name": l.vessel_name,
                "from_port": l.from_port_unlocode,
                "to_port": l.to_port_unlocode,
                "departure_day": l.departure_day,
                "arrival_day": l.arrival_day,
                "capacity_teu": l.capacity_teu,
                "capacity_weight_mt": l.capacity_weight_mt,
            }
            for l in data.voyage_legs
        ],
        "bookings": [
            {
                "booking_id": b.booking_id,
                "origin": b.origin_unlocode,
                "destination": b.destination_unlocode,
                "container_type": b.container_type.value,
                "quantity": b.quantity,
                "cargo_ready_day": b.cargo_ready_day,
                "delivery_deadline_day": b.delivery_deadline_day,
                "priority": b.priority.value,
            }
            for b in data.bookings
        ],
    }


@router.post("/world-1/solve-milp")
def solve_world_1_milp(db: Session = Depends(get_test_db)):
    """Runs the exact master MILP solver on cargo_pilot_test.db data and returns optimal decision plan."""
    data = load_world_1_from_db(db)
    solver = CargoPilotMILPSolver(data)
    sol = solver.solve(solver_choice="highs")
    return {
        "solver_name": sol.solver_name,
        "solver_status": sol.solver_status,
        "optimality_gap": sol.optimality_gap,
        "objective_value": sol.objective_value,
        "best_bound": sol.best_bound,
        "solve_time_seconds": sol.solve_time_seconds,
        "cost_breakdown": {
            "repositioning_cost": sol.total_repositioning_cost,
            "leasing_cost": sol.total_leasing_cost,
            "holding_cost": sol.total_holding_cost,
            "shortage_penalty": sol.total_shortage_penalty,
            "safety_stock_penalty": sol.total_safety_stock_penalty,
        },
        "booking_decisions": [
            {
                "booking_id": bd.booking_id,
                "path_id": bd.selected_path_id,
                "container_type": bd.container_type.value,
                "owned_quantity": bd.owned_quantity,
                "leased_quantity": bd.leased_quantity,
                "unserved_quantity": bd.unserved_quantity,
                "legs": bd.legs_traversed,
                "departure_day": bd.departure_day,
                "arrival_day": bd.arrival_day,
                "cost": bd.fulfillment_cost,
            }
            for bd in sol.booking_decisions
        ],
        "repositioning_decisions": [
            {
                "leg_id": rd.leg_id,
                "voyage_number": rd.voyage_number,
                "from_port": rd.from_port,
                "to_port": rd.to_port,
                "departure_day": rd.departure_day,
                "arrival_day": rd.arrival_day,
                "container_type": rd.container_type.value,
                "quantity": rd.quantity,
                "cost": rd.cost,
            }
            for rd in sol.repositioning_decisions
        ],
    }


@router.post("/world-1/run")
def run_world_1_simulation(db: Session = Depends(get_test_db)):
    """Executes the 40-day simulation using live cargo_pilot_test.db SQLite data and returns the full trajectory."""
    data = load_world_1_from_db(db)
    engine = DailySimulationEngine(data)
    history = engine.run_all()
    # Build Port Horizon Insights across the 40-day optimization window
    port_insights = []
    for port in data.ports.values():
        un = port.unlocode
        safety = port.safety_stock_teu

        # Calculate TEU trajectory for this port across all days
        trajectory = []
        for s in history:
            inv = s.port_inventories.get(un, {})
            teu = (inv.get("20FT_DRY", 0) * 1.0) + (inv.get("40FT_DRY", 0) * 2.0) + (inv.get("40FT_HIGH_CUBE", 0) * 2.0)
            trajectory.append((s.day, teu))

        init_teu = trajectory[0][1] if trajectory else 0
        min_day, min_teu = min(trajectory, key=lambda x: x[1]) if trajectory else (0, 0)
        max_day, max_teu = max(trajectory, key=lambda x: x[1]) if trajectory else (0, 0)

        if min_teu < safety:
            deficit_status = "CRITICAL_DEFICIT_RISK"
            explanation = f"Stock drops to {min_teu:.0f} TEU on Day {min_day} (below {safety} TEU safety threshold). CargoPilot solver schedules empty repositioning and leased buffers to prevent severe shortage penalties."
        elif min_teu < safety * 1.25:
            deficit_status = "TIGHT_BUFFER"
            explanation = f"Stock reaches tight buffer of {min_teu:.0f} TEU on Day {min_day} (target safety: {safety} TEU). Fully covered by incoming laden devanning and planned voyage calls."
        else:
            deficit_status = "SURPLUS_STABLE"
            explanation = f"Inventory remains well above safety threshold ({safety} TEU) throughout the entire 40-day horizon (Low: {min_teu:.0f} TEU on Day {min_day}). Acts as an equipment export hub."

        port_insights.append({
            "port_unlocode": un,
            "port_name": port.name,
            "initial_stock_teu": init_teu,
            "min_stock_teu": min_teu,
            "min_stock_day": min_day,
            "max_stock_teu": max_teu,
            "max_stock_day": max_day,
            "safety_stock_teu": safety,
            "deficit_status": deficit_status,
            "explanation": explanation,
        })

    # Map booking details for quick lookup
    booking_dict = {b.booking_id: b for b in data.bookings}

    # For each leg, calculate assigned laden bookings and empty repositioning
    leg_laden_bookings: Dict[str, List[Dict[str, Any]]] = {l.leg_id: [] for l in data.voyage_legs}
    leg_laden_teu: Dict[str, float] = {l.leg_id: 0.0 for l in data.voyage_legs}
    leg_empty_repositions: Dict[str, List[Dict[str, Any]]] = {l.leg_id: [] for l in data.voyage_legs}
    leg_empty_teu: Dict[str, float] = {l.leg_id: 0.0 for l in data.voyage_legs}

    for bd in engine.master_solution.booking_decisions:
        total_qty = bd.owned_quantity + bd.leased_quantity
        if total_qty <= 0:
            continue
        factor = 1.0 if bd.container_type == ContainerType.DRY_20FT else 2.0
        teu = total_qty * factor
        bk_info = booking_dict.get(bd.booking_id)
        dest = bk_info.destination_unlocode if bk_info else "—"
        orig = bk_info.origin_unlocode if bk_info else "—"

        for leg_id in bd.legs_traversed:
            if leg_id in leg_laden_bookings:
                leg_laden_bookings[leg_id].append({
                    "booking_id": bd.booking_id,
                    "origin": orig,
                    "destination": dest,
                    "container_type": bd.container_type.value,
                    "quantity": total_qty,
                    "teu_load": teu,
                    "owned_qty": bd.owned_quantity,
                    "leased_qty": bd.leased_quantity,
                })
                leg_laden_teu[leg_id] += teu

    for rd in engine.master_solution.repositioning_decisions:
        if rd.quantity <= 0:
            continue
        factor = 1.0 if rd.container_type == ContainerType.DRY_20FT else 2.0
        teu = rd.quantity * factor
        if rd.leg_id in leg_empty_repositions:
            leg_empty_repositions[rd.leg_id].append({
                "from_port": rd.from_port,
                "to_port": rd.to_port,
                "container_type": rd.container_type.value,
                "quantity": rd.quantity,
                "teu_load": teu,
            })
            leg_empty_teu[rd.leg_id] += teu

    # Build Port Vessel Manifests
    port_vessel_schedules = []
    for port in data.ports.values():
        un = port.unlocode

        outbound_legs = [l for l in data.voyage_legs if l.from_port_unlocode == un]
        inbound_legs = [l for l in data.voyage_legs if l.to_port_unlocode == un]

        port_calls = []

        # Process Outbound Calls (Vessels departing or in transit holding here)
        for leg in outbound_legs:
            laden_teu = leg_laden_teu.get(leg.leg_id, 0.0)
            empty_teu = leg_empty_teu.get(leg.leg_id, 0.0)
            total_onboard = laden_teu + empty_teu
            free_space = max(0.0, leg.capacity_teu - total_onboard)
            util_pct = round((total_onboard / leg.capacity_teu) * 100, 1) if leg.capacity_teu > 0 else 0.0

            prior_inbound = next((inl for inl in inbound_legs if inl.voyage_number == leg.voyage_number and inl.arrival_day <= leg.departure_day), None)

            arr_day = prior_inbound.arrival_day if prior_inbound else None
            hold_days = (leg.departure_day - arr_day) if arr_day is not None else 0
            call_type = "INTERMEDIATE_TRANSIT_CALL" if prior_inbound else "ORIGIN_DEPARTURE"

            port_calls.append({
                "voyage_number": leg.voyage_number,
                "vessel_name": leg.vessel_name,
                "call_type": call_type,
                "arrival_day": arr_day,
                "departure_day": leg.departure_day,
                "berth_stay_duration_days": hold_days,
                "destination_port": leg.to_port_unlocode,
                "vessel_capacity_teu": leg.capacity_teu,
                "deadweight_capacity_mt": leg.capacity_weight_mt,
                "laden_bookings_teu": laden_teu,
                "laden_bookings_count": len(leg_laden_bookings.get(leg.leg_id, [])),
                "laden_bookings_list": leg_laden_bookings.get(leg.leg_id, []),
                "empty_reposition_teu": empty_teu,
                "empty_reposition_list": leg_empty_repositions.get(leg.leg_id, []),
                "total_onboard_teu": total_onboard,
                "remaining_free_teu": free_space,
                "utilization_pct": util_pct,
            })

        # Process Terminal Turnaround arrivals
        for in_leg in inbound_legs:
            has_next = any(outl.voyage_number == in_leg.voyage_number and outl.from_port_unlocode == un for outl in outbound_legs)
            if not has_next:
                laden_discharging = leg_laden_teu.get(in_leg.leg_id, 0.0)
                empty_discharging = leg_empty_teu.get(in_leg.leg_id, 0.0)
                port_calls.append({
                    "voyage_number": in_leg.voyage_number,
                    "vessel_name": in_leg.vessel_name,
                    "call_type": "TERMINAL_TURNAROUND_ARRIVAL",
                    "arrival_day": in_leg.arrival_day,
                    "departure_day": None,
                    "berth_stay_duration_days": 0,
                    "destination_port": "TURNAROUND",
                    "vessel_capacity_teu": in_leg.capacity_teu,
                    "deadweight_capacity_mt": in_leg.capacity_weight_mt,
                    "laden_bookings_teu": 0.0,
                    "laden_bookings_count": 0,
                    "laden_bookings_list": [],
                    "empty_reposition_teu": 0.0,
                    "empty_reposition_list": [],
                    "total_onboard_teu": 0.0,
                    "remaining_free_teu": in_leg.capacity_teu,
                    "utilization_pct": 0.0,
                    "inbound_discharging_laden_teu": laden_discharging,
                    "inbound_discharging_empty_teu": empty_discharging,
                })

        port_calls.sort(key=lambda c: (c["departure_day"] if c["departure_day"] is not None else c["arrival_day"] or 0))

        port_vessel_schedules.append({
            "port_unlocode": un,
            "port_name": port.name,
            "total_calls_count": len(port_calls),
            "vessel_calls": port_calls,
        })

    return {
        "total_days": len(history),
        "horizon_days": 40,
        "final_cumulative_cost": history[-1].cumulative_total_cost,
        "port_horizon_insights": port_insights,
        "port_vessel_schedules": port_vessel_schedules,
        "today_directives": {
            "empty_repositions": [
                {
                    "port_unlocode": erd.port_unlocode,
                    "port_name": erd.port_name,
                    "should_load_empties": erd.should_load_empties,
                    "voyage_number": erd.voyage_number,
                    "destination_port": erd.destination_port,
                    "total_reposition_teu": erd.total_reposition_teu,
                    "action_instruction": erd.action_instruction,
                }
                for erd in history[0].empty_reposition_directives
            ],
            "booking_dispatches": [
                {
                    "booking_id": bdd.booking_id,
                    "origin_port": bdd.origin_port,
                    "destination_port": bdd.destination_port,
                    "container_type": bdd.container_type,
                    "total_quantity": bdd.total_quantity,
                    "owned_quantity": bdd.owned_quantity,
                    "leased_quantity": bdd.leased_quantity,
                    "assigned_voyage": bdd.assigned_voyage,
                    "departure_day": bdd.departure_day,
                    "arrival_day": bdd.arrival_day,
                    "urgency": bdd.urgency,
                    "action_instruction": bdd.action_instruction,
                }
                for bdd in history[0].booking_dispatch_directives
            ],
        },
        "snapshots": [
            {
                "day": s.day,
                "date": s.simulation_date,
                "port_inventories": s.port_inventories,
                "port_safety_stocks": s.port_safety_stocks,
                "vessels": [
                    {
                        "vessel_name": v.vessel_name,
                        "current_port": v.current_port,
                        "in_transit": v.in_transit,
                        "from_port": v.from_port,
                        "to_port": v.to_port,
                        "departure_day": v.departure_day,
                        "arrival_day": v.arrival_day,
                        "progress_pct": round(v.progress_pct, 1),
                        "teu_load": v.teu_load,
                        "weight_load_mt": v.weight_load_mt,
                    }
                    for v in s.vessels
                ],
                "bookings": [
                    {
                        "booking_id": b.booking_id,
                        "origin": b.origin_unlocode,
                        "destination": b.destination_unlocode,
                        "container_type": b.container_type.value,
                        "quantity": b.quantity,
                        "priority": b.priority.value,
                        "status": b.status,
                        "voyage": b.assigned_voyage_number,
                        "departure_day": b.departure_day,
                        "arrival_day": b.expected_arrival_day,
                        "actual_delivery_day": b.actual_delivery_day,
                    }
                    for b in s.bookings
                ],
                "active_repositions": s.active_repositions,
                "port_action_summaries": [
                    {
                        "port_unlocode": pas.port_unlocode,
                        "port_name": pas.port_name,
                        "current_stock": pas.current_stock,
                        "total_stock_teu": pas.total_stock_teu,
                        "safety_stock_teu": pas.safety_stock_teu,
                        "safety_status": pas.safety_status,
                        "outbound_laden_units": pas.outbound_laden_units,
                        "empty_reposition_load_units": pas.empty_reposition_load_units,
                        "inbound_devanning_units": pas.inbound_devanning_units,
                        "leased_units": pas.leased_units,
                        "recommended_action": pas.recommended_action,
                    }
                    for pas in s.port_action_summaries
                ],
                "empty_reposition_directives": [
                    {
                        "port_unlocode": erd.port_unlocode,
                        "port_name": erd.port_name,
                        "has_departing_vessel": erd.has_departing_vessel,
                        "voyage_number": erd.voyage_number,
                        "leg_id": erd.leg_id,
                        "destination_port": erd.destination_port,
                        "should_load_empties": erd.should_load_empties,
                        "reposition_quantities": erd.reposition_quantities,
                        "total_reposition_teu": erd.total_reposition_teu,
                        "action_instruction": erd.action_instruction,
                    }
                    for erd in s.empty_reposition_directives
                ],
                "booking_dispatch_directives": [
                    {
                        "booking_id": bdd.booking_id,
                        "origin_port": bdd.origin_port,
                        "destination_port": bdd.destination_port,
                        "container_type": bdd.container_type,
                        "total_quantity": bdd.total_quantity,
                        "owned_quantity": bdd.owned_quantity,
                        "leased_quantity": bdd.leased_quantity,
                        "assigned_voyage": bdd.assigned_voyage,
                        "departure_day": bdd.departure_day,
                        "arrival_day": bdd.arrival_day,
                        "urgency": bdd.urgency,
                        "action_instruction": bdd.action_instruction,
                    }
                    for bdd in s.booking_dispatch_directives
                ],
                "daily_holding_cost": s.daily_holding_cost,
                "daily_repositioning_cost": s.daily_repositioning_cost,
                "daily_leasing_cost": s.daily_leasing_cost,
                "cumulative_total_cost": s.cumulative_total_cost,
                "alerts": s.alerts,
            }
            for s in history
        ],
    }


@router.get("/world-1/day/{day_number}")
def get_world_1_day_snapshot(day_number: int, db: Session = Depends(get_test_db)):
    """Retrieves the exact state snapshot of World 1 on a specific day (0 to 40) from cargo_pilot_test.db."""
    if day_number < 0 or day_number > 40:
        raise HTTPException(status_code=400, detail="Day number must be between 0 and 40")

    data = load_world_1_from_db(db)
    engine = DailySimulationEngine(data)
    engine.run_all()

    if day_number >= len(engine.history):
        raise HTTPException(status_code=404, detail="Snapshot not found")

    s = engine.history[day_number]
    return {
        "day": s.day,
        "date": s.simulation_date,
        "port_inventories": s.port_inventories,
        "port_safety_stocks": s.port_safety_stocks,
        "vessels": [
            {
                "vessel_name": v.vessel_name,
                "current_port": v.current_port,
                "in_transit": v.in_transit,
                "from_port": v.from_port,
                "to_port": v.to_port,
                "departure_day": v.departure_day,
                "arrival_day": v.arrival_day,
                "progress_pct": round(v.progress_pct, 1),
                "teu_load": v.teu_load,
                "weight_load_mt": v.weight_load_mt,
            }
            for v in s.vessels
        ],
        "bookings": [
            {
                "booking_id": b.booking_id,
                "origin": b.origin_unlocode,
                "destination": b.destination_unlocode,
                "container_type": b.container_type.value,
                "quantity": b.quantity,
                "priority": b.priority.value,
                "status": b.status,
                "voyage": b.assigned_voyage_number,
                "departure_day": b.departure_day,
                "arrival_day": b.expected_arrival_day,
            }
            for b in s.bookings
        ],
        "active_repositions": s.active_repositions,
        "port_action_summaries": [
            {
                "port_unlocode": pas.port_unlocode,
                "port_name": pas.port_name,
                "current_stock": pas.current_stock,
                "total_stock_teu": pas.total_stock_teu,
                "safety_stock_teu": pas.safety_stock_teu,
                "safety_status": pas.safety_status,
                "outbound_laden_units": pas.outbound_laden_units,
                "empty_reposition_load_units": pas.empty_reposition_load_units,
                "inbound_devanning_units": pas.inbound_devanning_units,
                "leased_units": pas.leased_units,
                "recommended_action": pas.recommended_action,
            }
            for pas in s.port_action_summaries
        ],
        "empty_reposition_directives": [
            {
                "port_unlocode": erd.port_unlocode,
                "port_name": erd.port_name,
                "has_departing_vessel": erd.has_departing_vessel,
                "voyage_number": erd.voyage_number,
                "leg_id": erd.leg_id,
                "destination_port": erd.destination_port,
                "should_load_empties": erd.should_load_empties,
                "reposition_quantities": erd.reposition_quantities,
                "total_reposition_teu": erd.total_reposition_teu,
                "action_instruction": erd.action_instruction,
            }
            for erd in s.empty_reposition_directives
        ],
        "booking_dispatch_directives": [
            {
                "booking_id": bdd.booking_id,
                "origin_port": bdd.origin_port,
                "destination_port": bdd.destination_port,
                "container_type": bdd.container_type,
                "total_quantity": bdd.total_quantity,
                "owned_quantity": bdd.owned_quantity,
                "leased_quantity": bdd.leased_quantity,
                "assigned_voyage": bdd.assigned_voyage,
                "departure_day": bdd.departure_day,
                "arrival_day": bdd.arrival_day,
                "urgency": bdd.urgency,
                "action_instruction": bdd.action_instruction,
            }
            for bdd in s.booking_dispatch_directives
        ],
        "daily_holding_cost": s.daily_holding_cost,
        "daily_repositioning_cost": s.daily_repositioning_cost,
        "daily_leasing_cost": s.daily_leasing_cost,
        "cumulative_total_cost": s.cumulative_total_cost,
        "alerts": s.alerts,
    }


# ============================================================
# WORLD 1 DATA VALIDATION ENDPOINT
# ============================================================

@router.get("/world-1/validate")
def validate_world_1():
    """
    Run the full CargoPilot data validation suite against the World 1 dataset.
    Returns a structured QA report with ERROR / WARNING / INFO issues.
    """
    data = get_world_1_dataset()
    report = CargoPilotValidator("world_1").validate(data)
    return report.to_dict()


# ============================================================
# WORLD 2 ENDPOINTS  —  55 Ports, 18 Vessels, 84-Day Horizon
# ============================================================


def _build_voyage_util(data, sol) -> List[Dict]:
    """Compute per-leg capacity breakdown from a solved MILPSolution."""
    leg_laden_teu: Dict[str, float] = {}
    leg_laden_mt:  Dict[str, float] = {}
    leg_empty_teu: Dict[str, float] = {}
    leg_empty_mt:  Dict[str, float] = {}

    booking_map = {b.booking_id: b for b in data.bookings}

    for bd in sol.booking_decisions:
        b = booking_map.get(bd.booking_id)
        if not b:
            continue
        c_spec = data.container_types[b.container_type]
        total = bd.owned_quantity + bd.leased_quantity
        for lid in bd.legs_traversed:
            leg_laden_teu[lid] = leg_laden_teu.get(lid, 0.0) + total * c_spec.teu_factor
            leg_laden_mt[lid]  = leg_laden_mt.get(lid,  0.0) + total * c_spec.total_laden_weight_mt

    for rd in sol.repositioning_decisions:
        c_spec = data.container_types[rd.container_type]
        leg_empty_teu[rd.leg_id] = leg_empty_teu.get(rd.leg_id, 0.0) + rd.quantity * c_spec.teu_factor
        leg_empty_mt[rd.leg_id]  = leg_empty_mt.get(rd.leg_id,  0.0) + rd.quantity * c_spec.tare_weight_mt

    voyages: Dict[str, Dict] = {}
    for leg in sorted(data.voyage_legs, key=lambda l: l.departure_day):
        vn = leg.voyage_number
        if vn not in voyages:
            voyages[vn] = {
                "voyage_number": vn,
                "vessel_name":   leg.vessel_name,
                "service_code":  "_".join(vn.split("_")[1:-1]),   # VOY_AEX1_R2 → AEX1
                "rotation":      vn.split("_")[-1],               # R1, R2, …
                "legs": [],
            }
        laden_teu    = round(leg_laden_teu.get(leg.leg_id, 0.0), 1)
        empty_teu    = round(leg_empty_teu.get(leg.leg_id, 0.0), 1)
        pre_teu      = float(leg.booked_capacity_teu)
        used_teu     = laden_teu + empty_teu + pre_teu
        free_teu     = max(0.0, leg.capacity_teu - used_teu)

        laden_mt     = round(leg_laden_mt.get(leg.leg_id, 0.0), 1)
        empty_mt     = round(leg_empty_mt.get(leg.leg_id, 0.0), 1)
        pre_mt       = float(leg.booked_weight_mt)
        used_mt      = laden_mt + empty_mt + pre_mt
        free_mt      = max(0.0, leg.capacity_weight_mt - used_mt)

        util_pct     = round(used_teu / leg.capacity_teu * 100, 1) if leg.capacity_teu else 0.0
        wt_pct       = round(used_mt  / leg.capacity_weight_mt * 100, 1) if leg.capacity_weight_mt else 0.0

        voyages[vn]["legs"].append({
            "leg_id":              leg.leg_id,
            "from_port":           leg.from_port_unlocode,
            "to_port":             leg.to_port_unlocode,
            "departure_day":       leg.departure_day,
            "arrival_day":         leg.arrival_day,
            "transit_days":        leg.transit_days,
            # TEU breakdown
            "capacity_teu":        leg.capacity_teu,
            "pre_booked_teu":      pre_teu,
            "laden_booking_teu":   laden_teu,
            "empty_reposition_teu": empty_teu,
            "total_used_teu":      round(used_teu, 1),
            "free_teu":            round(free_teu, 1),
            "utilization_pct":     util_pct,
            # Weight breakdown (MT)
            "capacity_mt":         leg.capacity_weight_mt,
            "pre_booked_mt":       pre_mt,
            "laden_booking_mt":    laden_mt,
            "empty_reposition_mt": empty_mt,
            "total_used_mt":       round(used_mt, 1),
            "free_mt":             round(free_mt, 1),
            "weight_utilization_pct": wt_pct,
        })
    return list(voyages.values())



@router.get("/world-2/validate")
def validate_world_2():
    """
    Run the full CargoPilot data validation suite against World 2 (55-port, 84-day).
    Returns a structured QA report with ERROR / WARNING / INFO issues across:
    bookings, vessels, voyages, ports, inventory, costs, network, and demand forecasts.
    """
    data = get_world_2_dataset()
    report = CargoPilotValidator("world_2").validate(data)
    return report.to_dict()


@router.get("/world-2/voyages")
def get_world_2_voyages():
    """
    Returns all 67 voyages (18 services × recurring rotations) with per-leg capacity info.
    Before solving: shows raw fixture capacity and pre-booked (3rd-party) slots.
    Use POST /world-2/solve-milp to get laden/empty/free breakdown post-optimisation.
    """
    data = get_world_2_dataset()
    voyages: Dict[str, Dict] = {}
    for leg in sorted(data.voyage_legs, key=lambda l: l.departure_day):
        vn = leg.voyage_number
        if vn not in voyages:
            voyages[vn] = {
                "voyage_number": vn,
                "vessel_name":   leg.vessel_name,
                "service_code":  "_".join(vn.split("_")[1:-1]),
                "rotation":      vn.split("_")[-1],
                "capacity_teu":  leg.capacity_teu,
                "capacity_mt":   leg.capacity_weight_mt,
                "legs": [],
            }
        pre_teu = float(leg.booked_capacity_teu)
        pre_mt  = float(leg.booked_weight_mt)
        voyages[vn]["legs"].append({
            "leg_id":               leg.leg_id,
            "from_port":            leg.from_port_unlocode,
            "to_port":              leg.to_port_unlocode,
            "departure_day":        leg.departure_day,
            "arrival_day":          leg.arrival_day,
            "transit_days":         leg.transit_days,
            "capacity_teu":         leg.capacity_teu,
            "capacity_mt":          leg.capacity_weight_mt,
            "pre_booked_teu":       pre_teu,
            "pre_booked_mt":        pre_mt,
            "available_teu":        leg.capacity_teu - pre_teu,
            "available_mt":         leg.capacity_weight_mt - pre_mt,
            "pre_utilization_pct":  round(pre_teu / leg.capacity_teu * 100, 1) if leg.capacity_teu else 0.0,
            # Post-solve fields (null until solver runs)
            "laden_booking_teu":    None,
            "empty_reposition_teu": None,
            "free_teu":             None,
            "utilization_pct":      None,
            "laden_booking_mt":     None,
            "empty_reposition_mt":  None,
            "free_mt":              None,
            "weight_utilization_pct": None,
        })
    return {
        "status": "pre_solve",
        "total_voyages": len(voyages),
        "total_legs": len(data.voyage_legs),
        "voyages": list(voyages.values()),
    }


@router.get("/world-2/summary")
def get_world_2_summary():
    """Returns the full World 2 fixture summary (55 ports, 18 vessels, 349 legs, 193 bookings)."""
    data = get_world_2_dataset()
    ctypes = list(data.container_types.keys())

    # Aggregate voyages and rotation info
    voyages: Dict[str, Dict] = {}
    for leg in data.voyage_legs:
        vn = leg.voyage_number
        if vn not in voyages:
            voyages[vn] = {
                "voyage_number": vn,
                "vessel_name": leg.vessel_name,
                "service_code": "_".join(vn.split("_")[1:3]),  # e.g. AEX1_R1 → AEX1
                "legs": [],
            }
        voyages[vn]["legs"].append({
            "leg_id": leg.leg_id,
            "from_port": leg.from_port_unlocode,
            "to_port": leg.to_port_unlocode,
            "departure_day": leg.departure_day,
            "arrival_day": leg.arrival_day,
            "transit_days": leg.transit_days,
            "capacity_teu": leg.capacity_teu,
        })

    return {
        "world_id": "WORLD-02",
        "name": "Full-Scale Global MILP Benchmark (55 Ports, 18 Vessels, 84 Days)",
        "horizon_days": data.horizon_days,
        "base_date": str(data.base_date),
        "scale": {
            "ports": len(data.ports),
            "vessels": len(data.vessels),
            "container_types": len(data.container_types),
            "voyage_legs": len(data.voyage_legs),
            "unique_voyages": len(voyages),
            "bookings": len(data.bookings),
        },
        "new_milp_features": {
            "demand_forecast_entries": len(data.demand_forecast),
            "return_forecast_entries": len(data.return_forecast),
            "in_transit_pipeline_entries": sum(1 for v in data.in_transit_pipeline.values() if v > 0),
            "precomputed_safety_stocks": len(data.safety_stocks),
            "historical_weeks": 12,
            "historical_records": len(data.historical_demand),
            "lease_cap_short_entries": len(data.lease_cap_short),
            "storage_capacity_entries": len(data.storage_capacity),
        },
        "equation_families_active": 20,
        "ports": [
            {
                "unlocode": p.unlocode,
                "name": p.name,
                "country": p.country,
                "region": p.region,
                "latitude": p.latitude,
                "longitude": p.longitude,
                "storage_capacity_teu": p.storage_capacity_teu,
                "safety_stock_teu": p.safety_stock_teu,
                "devanning_lead_time_days": p.devanning_lead_time_days,
                "lift_on_cost": p.lift_on_cost,
                "lift_off_cost": p.lift_off_cost,
            }
            for p in data.ports.values()
        ],
        "vessels": [
            {
                "imo_number": v.imo_number,
                "name": v.name,
                "vessel_type": v.vessel_type.value,
                "capacity_teu": v.container_capacity_teu,
                "deadweight_mt": v.deadweight_capacity_mt,
                "reefer_plugs": v.reefer_plugs,
            }
            for v in data.vessels
        ],
        "voyages": list(voyages.values()),
        "bookings": [
            {
                "booking_id": b.booking_id,
                "origin": b.origin_unlocode,
                "destination": b.destination_unlocode,
                "container_type": b.container_type.value,
                "quantity": b.quantity,
                "cargo_ready_day": b.cargo_ready_day,
                "cutoff_day": b.cutoff_day,
                "delivery_deadline_day": b.delivery_deadline_day,
                "priority": b.priority.value,
                "cargo_weight_mt": b.cargo_weight_mt,
            }
            for b in data.bookings
        ],
        "cost_parameters": {
            "short_term_leasing_sample": {
                f"{p}_{k.value}": v
                for (p, k), v in list(data.leasing_costs.items())[:10]
            },
            "long_term_leasing_sample": {
                f"{p}_{k.value}": v
                for (p, k), v in list(data.leasing_costs_long.items())[:10]
            },
            "holding_costs_sample": {
                f"{p}_{k.value}": v
                for (p, k), v in list(data.holding_costs.items())[:10]
            },
            "shortage_penalties": {
                prio.value: pen for prio, pen in data.shortage_penalties.items()
            },
        },
        "forecast_sample": {
            "demand_D_CNSHA_40DC_day10": data.demand_forecast.get(
                ("CNSHA", ContainerType.DRY_40FT, 10), None
            ),
            "return_R_CNSHA_40DC_day31": data.return_forecast.get(
                ("CNSHA", ContainerType.DRY_40FT, 31), None
            ),
            "safety_stock_SS_CNSHA_40DC_day0": data.safety_stocks.get(
                ("CNSHA", ContainerType.DRY_40FT, 0), None
            ),
            "in_transit_G_NLRTM_40HC_day5": data.in_transit_pipeline.get(
                ("NLRTM", ContainerType.HIGH_CUBE_40FT, 5), None
            ),
        },
        "historical_sample": {
            "hist_demand_CNSHA_40DC_week_neg12": data.historical_demand.get(
                ("CNSHA", ContainerType.DRY_40FT, -84), None
            ),
            "hist_inv_NLRTM_40HC_week_neg4": data.historical_inventory.get(
                ("NLRTM", ContainerType.HIGH_CUBE_40FT, -28), None
            ),
        },
    }


@router.post("/world-2/solve-milp")
def solve_world_2_milp(time_limit: int = 120):
    """
    Runs the full 20-equation-family MILP on World 2 data.
    Returns optimal decisions including long-term leasing, delay variables,
    handling costs, and all new World 2 cost terms.
    Warning: With 55 ports × 193 bookings, allow 60–120s for solve.
    """
    data = get_world_2_dataset()
    solver = CargoPilotMILPSolver(data)
    sol = solver.solve(time_limit_seconds=float(time_limit))

    return {
        "solver_name": sol.solver_name,
        "solver_status": sol.solver_status,
        "optimality_gap": sol.optimality_gap,
        "objective_value": sol.objective_value,
        "best_bound": sol.best_bound,
        "solve_time_seconds": sol.solve_time_seconds,
        "num_variables": sol.num_variables,
        "num_constraints": sol.num_constraints,
        "num_integer_variables": sol.num_integer_variables,
        "world_2_active": True,
        "equation_families": 20,
        "cost_breakdown": {
            "repositioning_cost":     sol.total_repositioning_cost,
            "leasing_short_cost":     sol.total_leasing_short_cost,
            "leasing_long_cost":      sol.total_leasing_long_cost,
            "holding_cost":           sol.total_holding_cost,
            "handling_cost":          sol.total_handling_cost,
            "delay_penalty":          sol.total_delay_penalty,
            "shortage_penalty":       sol.total_shortage_penalty,
            "safety_stock_penalty":   sol.total_safety_stock_penalty,
        },
        "booking_decisions": [
            {
                "booking_id":      bd.booking_id,
                "path_id":         bd.selected_path_id,
                "container_type":  bd.container_type.value,
                "owned_qty":       bd.owned_quantity,
                "leased_qty":      bd.leased_quantity,
                "unserved_qty":    bd.unserved_quantity,
                "legs":            bd.legs_traversed,
                "departure_day":   bd.departure_day,
                "arrival_day":     bd.arrival_day,
                "delay_days":      bd.delay_days,
                "cost":            bd.fulfillment_cost,
            }
            for bd in sol.booking_decisions
        ],
        "repositioning_decisions": [
            {
                "leg_id":          rd.leg_id,
                "voyage_number":   rd.voyage_number,
                "from_port":       rd.from_port,
                "to_port":         rd.to_port,
                "departure_day":   rd.departure_day,
                "arrival_day":     rd.arrival_day,
                "container_type":  rd.container_type.value,
                "quantity":        rd.quantity,
                "cost":            rd.cost,
            }
            for rd in sol.repositioning_decisions
        ],
        "long_lease_decisions": [
            {
                "port":            ll.port_unlocode,
                "container_type":  ll.container_type.value,
                "day":             ll.day,
                "quantity":        ll.quantity,
                "cost":            ll.cost,
            }
            for ll in sol.long_lease_decisions
        ],
        "summary": {
            "bookings_fully_served": sum(
                1 for bd in sol.booking_decisions if bd.unserved_quantity == 0
            ),
            "bookings_partial":  sum(
                1 for bd in sol.booking_decisions if bd.unserved_quantity > 0
            ),
            "total_repositioning_moves": len(sol.repositioning_decisions),
            "total_long_lease_injections": len(sol.long_lease_decisions),
            "delayed_bookings": sum(
                1 for bd in sol.booking_decisions if bd.delay_days > 0.5
            ),
        },
        "voyage_utilization": _build_voyage_util(data, sol),
    }
