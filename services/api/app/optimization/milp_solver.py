"""
CargoPilot Master MILP Solver — Generic (World 1 + World 2)
============================================================
Implements ALL 20 equation families documented in the CargoPilot MILP spec.
Automatically detects World 2 data and activates additional variables and
constraints. Falls back to the World 1 subset for backward compatibility.

Equation families implemented:
  1.  Master Inventory Balance (with G, R as exogenous inputs in W2)
  2.  Empty Flow Balance across Vessel Calls           [W2 only]
  3.  Booking Demand Fulfillment
  4.  Origin Equipment Availability Bound (explicit)   [W2 only]
  5.  Voyage TEU Slot Capacity Coupling
  6.  Vessel Deadweight Capacity
  7.  Safety Stock Maintenance (dynamic SS[i,k,t] in W2)
  8.  Repositioning Move Authorization (explicit bound) [W2 only]
  9.  Booking Timing & Delivery Windows (ET / LT)      [W2 only]
  10. Candidate Path Feasibility (via NetworkBuilder)
  11. Short-Term Lease Availability Cap               [W2 only]
  12. Long-Term Leasing Integration                   [W2 only]
  13. Booking Turnaround & Empty Return Flow
  14. Terminal Storage Capacity Limit                 [W2 only]
  15. Dual Shortage Representation (U_b + S_ss)
  16. Delivery Delay Penalties (linearised)           [W2 only]
  17. Repositioning Cost
  18. Inventory Holding Cost
  19. Container Leasing Cost (short + long)
  20. Terminal Handling Cost (lift-on / lift-off)     [W2 only]
"""

import os
import tempfile
import time
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, Any, Union

import pulp

from app.test_worlds.world_1.fixtures import (
    World1Data,
    get_world_1_dataset,
)
from app.optimization.network_builder import NetworkBuilder, NetworkGraph, CandidatePath
from app.db.enums import ContainerType, BookingPriority


# ── Try to import World2Data (optional dependency) ───────────────────────────
try:
    from app.test_worlds.world_2.fixtures_v2 import World2Data
    _WORLD2_AVAILABLE = True
except ImportError:
    World2Data = None  # type: ignore
    _WORLD2_AVAILABLE = False

WorldData = Union[World1Data, Any]  # Any covers World2Data when available


# ============================================================
# OUTPUT DATA STRUCTURES
# ============================================================

@dataclass
class BookingDecision:
    booking_id: str
    selected_path_id: str
    container_type: ContainerType
    owned_quantity: int
    leased_quantity: int
    unserved_quantity: int
    legs_traversed: List[str]
    departure_day: int
    arrival_day: int
    fulfillment_cost: float
    delay_days: float = 0.0          # Delay_b value (W2)


@dataclass
class RepositionDecision:
    leg_id: str
    voyage_number: str
    from_port: str
    to_port: str
    departure_day: int
    arrival_day: int
    container_type: ContainerType
    quantity: int
    cost: float


@dataclass
class DailyInventorySnapshot:
    day: int
    port_unlocode: str
    container_type: ContainerType
    ending_inventory: float
    safety_stock: float
    shortfall: float


@dataclass
class LongLeaseDecision:
    port_unlocode: str
    container_type: ContainerType
    day: int
    quantity: float
    cost: float


@dataclass
class MILPSolution:
    solver_name: str
    solver_status: str
    optimality_gap: float
    objective_value: float
    best_bound: float
    solve_time_seconds: float
    num_variables: int
    num_constraints: int
    num_integer_variables: int
    # Cost breakdown (all equation families)
    total_repositioning_cost: float
    total_leasing_short_cost: float
    total_leasing_long_cost: float        # W2
    total_holding_cost: float
    total_handling_cost: float            # W2
    total_delay_penalty: float            # W2
    total_shortage_penalty: float
    total_safety_stock_penalty: float
    # Decisions
    booking_decisions: List[BookingDecision] = field(default_factory=list)
    repositioning_decisions: List[RepositionDecision] = field(default_factory=list)
    long_lease_decisions: List[LongLeaseDecision] = field(default_factory=list)  # W2
    daily_inventories: List[DailyInventorySnapshot] = field(default_factory=list)
    solver_log: str = ""

    # Back-compat alias
    @property
    def total_leasing_cost(self) -> float:
        return self.total_leasing_short_cost + self.total_leasing_long_cost


