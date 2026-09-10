"""
CargoPilot Planning & Optimization Engine
==========================================
Coupled Multi-Commodity MILP Engine for Discrete-Event Simulation World 1.

Formulates and solves the operational logistics optimization problem:
  - Joint booking-to-container and booking-to-voyage allocation
  - Strict 7-day departure cutoff horizon enforcement via fixed equality constraints
  - Empty container repositioning from surplus to deficit ports
  - Equipment leasing with explicit capacity and allocation linkage
  - Net vessel slot TEU capacity constraints accounting for pre-existing loads
  - Multi-container quantity tracking (Q_b >= 1)
  - Pure operational cost minimization objective
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import pulp

from app.world.world_state import (
    AllocationState,
    BookingState,
    ContainerState,
    EquipmentBalance,
    LeaseState,
    RepositioningState,
    VoyageState,
    WorldState,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Report Data Structures
# ---------------------------------------------------------------------------

@dataclass
class SolverResult:
    status: str                         # OPTIMAL | FEASIBLE | INFEASIBLE | TIME_LIMIT | ERROR
    objective_value: float
    solve_time_seconds: float
    num_variables: int
    num_constraints: int
    num_integer_variables: int
    solver_name: str = "PuLP-CBC"
    message: str = ""


@dataclass
class PreservedBookingRecord:
    booking_id: str
    origin_port_id: str
    destination_port_id: str
    equipment_type: str
    quantity: int
    scheduled_departure: str
    cutoff_time: str
    hours_to_departure: float
    assigned_voyage_id: Optional[str]
    assigned_containers: List[str]
    status: str                        # LOCKED | FROZEN_UNALLOCATED_EXCEPTION
    compliance_reason: str


@dataclass
class BookingAllocationDecision:
    booking_id: str
    origin_port_id: str
    destination_port_id: str
    equipment_type: str
    required_quantity: int
    allocated_quantity: int
    unallocated_quantity: int
    assigned_containers: List[str]
    assigned_voyage_id: str
    vessel_name: str
    departure_time: str
    arrival_time: str
    fulfillment_cost: float


@dataclass
class RepositioningDecision:
    order_id: str
    from_port_id: str
    to_port_id: str
    equipment_type: str
    quantity: int
    voyage_id: str
    departure_time: str
    arrival_time: str
    estimated_cost: float


@dataclass
class LeasingDecision:
    lease_id: str
    location_id: str
    equipment_type: str
    quantity: int
    daily_rate: float
    duration_days: float
    estimated_cost: float


@dataclass
class OperationalCostLedger:
    terminal_handling_cost: float = 0.0
    repositioning_cost: float = 0.0
    leasing_cost: float = 0.0
    unserved_demand_penalty: float = 0.0
    shortage_penalty: float = 0.0

    @property
    def total_operational_cost(self) -> float:
        return (
            self.terminal_handling_cost
            + self.repositioning_cost
            + self.leasing_cost
            + self.unserved_demand_penalty
            + self.shortage_penalty
        )


@dataclass
class OptimizationImpact:
    total_bookings_evaluated: int = 0
    bookings_allocated: int = 0
    bookings_unserved: int = 0
    teu_allocated: float = 0.0
    containers_allocated: int = 0
    locked_bookings_preserved: int = 0
    exceptions_preserved: int = 0
    repositioning_moves: int = 0
    repositioning_teu: float = 0.0
    leased_containers: int = 0
    unserved_demand_teu: float = 0.0
    costs: OperationalCostLedger = field(default_factory=OperationalCostLedger)


@dataclass
class OptimizationReport:
    world_id: str
    simulation_time: str
    execution_timestamp: str
    solver_result: SolverResult
    preserved_decisions: List[PreservedBookingRecord] = field(default_factory=list)
    booking_allocations: List[BookingAllocationDecision] = field(default_factory=list)
    repositioning_directives: List[RepositioningDecision] = field(default_factory=list)
    leasing_directives: List[LeasingDecision] = field(default_factory=list)
    impact: OptimizationImpact = field(default_factory=OptimizationImpact)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "world_id": self.world_id,
            "simulation_time": self.simulation_time,
            "execution_timestamp": self.execution_timestamp,
            "solver_result": {
                "status": self.solver_result.status,
                "objective_value": round(self.solver_result.objective_value, 2),
                "solve_time_seconds": round(self.solver_result.solve_time_seconds, 3),
                "num_variables": self.solver_result.num_variables,
                "num_constraints": self.solver_result.num_constraints,
                "num_integer_variables": self.solver_result.num_integer_variables,
                "solver_name": self.solver_result.solver_name,
                "message": self.solver_result.message,
            },
            "preserved_decisions": [
                {
                    "booking_id": p.booking_id,
                    "origin_port_id": p.origin_port_id,
                    "destination_port_id": p.destination_port_id,
                    "equipment_type": p.equipment_type,
                    "quantity": p.quantity,
                    "scheduled_departure": p.scheduled_departure,
                    "cutoff_time": p.cutoff_time,
                    "hours_to_departure": round(p.hours_to_departure, 1),
                    "assigned_voyage_id": p.assigned_voyage_id,
                    "assigned_containers": p.assigned_containers,
                    "status": p.status,
                    "compliance_reason": p.compliance_reason,
                }
                for p in self.preserved_decisions
            ],
            "booking_allocations": [
                {
                    "booking_id": a.booking_id,
                    "origin_port_id": a.origin_port_id,
                    "destination_port_id": a.destination_port_id,
                    "equipment_type": a.equipment_type,
                    "required_quantity": a.required_quantity,
                    "allocated_quantity": a.allocated_quantity,
                    "unallocated_quantity": a.unallocated_quantity,
                    "assigned_containers": a.assigned_containers,
                    "assigned_voyage_id": a.assigned_voyage_id,
                    "vessel_name": a.vessel_name,
                    "departure_time": a.departure_time,
                    "arrival_time": a.arrival_time,
                    "fulfillment_cost": round(a.fulfillment_cost, 2),
                }
                for a in self.booking_allocations
            ],
            "repositioning_directives": [
                {
                    "order_id": r.order_id,
                    "from_port_id": r.from_port_id,
                    "to_port_id": r.to_port_id,
                    "equipment_type": r.equipment_type,
                    "quantity": r.quantity,
                    "voyage_id": r.voyage_id,
                    "departure_time": r.departure_time,
                    "arrival_time": r.arrival_time,
                    "estimated_cost": round(r.estimated_cost, 2),
                }
                for r in self.repositioning_directives
            ],
            "leasing_directives": [
                {
                    "lease_id": l.lease_id,
                    "location_id": l.location_id,
                    "equipment_type": l.equipment_type,
                    "quantity": l.quantity,
                    "daily_rate": round(l.daily_rate, 2),
                    "duration_days": l.duration_days,
                    "estimated_cost": round(l.estimated_cost, 2),
                }
                for l in self.leasing_directives
            ],
            "impact": {
                "total_bookings_evaluated": self.impact.total_bookings_evaluated,
                "bookings_allocated": self.impact.bookings_allocated,
                "bookings_unserved": self.impact.bookings_unserved,
                "teu_allocated": round(self.impact.teu_allocated, 1),
                "containers_allocated": self.impact.containers_allocated,
                "locked_bookings_preserved": self.impact.locked_bookings_preserved,
                "exceptions_preserved": self.impact.exceptions_preserved,
                "repositioning_moves": self.impact.repositioning_moves,
                "repositioning_teu": round(self.impact.repositioning_teu, 1),
                "leased_containers": self.impact.leased_containers,
                "unserved_demand_teu": round(self.impact.unserved_demand_teu, 1),
                "costs": {
                    "terminal_handling_cost": round(self.impact.costs.terminal_handling_cost, 2),
                    "repositioning_cost": round(self.impact.costs.repositioning_cost, 2),
                    "leasing_cost": round(self.impact.costs.leasing_cost, 2),
                    "unserved_demand_penalty": round(self.impact.costs.unserved_demand_penalty, 2),
                    "shortage_penalty": round(self.impact.costs.shortage_penalty, 2),
                    "total_operational_cost": round(self.impact.costs.total_operational_cost, 2),
                },
            },
        }


# ---------------------------------------------------------------------------
# Planning Engine
# ---------------------------------------------------------------------------

class CargoPilotPlanningEngine:
    """
    MILP-based joint optimization engine for discrete-event simulation world state.
    """

    COST_HANDLING_PER_CONTAINER: float = 150.0
    COST_REPOSITIONING_PER_CONTAINER: float = 350.0
    COST_LEASE_PER_CONTAINER: float = 450.0
    COST_UNSERVED_PER_CONTAINER: float = 3500.0
    MAX_LEASE_PER_PORT: int = 250

    def __init__(self, state: WorldState, registry: Optional[Any] = None):
        self.state = state
        self.registry = registry
        self.t_sim = state.simulation_time

    def optimize(self, time_limit_seconds: float = 30.0) -> OptimizationReport:
        """
        Formulate and solve the MILP optimization model against self.state.
        """
        start_wall_time = time.perf_counter()
        report_timestamp = datetime.now(timezone.utc).isoformat()

        # -------------------------------------------------------------------
        # 1. Horizon Partitioning & Locked Horizon Classification
        # -------------------------------------------------------------------
        cutoff_delta = timedelta(hours=168)  # Exactly 7 days (Doc 2 §9.4)

        b_locked: List[BookingState] = []
        b_exceptions: List[BookingState] = []
        b_opt: List[BookingState] = []

        preserved_records: List[PreservedBookingRecord] = []

        # Find assigned containers for each booking from existing allocations
        containers_by_booking: Dict[str, List[str]] = {}
        for alloc in self.state.allocations.values():
            containers_by_booking.setdefault(alloc.booking_id, []).append(alloc.container_id)

        for b in self.state.bookings.values():
            dep_time = self._estimate_departure_time(b)
            time_to_dep = dep_time - self.t_sim
            is_inside_7d = time_to_dep <= cutoff_delta

            if is_inside_7d:
                has_allocation = (
                    b.status in ("ALLOCATED", "LOCKED")
                    or b.booking_id in containers_by_booking
                    or b.voyage_id is not None
                )
                if has_allocation:
                    b_locked.append(b)
                    preserved_records.append(
                        PreservedBookingRecord(
                            booking_id=b.booking_id,
                            origin_port_id=b.origin_port_id,
                            destination_port_id=b.destination_port_id,
                            equipment_type=b.equipment_type,
                            quantity=b.quantity,
                            scheduled_departure=dep_time.isoformat(),
                            cutoff_time=(b.cutoff_time or (dep_time - timedelta(days=7))).isoformat(),
                            hours_to_departure=time_to_dep.total_seconds() / 3600.0,
                            assigned_voyage_id=b.voyage_id,
                            assigned_containers=containers_by_booking.get(b.booking_id, []),
                            status="LOCKED",
                            compliance_reason="Departure within 7-day cutoff (<=168h) - locked by rule Doc 2 §9.4; preserved as fixed equality constraint.",
                        )
                    )
                else:
                    # Inside 7 days without allocation -> operational freeze exception
                    b_exceptions.append(b)
                    preserved_records.append(
                        PreservedBookingRecord(
                            booking_id=b.booking_id,
                            origin_port_id=b.origin_port_id,
                            destination_port_id=b.destination_port_id,
                            equipment_type=b.equipment_type,
                            quantity=b.quantity,
                            scheduled_departure=dep_time.isoformat(),
                            cutoff_time=(b.cutoff_time or (dep_time - timedelta(days=7))).isoformat(),
                            hours_to_departure=time_to_dep.total_seconds() / 3600.0,
                            assigned_voyage_id=None,
                            assigned_containers=[],
                            status="FROZEN_UNALLOCATED_EXCEPTION",
                            compliance_reason="Unallocated inside 7-day cutoff window (<=168h) - barred from solver optimization per operational freeze rule.",
                        )
                    )
            else:
                # Outside 7-day window -> eligible for MILP decision making
                b_opt.append(b)

        # -------------------------------------------------------------------
        # 2. Available Container Inventory per (Port, Type)
        # -------------------------------------------------------------------
        empty_containers: Dict[Tuple[str, str], List[str]] = {}
        for c in self.state.containers.values():
            if c.status == "EMPTY_AVAILABLE" and c.condition == "GOOD" and c.current_location_id:
                empty_containers.setdefault((c.current_location_id, c.equipment_type), []).append(c.container_id)

        # -------------------------------------------------------------------
        # 3. Initial Committed Voyage Loads & Net Slot Capacity
        # -------------------------------------------------------------------
        # Initial load = active loaded TEU on transit vessels + pre-existing locked allocations
        initial_voyage_load: Dict[str, float] = {}
        for v in self.state.voyages.values():
            vessel = self.state.vessels.get(v.vessel_id)
            load = 0.0
            if vessel and vessel.status == "IN_TRANSIT" and vessel.current_voyage_id == v.voyage_id:
                load += vessel.current_load_teu
            initial_voyage_load[v.voyage_id] = load

        # Add locked booking loads
        for b in b_locked:
            if b.voyage_id and b.voyage_id in initial_voyage_load:
                teu_mult = 1.0 if b.equipment_type == "20DC" else 2.0
                initial_voyage_load[b.voyage_id] += teu_mult * b.quantity

        net_voyage_capacity: Dict[str, float] = {
            v.voyage_id: max(0.0, v.capacity_teu - initial_voyage_load.get(v.voyage_id, 0.0))
            for v in self.state.voyages.values()
        }

        # -------------------------------------------------------------------
        # 4. Identify Candidate Voyages per Booking
        # -------------------------------------------------------------------
        candidate_voyages_by_b: Dict[str, List[VoyageState]] = {}
        for b in b_opt:
            cands = [
                v for v in self.state.voyages.values()
                if v.origin_port_id == b.origin_port_id
                and v.destination_port_id == b.destination_port_id
                and v.scheduled_departure >= self.t_sim + cutoff_delta
                and v.scheduled_departure >= b.cargo_ready_time - timedelta(hours=24)
            ]
            # Sort by departure time
            cands.sort(key=lambda x: x.scheduled_departure)
            candidate_voyages_by_b[b.booking_id] = cands

        # -------------------------------------------------------------------
        # 5. Build PuLP MILP Model
        # -------------------------------------------------------------------
        model = pulp.LpProblem("CargoPilot_Simulation_Planning", pulp.LpMinimize)

        # Decision Variables
        # Y_own[b, v]: owned containers allocated to booking b on voyage v
        # L_lease[b, v]: leased containers allocated to booking b on voyage v
        # U[b]: unserved booking quantity
        Y_own: Dict[Tuple[str, str], pulp.LpVariable] = {}
        L_lease: Dict[Tuple[str, str], pulp.LpVariable] = {}
        U_unserved: Dict[str, pulp.LpVariable] = {}

        for b in b_opt:
            U_unserved[b.booking_id] = pulp.LpVariable(
                f"U_{b.booking_id.replace('-', '_')}",
                lowBound=0,
                upBound=b.quantity,
                cat=pulp.LpInteger,
            )
            for v in candidate_voyages_by_b[b.booking_id]:
                key = (b.booking_id, v.voyage_id)
                var_suffix = f"{b.booking_id}_{v.voyage_id}".replace("-", "_")
                Y_own[key] = pulp.LpVariable(
                    f"Yown_{var_suffix}",
                    lowBound=0,
                    upBound=b.quantity,
                    cat=pulp.LpInteger,
                )
                L_lease[key] = pulp.LpVariable(
                    f"Llease_{var_suffix}",
                    lowBound=0,
                    upBound=b.quantity,
                    cat=pulp.LpInteger,
                )

        # Fixed equality variables for b_locked (exact mathematical preservation)
        for b in b_locked:
            if b.voyage_id:
                key = (b.booking_id, b.voyage_id)
                var_suffix = f"locked_{b.booking_id}_{b.voyage_id}".replace("-", "_")
                y_fixed = pulp.LpVariable(
                    f"Yfix_{var_suffix}",
                    lowBound=b.quantity,
                    upBound=b.quantity,
                    cat=pulp.LpInteger,
                )
                Y_own[key] = y_fixed
                # Demand satisfaction for locked is exact: Y_own == b.quantity
                model += (y_fixed == b.quantity, f"FixedAlloc_{var_suffix}")

        # X_repo[v, k]: empty repositioning units on voyage v of type k
        X_repo: Dict[Tuple[str, str], pulp.LpVariable] = {}
        eq_types = ["20DC", "40DC", "40HC"]

        scheduled_future_voyages = [
            v for v in self.state.voyages.values()
            if v.scheduled_departure >= self.t_sim
        ]

        for v in scheduled_future_voyages:
            for k in eq_types:
                key = (v.voyage_id, k)
                X_repo[key] = pulp.LpVariable(
                    f"Xrepo_{v.voyage_id.replace('-', '_')}_{k}",
                    lowBound=0,
                    cat=pulp.LpInteger,
                )

        # LeaseOrder[p, k]: total direct equipment lease orders executed at port p
        LeaseOrder: Dict[Tuple[str, str], pulp.LpVariable] = {}
        for port_id in self.state.ports.keys():
            for k in eq_types:
                key = (port_id, k)
                LeaseOrder[key] = pulp.LpVariable(
                    f"LeaseOrd_{port_id}_{k}",
                    lowBound=0,
                    upBound=self.MAX_LEASE_PER_PORT,
                    cat=pulp.LpInteger,
                )

        # -------------------------------------------------------------------
        # 6. Constraints
        # -------------------------------------------------------------------

        # (a) Demand Fulfillment for B_opt
        for b in b_opt:
            cands = candidate_voyages_by_b[b.booking_id]
            if cands:
                fulfillment_terms = [
                    Y_own[(b.booking_id, v.voyage_id)] + L_lease[(b.booking_id, v.voyage_id)]
                    for v in cands
                ]
                model += (
                    pulp.lpSum(fulfillment_terms) + U_unserved[b.booking_id] == b.quantity,
                    f"Demand_{b.booking_id.replace('-', '_')}",
                )
            else:
                # No candidate voyages available; must be unserved
                model += (
                    U_unserved[b.booking_id] == b.quantity,
                    f"DemandNoCand_{b.booking_id.replace('-', '_')}",
                )

        # (b) Origin Equipment Inventory Bound (for EMPTY_AVAILABLE containers)
        for (port_id, eq_type), c_list in empty_containers.items():
            avail_count = len(c_list)
            # Sum of owned allocations from this port
            b_terms = [
                Y_own[(b.booking_id, v.voyage_id)]
                for b in b_opt
                if b.origin_port_id == port_id and b.equipment_type == eq_type
                for v in candidate_voyages_by_b[b.booking_id]
                if (b.booking_id, v.voyage_id) in Y_own
            ]
            # Sum of empty repositioning departing from this port
            repo_terms = [
                X_repo[(v.voyage_id, eq_type)]
                for v in scheduled_future_voyages
                if v.origin_port_id == port_id and (v.voyage_id, eq_type) in X_repo
            ]
            if b_terms or repo_terms:
                model += (
                    pulp.lpSum(b_terms) + pulp.lpSum(repo_terms) <= avail_count,
                    f"AvailInv_{port_id}_{eq_type}",
                )

        # (c) Leased Equipment Linkage & Availability
        # Total leased containers assigned to bookings from port p must not exceed LeaseOrder[p, k]
        for port_id in self.state.ports.keys():
            for eq_type in eq_types:
                lease_alloc_terms = [
                    L_lease[(b.booking_id, v.voyage_id)]
                    for b in b_opt
                    if b.origin_port_id == port_id and b.equipment_type == eq_type
                    for v in candidate_voyages_by_b[b.booking_id]
                    if (b.booking_id, v.voyage_id) in L_lease
                ]
                if lease_alloc_terms:
                    model += (
                        pulp.lpSum(lease_alloc_terms) <= LeaseOrder[(port_id, eq_type)],
                        f"LeaseLink_{port_id}_{eq_type}",
                    )

        # (d) Net Vessel Slot TEU Capacity Constraint
        for v in scheduled_future_voyages:
            net_cap = net_voyage_capacity.get(v.voyage_id, v.capacity_teu)
            # Find all bookings that could be assigned to voyage v
            voyage_b_terms = []
            for b in b_opt:
                if v in candidate_voyages_by_b.get(b.booking_id, []):
                    teu_mult = 1.0 if b.equipment_type == "20DC" else 2.0
                    key = (b.booking_id, v.voyage_id)
                    voyage_b_terms.append(teu_mult * (Y_own[key] + L_lease[key]))

            repo_teu_terms = [
                (1.0 if k == "20DC" else 2.0) * X_repo[(v.voyage_id, k)]
                for k in eq_types
                if (v.voyage_id, k) in X_repo
            ]

            if voyage_b_terms or repo_teu_terms:
                model += (
                    pulp.lpSum(voyage_b_terms) + pulp.lpSum(repo_teu_terms) <= net_cap,
                    f"VesselCap_{v.voyage_id.replace('-', '_')}",
                )

        # (e) Repositioning Surplus Flow Limit (cannot reposition more than port surplus)
        for port_id in self.state.ports.keys():
            for eq_type in eq_types:
                avail = len(empty_containers.get((port_id, eq_type), []))
                eq_bal = self.state.equipment.get((port_id, eq_type))
                target = eq_bal.target if eq_bal else 50
                surplus = max(0, avail - target)
                port_repo_terms = [
                    X_repo[(v.voyage_id, eq_type)]
                    for v in scheduled_future_voyages
                    if v.origin_port_id == port_id and (v.voyage_id, eq_type) in X_repo
                ]
                if port_repo_terms:
                    model += (
                        pulp.lpSum(port_repo_terms) <= surplus,
                        f"SurplusRepoLimit_{port_id}_{eq_type}",
                    )

        # -------------------------------------------------------------------
        # 7. Operational Cost Minimization Objective
        # -------------------------------------------------------------------
        cost_objective = []

        # Terminal handling cost
        for key, var in Y_own.items():
            if not key[0].startswith("BKG-"):
                continue
            # Exclude locked fixed variables from optimization penalty
            if any(b.booking_id == key[0] for b in b_locked):
                continue
            cost_objective.append(self.COST_HANDLING_PER_CONTAINER * var)

        for key, var in L_lease.items():
            cost_objective.append(self.COST_HANDLING_PER_CONTAINER * var)

        # Repositioning move costs
        for key, var in X_repo.items():
            cost_objective.append(self.COST_REPOSITIONING_PER_CONTAINER * var)

        # Direct leasing costs
        for key, var in LeaseOrder.items():
            cost_objective.append(self.COST_LEASE_PER_CONTAINER * var)

        # Unserved demand penalties
        for b_id, var in U_unserved.items():
            cost_objective.append(self.COST_UNSERVED_PER_CONTAINER * var)

        model += pulp.lpSum(cost_objective), "Total_Operational_Cost"

        # -------------------------------------------------------------------
        # 8. Solve Model
        # -------------------------------------------------------------------
        solver = pulp.PULP_CBC_CMD(msg=0, timeLimit=time_limit_seconds)
        solve_start = time.perf_counter()
        try:
            model.solve(solver)
            solve_time = time.perf_counter() - solve_start
            raw_status = pulp.LpStatus[model.status]
        except Exception as e:
            logger.exception("Solver execution error: %s", e)
            solve_time = time.perf_counter() - solve_start
            raw_status = "Error"

        # Map to standard status string
        status_map = {
            "Optimal": "OPTIMAL",
            "Not Solved": "TIME_LIMIT",
            "Infeasible": "INFEASIBLE",
            "Unbounded": "UNBOUNDED",
            "Undefined": "ERROR",
            "Error": "ERROR",
        }
        solver_status = status_map.get(raw_status, raw_status.upper())

        # Count model metrics
        num_vars = len(model.variables())
        num_constrs = len(model.constraints)
        num_integers = sum(1 for v in model.variables() if v.cat in (pulp.LpInteger, pulp.LpBinary))

        solver_res = SolverResult(
            status=solver_status,
            objective_value=float(pulp.value(model.objective) or 0.0) if solver_status in ("OPTIMAL", "FEASIBLE") else 0.0,
            solve_time_seconds=solve_time,
            num_variables=num_vars,
            num_constraints=num_constrs,
            num_integer_variables=num_integers,
            solver_name="PuLP-CBC",
            message="Optimal solution found." if solver_status == "OPTIMAL" else f"Solver status: {solver_status}",
        )

        # If INFEASIBLE or ERROR: Do not mutate world state!
        if solver_status not in ("OPTIMAL", "FEASIBLE"):
            logger.warning("CargoPilot solver finished with status: %s. WorldState untouched.", solver_status)
            return OptimizationReport(
                world_id=self.state.world_id,
                simulation_time=self.t_sim.isoformat(),
                execution_timestamp=report_timestamp,
                solver_result=solver_res,
                preserved_decisions=preserved_records,
                booking_allocations=[],
                repositioning_directives=[],
                leasing_directives=[],
                impact=OptimizationImpact(
                    total_bookings_evaluated=len(self.state.bookings),
                    locked_bookings_preserved=len(b_locked),
                    exceptions_preserved=len(b_exceptions),
                ),
            )

        # -------------------------------------------------------------------
        # 9. Apply Feasible Decisions to WorldState
        # -------------------------------------------------------------------
        alloc_decisions: List[BookingAllocationDecision] = []
        repo_decisions: List[RepositioningDecision] = []
        lease_decisions: List[LeasingDecision] = []

        total_teu_allocated = 0.0
        total_containers_allocated = 0
        total_unserved_teu = 0.0
        total_repositioning_teu = 0.0

        cost_handling = 0.0
        cost_repositioning = 0.0
        cost_leasing = 0.0
        cost_unserved = 0.0

        # Assign containers and update booking state
        alloc_counter = len(self.state.allocations) + 1
        leased_counter = len([c for c in self.state.containers if c.startswith("C-LSD")]) + 1
        vessels_by_id = {v.vessel_id: v for v in self.state.vessels.values()}

        for b in b_opt:
            cands = candidate_voyages_by_b[b.booking_id]
            assigned_voyage: Optional[VoyageState] = None
            assigned_cids: List[str] = []
            alloc_qty_owned = 0
            alloc_qty_leased = 0

            for v in cands:
                y_val = int(round(pulp.value(Y_own.get((b.booking_id, v.voyage_id), 0)) or 0))
                l_val = int(round(pulp.value(L_lease.get((b.booking_id, v.voyage_id), 0)) or 0))

                if y_val > 0 or l_val > 0:
                    assigned_voyage = v
                    alloc_qty_owned = y_val
                    alloc_qty_leased = l_val
                    break

            u_val = int(round(pulp.value(U_unserved.get(b.booking_id, 0)) or 0))
            teu_per_unit = 1.0 if b.equipment_type == "20DC" else 2.0

            if assigned_voyage and (alloc_qty_owned + alloc_qty_leased > 0):
                total_allocated = alloc_qty_owned + alloc_qty_leased
                vessel_name = vessels_by_id.get(assigned_voyage.vessel_id, None)
                v_name_str = vessel_name.name if vessel_name else assigned_voyage.vessel_id

                # Match owned containers from available inventory at origin port
                avail_c_list = empty_containers.get((b.origin_port_id, b.equipment_type), [])
                matched_cids = list(avail_c_list[:alloc_qty_owned])
                # Remove allocated containers from available pool
                empty_containers[(b.origin_port_id, b.equipment_type)] = avail_c_list[alloc_qty_owned:]

                # For leased containers, instantiate distinct leased container units
                for _ in range(alloc_qty_leased):
                    leased_cid = f"C-LSD-{leased_counter:05d}"
                    leased_counter += 1
                    matched_cids.append(leased_cid)
                    self.state.containers[leased_cid] = ContainerState(
                        container_id=leased_cid,
                        equipment_type=b.equipment_type,
                        status="ALLOCATED",
                        condition="GOOD",
                        current_location_id=b.origin_port_id,
                        current_voyage_id=assigned_voyage.voyage_id,
                        booking_id=b.booking_id,
                    )

                for cid in matched_cids:
                    alloc_id = f"ALLOC-{alloc_counter:05d}"
                    alloc_counter += 1
                    self.state.allocations[alloc_id] = AllocationState(
                        allocation_id=alloc_id,
                        booking_id=b.booking_id,
                        container_id=cid,
                        voyage_id=assigned_voyage.voyage_id,
                        status="ALLOCATED",
                        locked=False,
                    )
                    # Update container state
                    if cid in self.state.containers:
                        c = self.state.containers[cid]
                        c.status = "ALLOCATED"
                        c.booking_id = b.booking_id
                        c.allocation_id = alloc_id
                        c.current_voyage_id = assigned_voyage.voyage_id

                    assigned_cids.append(cid)

                # Update booking state
                b.status = "ALLOCATED"
                b.voyage_id = assigned_voyage.voyage_id
                b.allocation_id = f"ALLOC-SET-{b.booking_id}"

                # Update equipment balance at origin port
                eq_bal = self.state.equipment.get((b.origin_port_id, b.equipment_type))
                if eq_bal:
                    eq_bal.available = max(0, eq_bal.available - alloc_qty_owned)
                    eq_bal.allocated += total_allocated

                # Update voyage booked TEU
                added_teu = total_allocated * teu_per_unit
                assigned_voyage.booked_teu += added_teu

                total_teu_allocated += added_teu
                total_containers_allocated += total_allocated
                cost_handling += total_allocated * self.COST_HANDLING_PER_CONTAINER

                alloc_decisions.append(
                    BookingAllocationDecision(
                        booking_id=b.booking_id,
                        origin_port_id=b.origin_port_id,
                        destination_port_id=b.destination_port_id,
                        equipment_type=b.equipment_type,
                        required_quantity=b.quantity,
                        allocated_quantity=total_allocated,
                        unallocated_quantity=u_val,
                        assigned_containers=assigned_cids,
                        assigned_voyage_id=assigned_voyage.voyage_id,
                        vessel_name=v_name_str,
                        departure_time=assigned_voyage.scheduled_departure.isoformat(),
                        arrival_time=assigned_voyage.scheduled_arrival.isoformat(),
                        fulfillment_cost=total_allocated * self.COST_HANDLING_PER_CONTAINER,
                    )
                )
            else:
                total_unserved_teu += u_val * teu_per_unit
                cost_unserved += u_val * self.COST_UNSERVED_PER_CONTAINER

        # Apply Repositioning Decisions
        repo_counter = len(self.state.repositioning_orders) + 1
        for (v_id, eq_type), var in X_repo.items():
            qty = int(round(pulp.value(var) or 0))
            if qty > 0:
                voyage = self.state.voyages.get(v_id)
                if voyage:
                    order_id = f"REPO-{repo_counter:04d}"
                    repo_counter += 1
                    cost = qty * self.COST_REPOSITIONING_PER_CONTAINER
                    cost_repositioning += cost
                    teu_mult = 1.0 if eq_type == "20DC" else 2.0
                    total_repositioning_teu += qty * teu_mult

                    self.state.repositioning_orders[order_id] = RepositioningState(
                        reposition_id=order_id,
                        source_location_id=voyage.origin_port_id,
                        destination_location_id=voyage.destination_port_id,
                        equipment_type=eq_type,
                        quantity=qty,
                        departure_time=voyage.scheduled_departure,
                        estimated_arrival=voyage.scheduled_arrival,
                        status="IN_TRANSIT",
                    )
                    # Deduct from origin port available equipment balance
                    eq_bal = self.state.equipment.get((voyage.origin_port_id, eq_type))
                    if eq_bal:
                        eq_bal.available = max(0, eq_bal.available - qty)

                    repo_decisions.append(
                        RepositioningDecision(
                            order_id=order_id,
                            from_port_id=voyage.origin_port_id,
                            to_port_id=voyage.destination_port_id,
                            equipment_type=eq_type,
                            quantity=qty,
                            voyage_id=v_id,
                            departure_time=voyage.scheduled_departure.isoformat(),
                            arrival_time=voyage.scheduled_arrival.isoformat(),
                            estimated_cost=cost,
                        )
                    )

        # Apply Leasing Decisions
        lease_counter = len(self.state.leases) + 1
        for (port_id, eq_type), var in LeaseOrder.items():
            qty = int(round(pulp.value(var) or 0))
            if qty > 0:
                lease_id = f"LEASE-{lease_counter:04d}"
                lease_counter += 1
                cost = qty * self.COST_LEASE_PER_CONTAINER
                cost_leasing += cost

                self.state.leases[lease_id] = LeaseState(
                    lease_id=lease_id,
                    location_id=port_id,
                    equipment_type=eq_type,
                    quantity=qty,
                    daily_rate=25.0,
                    start_time=self.t_sim,
                    duration_days=30.0,
                    status="ACTIVE",
                    equipment_available_at=self.t_sim,
                )
                # Increment available equipment balance at port
                eq_bal = self.state.equipment.get((port_id, eq_type))
                if eq_bal:
                    eq_bal.available += qty

                lease_decisions.append(
                    LeasingDecision(
                        lease_id=lease_id,
                        location_id=port_id,
                        equipment_type=eq_type,
                        quantity=qty,
                        daily_rate=25.0,
                        duration_days=30.0,
                        estimated_cost=cost,
                    )
                )

        # -------------------------------------------------------------------
        # 10. Assemble and Return Optimization Report
        # -------------------------------------------------------------------
        cost_ledger = OperationalCostLedger(
            terminal_handling_cost=cost_handling,
            repositioning_cost=cost_repositioning,
            leasing_cost=cost_leasing,
            unserved_demand_penalty=cost_unserved,
            shortage_penalty=0.0,
        )

        impact = OptimizationImpact(
            total_bookings_evaluated=len(self.state.bookings),
            bookings_allocated=len(alloc_decisions),
            bookings_unserved=len(b_opt) - len(alloc_decisions),
            teu_allocated=total_teu_allocated,
            containers_allocated=total_containers_allocated,
            locked_bookings_preserved=len(b_locked),
            exceptions_preserved=len(b_exceptions),
            repositioning_moves=len(repo_decisions),
            repositioning_teu=total_repositioning_teu,
            leased_containers=sum(l.quantity for l in lease_decisions),
            unserved_demand_teu=total_unserved_teu,
            costs=cost_ledger,
        )

        report = OptimizationReport(
            world_id=self.state.world_id,
            simulation_time=self.t_sim.isoformat(),
            execution_timestamp=report_timestamp,
            solver_result=solver_res,
            preserved_decisions=preserved_records,
            booking_allocations=alloc_decisions,
            repositioning_directives=repo_decisions,
            leasing_directives=lease_decisions,
            impact=impact,
        )

        logger.info(
            "CargoPilot Optimization complete in %.2fs: %s. Allocated %d bookings (%0.1f TEU), preserved %d locked.",
            solve_time,
            solver_status,
            len(alloc_decisions),
            total_teu_allocated,
            len(b_locked),
        )

        return report

    def _estimate_departure_time(self, booking: BookingState) -> datetime:
        """
        Estimate scheduled departure timestamp for a booking.
        Uses assigned voyage departure if known, else minimum candidate departure,
        else fallback from cargo ready time.
        """
        if booking.voyage_id and booking.voyage_id in self.state.voyages:
            return self.state.voyages[booking.voyage_id].scheduled_departure

        # Search candidate scheduled voyages from origin to destination
        candidates = [
            v for v in self.state.voyages.values()
            if v.origin_port_id == booking.origin_port_id
            and v.destination_port_id == booking.destination_port_id
            and v.scheduled_departure >= booking.cargo_ready_time
        ]
        if candidates:
            candidates.sort(key=lambda x: x.scheduled_departure)
            return candidates[0].scheduled_departure

        # Fallback based on cargo ready time
        return booking.cargo_ready_time + timedelta(days=2)