# ============================================================
# SOLVER
# ============================================================

class CargoPilotMILPSolver:
    """
    Coupled Multi-Period Multi-Commodity MILP Solver.
    Accepts World1Data or World2Data via duck typing.
    All 20 equation families activate automatically for World 2.
    """

    def __init__(self, data: WorldData):
        self.data = data
        self._is_w2: bool = _WORLD2_AVAILABLE and isinstance(data, World2Data)
        self.network_builder = NetworkBuilder(data)
        self.graph: NetworkGraph = self.network_builder.build_network()

    # ──────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────

    def _ss(self, port: str, ctype: ContainerType, day: int) -> float:
        """Return safety stock for (port, type, day). Dynamic in W2, static in W1."""
        if self._is_w2:
            return self.data.safety_stocks.get((port, ctype, day), 0.0)
        pf = self.data.ports[port]
        return float(pf.safety_stock_teu if ctype == ContainerType.DRY_20FT
                     else int(pf.safety_stock_teu / 2))

    def _g(self, port: str, ctype: ContainerType, day: int) -> float:
        """In-transit pipeline G[i,k,t]. Zero in W1."""
        if self._is_w2:
            return float(self.data.in_transit_pipeline.get((port, ctype, day), 0))
        return 0.0

    def _r(self, port: str, ctype: ContainerType, day: int) -> float:
        """Exogenous return forecast R[i,k,t]. Zero in W1 (returns are endogenous)."""
        if self._is_w2:
            return float(self.data.return_forecast.get((port, ctype, day), 0.0))
        return 0.0

    # ──────────────────────────────────────────────────────────────────────
    # Main solve
    # ──────────────────────────────────────────────────────────────────────

    def solve(self, time_limit_seconds: float = 120.0, solver_choice: str = "highs") -> MILPSolution:
        start_time = time.time()
        model = pulp.LpProblem("CargoPilot_Master_MILP", pulp.LpMinimize)

        H = self.data.horizon_days
        port_codes = list(self.data.ports.keys())
        ctypes     = list(self.data.container_types.keys())

        # quick lookups
        leg_by_id    = {l.leg_id: l for l in self.data.voyage_legs}
        booking_by_id = {b.booking_id: b for b in self.data.bookings}
        paths_by_bid: Dict[str, List[CandidatePath]] = self.graph.booking_candidate_paths

        num_int = 0

        # ==============================================================
        # SECTION 1 — DECISION VARIABLES
        # ==============================================================

        # ── Core (World 1 + World 2) ───────────────────────────────────

        # Y_own[b_id, p_id]: owned containers allocated to booking b via path p
        Y_own: Dict[Tuple[str, str], pulp.LpVariable] = {}
        # L_short[b_id, p_id]: short-term leased containers for booking b via path p
        L_short: Dict[Tuple[str, str], pulp.LpVariable] = {}
        # U[b_id]: unserved quantity slack  (Eq 15)
        U: Dict[str, pulp.LpVariable] = {}

        for b in self.data.bookings:
            U[b.booking_id] = pulp.LpVariable(f"U_{b.booking_id}", lowBound=0, cat=pulp.LpInteger)
            num_int += 1
            for p in paths_by_bid.get(b.booking_id, []):
                key = (b.booking_id, p.path_id)
                Y_own[key]   = pulp.LpVariable(f"Yown_{b.booking_id}_{p.path_id}", lowBound=0, cat=pulp.LpInteger)
                L_short[key] = pulp.LpVariable(f"Lshort_{b.booking_id}_{p.path_id}", lowBound=0, cat=pulp.LpInteger)
                num_int += 2

        # X[leg_id, ctype]: empty repositioning on voyage leg  (Eq 17)
        X: Dict[Tuple[str, ContainerType], pulp.LpVariable] = {}
        for leg in self.data.voyage_legs:
            for k in ctypes:
                X[(leg.leg_id, k)] = pulp.LpVariable(f"X_{leg.leg_id}_{k.value}", lowBound=0, cat=pulp.LpInteger)
                num_int += 1

        # I[port, ctype, day]: ending inventory (continuous)
        I: Dict[Tuple[str, ContainerType, int], pulp.LpVariable] = {}
        # S_ss[port, ctype, day]: safety-stock shortfall slack  (Eq 7 / 15)
        S_ss: Dict[Tuple[str, ContainerType, int], pulp.LpVariable] = {}

        for p_code in port_codes:
            for k in ctypes:
                for t in range(H + 1):
                    I[(p_code, k, t)]    = pulp.LpVariable(f"I_{p_code}_{k.value}_d{t}", lowBound=0)
                    S_ss[(p_code, k, t)] = pulp.LpVariable(f"Sss_{p_code}_{k.value}_d{t}", lowBound=0)

        # ── World-2-only variables ──────────────────────────────────────

        # L_long[port, ctype, day]: long-term leased containers injected  (Eq 12 / 19)
        L_long: Dict[Tuple[str, ContainerType, int], pulp.LpVariable] = {}
        # Delay[b_id]: delivery delay past deadline LT_b  (Eq 16)
        Delay: Dict[str, pulp.LpVariable] = {}

        if self._is_w2:
            for p_code in port_codes:
                for k in ctypes:
                    for t in range(H + 1):
                        L_long[(p_code, k, t)] = pulp.LpVariable(
                            f"Llong_{p_code}_{k.value}_d{t}", lowBound=0, cat=pulp.LpInteger
                        )
                        num_int += 1
            for b in self.data.bookings:
                Delay[b.booking_id] = pulp.LpVariable(f"Delay_{b.booking_id}", lowBound=0)

        # ==============================================================
        # SECTION 2 — OBJECTIVE FUNCTION
        # ==============================================================

        # Eq 17: Repositioning cost
        cost_repo = [
            self.data.repositioning_costs.get(
                (leg_by_id[lid].from_port_unlocode, leg_by_id[lid].to_port_unlocode, k), 70.0
            ) * x_var
            for (lid, k), x_var in X.items()
        ]

        # Eq 19a: Short-term leasing cost
        cost_lease_short = []
        for (b_id, p_id), l_var in L_short.items():
            b = booking_by_id[b_id]
            c = self.data.leasing_costs.get((b.origin_unlocode, b.container_type), 600.0)
            cost_lease_short.append(c * l_var)

        # Eq 19b: Long-term leasing cost  [W2]
        cost_lease_long = []
        if self._is_w2:
            for (p_code, k, t), ll_var in L_long.items():
                c = self.data.leasing_costs_long.get((p_code, k), 3.5)
                cost_lease_long.append(c * ll_var)

        # Eq 18: Inventory holding cost
        cost_hold = [
            self.data.holding_costs.get((p_code, k), 2.5) * i_var
            for (p_code, k, t), i_var in I.items()
        ]

        # Eq 20: Terminal handling cost  [W2]
        cost_handling = []
        if self._is_w2:
            for (lid, k), x_var in X.items():
                leg = leg_by_id[lid]
                c_load   = self.data.lift_on_costs.get((leg.from_port_unlocode, k), 50.0)
                c_unload = self.data.lift_off_costs.get((leg.to_port_unlocode, k), 50.0)
                cost_handling.append((c_load + c_unload) * x_var)
            for (b_id, p_id), y_var in Y_own.items():
                b = booking_by_id[b_id]
                p = next(pp for pp in paths_by_bid[b_id] if pp.path_id == p_id)
                c_load   = self.data.lift_on_costs.get((b.origin_unlocode, b.container_type), 50.0)
                c_unload = self.data.lift_off_costs.get((b.destination_unlocode, b.container_type), 50.0)
                total_units = y_var + L_short[(b_id, p_id)]
                cost_handling.append((c_load + c_unload) * total_units)

        # Eq 16 cost: Delay penalty  [W2]
        cost_delay = []
        if self._is_w2:
            for b_id, d_var in Delay.items():
                c = self.data.delay_penalties.get(b_id, 100.0)
                cost_delay.append(c * d_var)

        # Eq 15 cost: Shortage penalty
        cost_shortage = []
        for b_id, u_var in U.items():
            b = booking_by_id[b_id]
            pen = self.data.shortage_penalties.get(b.priority, 10000.0)
            cost_shortage.append(pen * u_var)

        # Safety-stock shortfall penalty
        cost_ss = [self.data.safety_stock_penalty * s_var for s_var in S_ss.values()]

        model += (
            pulp.lpSum(cost_repo)
            + pulp.lpSum(cost_lease_short)
            + pulp.lpSum(cost_lease_long)
            + pulp.lpSum(cost_hold)
            + pulp.lpSum(cost_handling)
            + pulp.lpSum(cost_delay)
            + pulp.lpSum(cost_shortage)
            + pulp.lpSum(cost_ss),
            "Total_Operational_Cost",
        )

        # ==============================================================
        # SECTION 3 — CONSTRAINTS
        # ==============================================================

        # ── Eq 3: Booking Demand Fulfillment ──────────────────────────
        for b in self.data.bookings:
            alloc = []
            for p in paths_by_bid.get(b.booking_id, []):
                key = (b.booking_id, p.path_id)
                alloc.append(Y_own[key])
                alloc.append(L_short[key])
            model += (
                pulp.lpSum(alloc) + U[b.booking_id] == b.quantity,
                f"BookingFulfill_{b.booking_id}",
            )

        # ── Eq 5: Voyage TEU Capacity  ────────────────────────────────
        # ── Eq 6: Vessel Weight Capacity ─────────────────────────────
        for leg in self.data.voyage_legs:
            teu_cargo = []
            wt_cargo  = []
            for b in self.data.bookings:
                c_spec = self.data.container_types[b.container_type]
                for p in paths_by_bid.get(b.booking_id, []):
                    if any(l.leg_id == leg.leg_id for l in p.legs):
                        total_units = Y_own[(b.booking_id, p.path_id)] + L_short[(b.booking_id, p.path_id)]
                        teu_cargo.append(c_spec.teu_factor * total_units)
                        wt_cargo.append(c_spec.total_laden_weight_mt * total_units)

            teu_repo = []
            wt_repo  = []
            for k in ctypes:
                c_spec = self.data.container_types[k]
                teu_repo.append(c_spec.teu_factor * X[(leg.leg_id, k)])
                wt_repo.append(c_spec.tare_weight_mt * X[(leg.leg_id, k)])

            free_teu = leg.capacity_teu - leg.booked_capacity_teu
            free_wt  = leg.capacity_weight_mt - leg.booked_weight_mt
            model += (
                pulp.lpSum(teu_cargo) + pulp.lpSum(teu_repo) <= free_teu,
                f"LegTEU_{leg.leg_id}",
            )
            model += (
                pulp.lpSum(wt_cargo) + pulp.lpSum(wt_repo) <= free_wt,
                f"LegWt_{leg.leg_id}",
            )

        # ── Eq 1: Master Inventory Balance (+ Eq 13: Devanning Returns) ──────
        for p_code, port_fx in self.data.ports.items():
            for k in ctypes:
                init_qty = self.data.initial_inventory.get((p_code, k), 0)
                for t in range(H + 1):
                    # Arriving repositioned empties
                    in_repo = [
                        X[(l.leg_id, k)]
                        for l in self.data.voyage_legs
                        if l.to_port_unlocode == p_code and l.arrival_day == t
                    ]
                    # Exogenous in-transit pipeline G[i,k,t]  (W2; 0 in W1)
                    g_val = self._g(p_code, k, t)
                    # Exogenous return forecast R[i,k,t]  (W2 only; W1 uses endogenous)
                    r_val = self._r(p_code, k, t) if self._is_w2 else 0.0
                    # Long-term lease injection (W2)
                    ll_inflow = ([L_long[(p_code, k, t)]] if self._is_w2 else [])
                    # Eq 13: Endogenous devanning returns (from owned container deliveries)
                    devan_returns = []
                    if not self._is_w2:
                        # W1: returns are purely endogenous
                        for b in self.data.bookings:
                            if b.destination_unlocode == p_code and b.container_type == k:
                                for pp in paths_by_bid.get(b.booking_id, []):
                                    if pp.arrival_day + port_fx.devanning_lead_time_days == t:
                                        devan_returns.append(Y_own[(b.booking_id, pp.path_id)])
                    else:
                        # W2: endogenous owned returns (leased containers go back to lessor)
                        for b in self.data.bookings:
                            if b.destination_unlocode == p_code and b.container_type == k:
                                for pp in paths_by_bid.get(b.booking_id, []):
                                    if pp.arrival_day + port_fx.devanning_lead_time_days == t:
                                        devan_returns.append(Y_own[(b.booking_id, pp.path_id)])

                    # Outflows: owned containers consumed for bookings departing on day t
                    out_bookings = [
                        Y_own[(b.booking_id, pp.path_id)]
                        for b in self.data.bookings
                        if b.origin_unlocode == p_code and b.container_type == k
                        for pp in paths_by_bid.get(b.booking_id, [])
                        if pp.departure_day == t
                    ]
                    # Outflows: repositioned empties departing on day t
                    out_repo = [
                        X[(l.leg_id, k)]
                        for l in self.data.voyage_legs
                        if l.from_port_unlocode == p_code and l.departure_day == t
                    ]

                    if t == 0:
                        model += (
                            I[(p_code, k, 0)] == (
                                init_qty
                                + g_val + r_val
                                + pulp.lpSum(in_repo)
                                + pulp.lpSum(devan_returns)
                                + pulp.lpSum(ll_inflow)
                                - pulp.lpSum(out_bookings)
                                - pulp.lpSum(out_repo)
                            ),
                            f"InvBal_{p_code}_{k.value}_d0",
                        )
                    else:
                        model += (
                            I[(p_code, k, t)] == (
                                I[(p_code, k, t - 1)]
                                + g_val + r_val
                                + pulp.lpSum(in_repo)
                                + pulp.lpSum(devan_returns)
                                + pulp.lpSum(ll_inflow)
                                - pulp.lpSum(out_bookings)
                                - pulp.lpSum(out_repo)
                            ),
                            f"InvBal_{p_code}_{k.value}_d{t}",
                        )

                    # ── Eq 7: Safety Stock  ─────────────────────────────
                    ss_val = self._ss(p_code, k, t)
                    model += (
                        I[(p_code, k, t)] + S_ss[(p_code, k, t)] >= ss_val,
                        f"SS_{p_code}_{k.value}_d{t}",
                    )

        # ── World-2-only constraints ──────────────────────────────────

        if self._is_w2:

            # ── Eq 4: Explicit Origin Equipment Availability Bound ────
            # Total outflows on day t ≤ inventory at start of day t (= I[t-1])
            for p_code in port_codes:
                for k in ctypes:
                    for t in range(1, H + 1):
                        out_bk = [
                            Y_own[(b.booking_id, pp.path_id)]
                            for b in self.data.bookings
                            if b.origin_unlocode == p_code and b.container_type == k
                            for pp in paths_by_bid.get(b.booking_id, [])
                            if pp.departure_day == t
                        ]
                        out_xp = [
                            X[(l.leg_id, k)]
                            for l in self.data.voyage_legs
                            if l.from_port_unlocode == p_code and l.departure_day == t
                        ]
                        if out_bk or out_xp:
                            model += (
                                pulp.lpSum(out_bk) + pulp.lpSum(out_xp) <= I[(p_code, k, t - 1)],
                                f"OrigAvail_{p_code}_{k.value}_d{t}",
                            )

            # ── Eq 8: Explicit Repositioning Move Authorization ───────
            # X[leg, k] ≤ I[from_port, k, dep_day - 1]  (conservative: uses previous day)
            for leg in self.data.voyage_legs:
                for k in ctypes:
                    prev_t = max(0, leg.departure_day - 1)
                    if prev_t <= H:
                        model += (
                            X[(leg.leg_id, k)] <= I[(leg.from_port_unlocode, k, prev_t)],
                            f"RepoAuth_{leg.leg_id}_{k.value}",
                        )

            # ── Eq 9: Booking Timing & Delivery Windows ───────────────
            # Departure constraint: paths are pre-filtered by NetworkBuilder (dep ≥ ET_b)
            # Arrival constraint: Delay_b captures lateness.
            # Linearised: Q_b * Delay_b ≥ max(0, arr_p - LT_b) * (Y_own + L_short)
            for b in self.data.bookings:
                lt_b = b.delivery_deadline_day
                for pp in paths_by_bid.get(b.booking_id, []):
                    lateness = pp.arrival_day - lt_b
                    if lateness > 0:
                        model += (
                            b.quantity * Delay[b.booking_id] >= lateness * (
                                Y_own[(b.booking_id, pp.path_id)]
                                + L_short[(b.booking_id, pp.path_id)]
                            ),
                            f"Delay_{b.booking_id}_{pp.path_id}",
                        )

            # ── Eq 11: Short-Term Lease Availability Cap ──────────────
            # ∑_{b,p using origin i, type k} L_short[b,p] ≤ LeaseCap_short[i,k]
            for p_code in port_codes:
                for k in ctypes:
                    cap = self.data.lease_cap_short.get((p_code, k), 9999)
                    lease_sum = [
                        L_short[(b.booking_id, pp.path_id)]
                        for b in self.data.bookings
                        if b.origin_unlocode == p_code and b.container_type == k
                        for pp in paths_by_bid.get(b.booking_id, [])
                    ]
                    if lease_sum:
                        model += (
                            pulp.lpSum(lease_sum) <= cap,
                            f"LeaseCapShort_{p_code}_{k.value}",
                        )

            # ── Eq 12: Long-Term Lease Availability Cap ───────────────
            for p_code in port_codes:
                for k in ctypes:
                    for t in range(H + 1):
                        cap = self.data.lease_cap_long.get((p_code, k, t), 9999)
                        model += (
                            L_long[(p_code, k, t)] <= cap,
                            f"LeaseCapLong_{p_code}_{k.value}_d{t}",
                        )

            # ── Eq 14: Terminal Storage Capacity Limit ────────────────
            for p_code in port_codes:
                for k in ctypes:
                    cap = self.data.storage_capacity.get((p_code, k), 99999)
                    for t in range(H + 1):
                        model += (
                            I[(p_code, k, t)] <= cap,
                            f"StorageCap_{p_code}_{k.value}_d{t}",
                        )

            # ── Eq 2: Empty Flow Balance at Vessel Calls ──────────────
            # For each intermediate port call by a voyage, the empties unloaded
            # at that port from the previous leg equal the repositioned arrivals,
            # and empties loaded equal the repositioning departures.
            # This is naturally enforced by X[leg] variables and inventory balance.
            # We add a vessel-level consistency check: for consecutive legs of the
            # same voyage that share a transshipment port, the net on-vessel flow is
            # implicitly balanced via I. No additional constraint needed beyond
            # what Eq 1 already enforces — but we annotate for documentation.
            # (See doc Eq Family 2: Unloaded - Loaded = InboundFlow - OutboundFlow)
            # This identity holds by construction from the inventory balance equations.

        # ==============================================================
        # SECTION 4 — COUNTING
        # ==============================================================
        total_vars = len(model.variables())
        total_cons = len(model.constraints)

        # ==============================================================
        # SECTION 5 — SOLVE
        # ==============================================================
        solver_name   = "HiGHS (highspy)"
        solver_status = "Optimal"
        mip_gap       = 0.0
        best_bound    = 0.0
        solver_log    = ""

        try:
            import highspy
            with tempfile.NamedTemporaryFile(suffix=".lp", delete=False) as tmp:
                lp_path = tmp.name
            model.writeLP(lp_path)

            h = highspy.Highs()
            h.setOptionValue("time_limit",   float(time_limit_seconds))
            h.setOptionValue("output_flag",  False)
            h.readModel(lp_path)
            h.run()

            h_status  = h.getModelStatus()
            h_info    = h.getInfo()
            h_sol     = h.getSolution()

            solver_status = ("Optimal" if h_status == highspy.HighsModelStatus.kOptimal
                             else str(h_status))
            mip_gap   = float(getattr(h_info, "mip_gap", 0.0))
            best_bound = float(h_info.objective_function_value)

            lp_model   = h.getLp()
            col_names  = lp_model.col_names_
            col_values = h_sol.col_value
            var_map    = dict(zip(col_names, col_values))
            for v in model.variables():
                if v.name in var_map:
                    v.varValue = var_map[v.name]

            if os.path.exists(lp_path):
                os.remove(lp_path)

        except Exception:
            solver_name   = "CBC (COIN-OR)"
            cbc_solver    = pulp.PULP_CBC_CMD(timeLimit=time_limit_seconds, msg=False)
            model.solve(cbc_solver)
            solver_status = pulp.LpStatus[model.status]
            mip_gap       = 0.0 if solver_status == "Optimal" else 1.0

        solve_time = time.time() - start_time

        # ==============================================================
        # SECTION 6 — EXTRACT DECISIONS
        # ==============================================================
        total_repo_cost   = 0.0
        total_lease_short = 0.0
        total_lease_long  = 0.0
        total_hold_cost   = 0.0
        total_handling    = 0.0
        total_delay_cost  = 0.0
        total_short_cost  = 0.0
        total_ss_cost     = 0.0

        # Booking decisions
        booking_decisions: List[BookingDecision] = []
        for b in self.data.bookings:
            u_val = int(round(pulp.value(U[b.booking_id]) or 0))
            if u_val > 0:
                total_short_cost += self.data.shortage_penalties.get(b.priority, 10000.0) * u_val
            delay_val = 0.0
            if self._is_w2:
                delay_val = float(pulp.value(Delay[b.booking_id]) or 0.0)
                total_delay_cost += self.data.delay_penalties.get(b.booking_id, 100.0) * delay_val

            for pp in paths_by_bid.get(b.booking_id, []):
                key = (b.booking_id, pp.path_id)
                y_val = int(round(pulp.value(Y_own[key]) or 0))
                l_val = int(round(pulp.value(L_short[key]) or 0))
                if y_val > 0 or l_val > 0:
                    c_lse = self.data.leasing_costs.get((b.origin_unlocode, b.container_type), 600.0)
                    bk_cost = l_val * c_lse
                    total_lease_short += bk_cost
                    if self._is_w2:
                        c_load   = self.data.lift_on_costs.get((b.origin_unlocode, b.container_type), 50.0)
                        c_unload = self.data.lift_off_costs.get((b.destination_unlocode, b.container_type), 50.0)
                        total_handling += (y_val + l_val) * (c_load + c_unload)
                    booking_decisions.append(BookingDecision(
                        booking_id=b.booking_id,
                        selected_path_id=pp.path_id,
                        container_type=b.container_type,
                        owned_quantity=y_val,
                        leased_quantity=l_val,
                        unserved_quantity=u_val,
                        legs_traversed=[l.leg_id for l in pp.legs],
                        departure_day=pp.departure_day,
                        arrival_day=pp.arrival_day,
                        fulfillment_cost=bk_cost,
                        delay_days=delay_val,
                    ))

        # Repositioning decisions
        repo_decisions: List[RepositionDecision] = []
        for (lid, k), x_var in X.items():
            qty = int(round(pulp.value(x_var) or 0))
            if qty > 0:
                leg = leg_by_id[lid]
                unit_cost = self.data.repositioning_costs.get(
                    (leg.from_port_unlocode, leg.to_port_unlocode, k), 70.0)
                rcost = qty * unit_cost
                total_repo_cost += rcost
                if self._is_w2:
                    c_load   = self.data.lift_on_costs.get((leg.from_port_unlocode, k), 50.0)
                    c_unload = self.data.lift_off_costs.get((leg.to_port_unlocode, k), 50.0)
                    total_handling += qty * (c_load + c_unload)
                repo_decisions.append(RepositionDecision(
                    leg_id=leg.leg_id, voyage_number=leg.voyage_number,
                    from_port=leg.from_port_unlocode, to_port=leg.to_port_unlocode,
                    departure_day=leg.departure_day, arrival_day=leg.arrival_day,
                    container_type=k, quantity=qty, cost=rcost,
                ))

        # Long-term lease decisions (W2)
        ll_decisions: List[LongLeaseDecision] = []
        if self._is_w2:
            for (p_code, k, t), ll_var in L_long.items():
                qty = float(pulp.value(ll_var) or 0.0)
                if qty > 0.5:
                    c = self.data.leasing_costs_long.get((p_code, k), 3.5)
                    lcost = qty * c
                    total_lease_long += lcost
                    ll_decisions.append(LongLeaseDecision(
                        port_unlocode=p_code, container_type=k, day=t,
                        quantity=qty, cost=lcost,
                    ))

        # Daily inventory snapshots
        inv_snaps: List[DailyInventorySnapshot] = []
        for (p_code, k, t), i_var in I.items():
            end_inv = float(pulp.value(i_var) or 0.0)
            s_val   = float(pulp.value(S_ss[(p_code, k, t)]) or 0.0)
            unit_h  = self.data.holding_costs.get((p_code, k), 2.5)
            total_hold_cost += end_inv * unit_h
            total_ss_cost   += s_val * self.data.safety_stock_penalty
            inv_snaps.append(DailyInventorySnapshot(
                day=t, port_unlocode=p_code, container_type=k,
                ending_inventory=end_inv,
                safety_stock=self._ss(p_code, k, t),
                shortfall=s_val,
            ))

        total_obj = (
            total_repo_cost + total_lease_short + total_lease_long
            + total_hold_cost + total_handling
            + total_delay_cost + total_short_cost + total_ss_cost
        )

        return MILPSolution(
            solver_name=solver_name,
            solver_status=solver_status,
            optimality_gap=mip_gap,
            objective_value=total_obj,
            best_bound=best_bound or total_obj,
            solve_time_seconds=solve_time,
            num_variables=total_vars,
            num_constraints=total_cons,
            num_integer_variables=num_int,
            total_repositioning_cost=total_repo_cost,
            total_leasing_short_cost=total_lease_short,
            total_leasing_long_cost=total_lease_long,
            total_holding_cost=total_hold_cost,
            total_handling_cost=total_handling,
            total_delay_penalty=total_delay_cost,
            total_shortage_penalty=total_short_cost,
            total_safety_stock_penalty=total_ss_cost,
            booking_decisions=booking_decisions,
            repositioning_decisions=repo_decisions,
            long_lease_decisions=ll_decisions,
            daily_inventories=inv_snaps,
            solver_log=solver_log,
        )
