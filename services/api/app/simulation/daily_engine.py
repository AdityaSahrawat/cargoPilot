from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Dict, List, Tuple, Optional, Any
import copy

from app.test_worlds.world_1.fixtures import (
    World1Data,
    PortFixture,
    VesselFixture,
    VoyageLegFixture,
    BookingFixture,
    ContainerTypeSpec,
    get_world_1_dataset,
)
from app.optimization.milp_solver import CargoPilotMILPSolver, MILPSolution
from app.db.enums import ContainerType, BookingPriority, BookingStatus


@dataclass
class VesselState:
    vessel_name: str
    current_port: Optional[str]
    in_transit: bool
    from_port: Optional[str]
    to_port: Optional[str]
    departure_day: Optional[int]
    arrival_day: Optional[int]
    progress_pct: float
    teu_load: int
    weight_load_mt: float


@dataclass
class BookingSimulationState:
    booking_id: str
    origin_unlocode: str
    destination_unlocode: str
    container_type: ContainerType
    quantity: int
    priority: BookingPriority
    status: str  # REQUESTED, CONFIRMED, GATED, LOADED, IN_TRANSIT, DELIVERED, DEVANNING_DONE
    assigned_voyage_number: Optional[str]
    departure_day: Optional[int]
    expected_arrival_day: Optional[int]
    actual_delivery_day: Optional[int]
    is_leased: bool


@dataclass
class BookingDispatchDirective:
    booking_id: str
    origin_port: str
    destination_port: str
    container_type: str
    total_quantity: int
    owned_quantity: int
    leased_quantity: int
    assigned_voyage: str
    departure_day: int
    arrival_day: int
    urgency: str  # DISPATCH_NOW, LOAD_VESSEL_TODAY, IN_TRANSIT, DELIVERED, UPCOMING
    action_instruction: str


@dataclass
class EmptyRepositionDirective:
    port_unlocode: str
    port_name: str
    has_departing_vessel: bool
    voyage_number: Optional[str]
    leg_id: Optional[str]
    destination_port: Optional[str]
    should_load_empties: bool
    reposition_quantities: Dict[str, int]
    total_reposition_teu: int
    action_instruction: str


@dataclass
class PortDailyActionSummary:
    port_unlocode: str
    port_name: str
    current_stock: Dict[str, float]
    total_stock_teu: int
    safety_stock_teu: int
    safety_status: str  # HEALTHY, WARNING, CRITICAL
    outbound_laden_units: int
    empty_reposition_load_units: int
    inbound_devanning_units: int
    leased_units: int
    recommended_action: str


@dataclass
class DaySimulationSnapshot:
    day: int
    simulation_date: str
    port_inventories: Dict[str, Dict[str, float]]
    port_safety_stocks: Dict[str, int]
    vessels: List[VesselState]
    bookings: List[BookingSimulationState]
    active_repositions: List[Dict[str, Any]]
    port_action_summaries: List[PortDailyActionSummary]
    empty_reposition_directives: List[EmptyRepositionDirective]
    booking_dispatch_directives: List[BookingDispatchDirective]
    daily_holding_cost: float
    daily_repositioning_cost: float
    daily_leasing_cost: float
    cumulative_total_cost: float
    alerts: List[str]


class DailySimulationEngine:
    """40-Day Daily Rolling-Horizon Simulation & Operational Dispatch Engine for Test World 1."""

    def __init__(self, data: Optional[World1Data] = None):
        self.data = data or get_world_1_dataset()
        self.current_day: int = 0
        self.history: List[DaySimulationSnapshot] = []

        # Current Port Inventories: (port, ctype) -> float
        self.inventories: Dict[Tuple[str, ContainerType], float] = dict(self.data.initial_inventory)

        # In-transit Devanning queue: list of (return_day, port, ctype, qty)
        self.devanning_queue: List[Tuple[int, str, ContainerType, int]] = []

        # Solve Master Plan for full baseline schedule
        self.milp_solver = CargoPilotMILPSolver(self.data)
        self.master_solution: MILPSolution = self.milp_solver.solve()

        # Cumulative financial tracking
        self.cumulative_hold_cost: float = 0.0
        self.cumulative_repo_cost: float = 0.0
        self.cumulative_lease_cost: float = 0.0

        # Booking state index
        self.booking_states: Dict[str, BookingSimulationState] = {}
        for b in self.data.bookings:
            dec = next((d for d in self.master_solution.booking_decisions if d.booking_id == b.booking_id), None)
            assigned_voy = None
            dep_day = None
            arr_day = None
            is_leased = False

            if dec:
                dep_day = dec.departure_day
                arr_day = dec.arrival_day
                is_leased = dec.leased_quantity > 0
                first_leg = next((l for l in self.data.voyage_legs if l.leg_id in dec.legs_traversed), None)
                if first_leg:
                    assigned_voy = first_leg.voyage_number

            self.booking_states[b.booking_id] = BookingSimulationState(
                booking_id=b.booking_id,
                origin_unlocode=b.origin_unlocode,
                destination_unlocode=b.destination_unlocode,
                container_type=b.container_type,
                quantity=b.quantity,
                priority=b.priority,
                status="REQUESTED",
                assigned_voyage_number=assigned_voy,
                departure_day=dep_day,
                expected_arrival_day=arr_day,
                actual_delivery_day=None,
                is_leased=is_leased,
            )

        # Initial Snapshot on Day 0
        self._record_snapshot(0, ["Simulation initialized. Ready for Day 0 dispatch."])

    def step(self) -> DaySimulationSnapshot:
        """Executes one simulation day advancement (t -> t+1)."""
        if self.current_day >= self.data.horizon_days:
            return self.history[-1]

        self.current_day += 1
        t = self.current_day
        day_alerts = []

        # 1. Devanning Returns Processing
        remaining_queue = []
        for ret_day, port, ctype, qty in self.devanning_queue:
            if ret_day == t:
                self.inventories[(port, ctype)] = self.inventories.get((port, ctype), 0.0) + qty
                day_alerts.append(f"Day {t}: Devanned {qty} x {ctype.value} returned to empty stock at {port}")
            else:
                remaining_queue.append((ret_day, port, ctype, qty))
        self.devanning_queue = remaining_queue

        # 2. Voyage Leg Departures & Arrivals
        daily_repo_cost = 0.0
        daily_lease_cost = 0.0

        for leg in self.data.voyage_legs:
            # Repositioning departures on day t
            if leg.departure_day == t:
                for rd in self.master_solution.repositioning_decisions:
                    if rd.leg_id == leg.leg_id:
                        self.inventories[(leg.from_port_unlocode, rd.container_type)] -= rd.quantity
                        daily_repo_cost += rd.cost
                        day_alerts.append(
                            f"Day {t}: Repositioned {rd.quantity} x {rd.container_type.value} departed {leg.from_port_unlocode} on {leg.voyage_number}"
                        )

            # Repositioning arrivals on day t
            if leg.arrival_day == t:
                for rd in self.master_solution.repositioning_decisions:
                    if rd.leg_id == leg.leg_id:
                        self.inventories[(leg.to_port_unlocode, rd.container_type)] += rd.quantity
                        day_alerts.append(
                            f"Day {t}: Repositioned {rd.quantity} x {rd.container_type.value} arrived {leg.to_port_unlocode} on {leg.voyage_number}"
                        )

        # 3. Booking Lifecycle Progression
        for b in self.data.bookings:
            b_state = self.booking_states[b.booking_id]
            dec = next((d for d in self.master_solution.booking_decisions if d.booking_id == b.booking_id), None)
            port_fx = self.data.ports[b.origin_unlocode]
            dest_fx = self.data.ports[b.destination_unlocode]

            # D - 1 (Cargo Ready Day)
            if t == b.cargo_ready_day and b_state.status == "REQUESTED":
                b_state.status = "CONFIRMED"
                day_alerts.append(f"Day {t}: Booking {b.booking_id} confirmed at {b.origin_unlocode}")

            # Departure Day (Loading & Sailing)
            if dec and t == dec.departure_day:
                b_state.status = "IN_TRANSIT"
                if dec.owned_quantity > 0:
                    self.inventories[(b.origin_unlocode, b.container_type)] -= dec.owned_quantity
                if dec.leased_quantity > 0:
                    daily_lease_cost += dec.fulfillment_cost
                    day_alerts.append(
                        f"Day {t}: Leased {dec.leased_quantity} x {b.container_type.value} for {b.booking_id} at {b.origin_unlocode}"
                    )
                day_alerts.append(f"Day {t}: Booking {b.booking_id} loaded and sailed from {b.origin_unlocode}")

            # Arrival Day (Discharge & Devanning Start)
            if dec and t == dec.arrival_day:
                b_state.status = "DELIVERED"
                b_state.actual_delivery_day = t
                day_alerts.append(f"Day {t}: Booking {b.booking_id} discharged at {b.destination_unlocode}")
                if dec.owned_quantity > 0:
                    devan_day = t + dest_fx.devanning_lead_time_days
                    self.devanning_queue.append((devan_day, b.destination_unlocode, b.container_type, dec.owned_quantity))

        # 4. Inventory Holding Costs on Day t
        daily_hold_cost = 0.0
        for (port_code, ctype), qty in self.inventories.items():
            unit_hold = self.data.holding_costs.get((port_code, ctype), 2.5)
            daily_hold_cost += max(0.0, qty) * unit_hold

        # Check safety stock violations
        for port_code, port_fx in self.data.ports.items():
            for ctype in self.data.container_types.keys():
                ss_target = port_fx.safety_stock_teu if ctype == ContainerType.DRY_20FT else int(port_fx.safety_stock_teu / 2)
                cur_qty = self.inventories.get((port_code, ctype), 0.0)
                if cur_qty < ss_target:
                    day_alerts.append(
                        f"Day {t}: Safety Stock Warning at {port_code} for {ctype.value} ({cur_qty:.0f} < {ss_target})"
                    )

        self.cumulative_hold_cost += daily_hold_cost
        self.cumulative_repo_cost += daily_repo_cost
        self.cumulative_lease_cost += daily_lease_cost

        return self._record_snapshot(t, day_alerts, daily_hold_cost, daily_repo_cost, daily_lease_cost)

    def _record_snapshot(
        self,
        t: int,
        alerts: List[str],
        daily_hold: float = 0.0,
        daily_repo: float = 0.0,
        daily_lease: float = 0.0,
    ) -> DaySimulationSnapshot:
        """Constructs an immutable state snapshot of the full world on day t including concrete dispatch orders."""
        sim_date = (self.data.base_date + timedelta(days=t)).isoformat()

        # Format port inventories
        port_invs: Dict[str, Dict[str, float]] = {}
        port_ss: Dict[str, int] = {}
        for port_code in self.data.ports.keys():
            port_invs[port_code] = {}
            port_ss[port_code] = self.data.ports[port_code].safety_stock_teu
            for ctype in self.data.container_types.keys():
                port_invs[port_code][ctype.value] = self.inventories.get((port_code, ctype), 0.0)

        # Vessel Positions
        vessel_states: List[VesselState] = []
        for v in self.data.vessels:
            active_leg = next(
                (l for l in self.data.voyage_legs if l.vessel_name == v.name and l.departure_day <= t <= l.arrival_day),
                None,
            )
            if active_leg:
                transit_len = max(1, active_leg.arrival_day - active_leg.departure_day)
                pct = min(1.0, max(0.0, (t - active_leg.departure_day) / transit_len))
                vessel_states.append(
                    VesselState(
                        vessel_name=v.name,
                        current_port=None if pct < 1.0 else active_leg.to_port_unlocode,
                        in_transit=pct < 1.0,
                        from_port=active_leg.from_port_unlocode,
                        to_port=active_leg.to_port_unlocode,
                        departure_day=active_leg.departure_day,
                        arrival_day=active_leg.arrival_day,
                        progress_pct=pct * 100.0,
                        teu_load=active_leg.booked_capacity_teu,
                        weight_load_mt=active_leg.booked_weight_mt,
                    )
                )
            else:
                last_leg = next(
                    (l for l in sorted(self.data.voyage_legs, key=lambda l: l.arrival_day, reverse=True)
                     if l.vessel_name == v.name and l.arrival_day <= t),
                    None,
                )
                port_at = last_leg.to_port_unlocode if last_leg else "CNSHA"
                vessel_states.append(
                    VesselState(
                        vessel_name=v.name,
                        current_port=port_at,
                        in_transit=False,
                        from_port=None,
                        to_port=None,
                        departure_day=None,
                        arrival_day=None,
                        progress_pct=0.0,
                        teu_load=0,
                        weight_load_mt=0.0,
                    )
                )

        # -------------------------------------------------------------
        # MATHEMATICAL OPERATIONAL DISPATCH DIRECTIVES FOR DAY t
        # -------------------------------------------------------------
        # 1. Booking Dispatch Directives
        booking_dispatch_directives: List[BookingDispatchDirective] = []
        for b in self.data.bookings:
            dec = next((d for d in self.master_solution.booking_decisions if d.booking_id == b.booking_id), None)
            b_state = self.booking_states.get(b.booking_id)
            if not dec:
                continue

            # Determine urgency and concrete operator command for day t
            if t == b.cargo_ready_day:
                urgency = "DISPATCH_NOW"
                source = f"{dec.owned_quantity} Owned Depot Units" if dec.owned_quantity > 0 else f"{dec.leased_quantity} Leased In Units"
                assigned_v = b_state.assigned_voyage_number if b_state else "scheduled voyage"
                action_instruction = (
                    f"RELEASE & COMMIT {b.quantity} × {b.container_type.value} ({source}) at {b.origin_unlocode}. "
                    f"Stage for loading onto {assigned_v} (Departs Day {dec.departure_day})."
                )
            elif t == dec.departure_day:
                urgency = "LOAD_VESSEL_TODAY"
                action_instruction = (
                    f"LOAD {b.quantity} × {b.container_type.value} onto vessel at {b.origin_unlocode} for departure today on {dec.selected_path_id}."
                )
            elif dec.departure_day < t < dec.arrival_day:
                urgency = "IN_TRANSIT"
                action_instruction = f"In transit to {b.destination_unlocode} (Expected arrival Day {dec.arrival_day})."
            elif t >= dec.arrival_day:
                urgency = "DELIVERED"
                action_instruction = f"Delivered at {b.destination_unlocode}. Containers entering turnaround devanning queue."
            else:
                urgency = "UPCOMING"
                action_instruction = f"Demand planned for Day {b.cargo_ready_day}. Hold empty equipment in yard."

            booking_dispatch_directives.append(
                BookingDispatchDirective(
                    booking_id=b.booking_id,
                    origin_port=b.origin_unlocode,
                    destination_port=b.destination_unlocode,
                    container_type=b.container_type.value,
                    total_quantity=b.quantity,
                    owned_quantity=dec.owned_quantity,
                    leased_quantity=dec.leased_quantity,
                    assigned_voyage=dec.legs_traversed[0] if dec.legs_traversed else "VOY",
                    departure_day=dec.departure_day,
                    arrival_day=dec.arrival_day,
                    urgency=urgency,
                    action_instruction=action_instruction,
                )
            )

        # 2. Empty Repositioning Directives across all 4 ports on Day t
        empty_reposition_directives: List[EmptyRepositionDirective] = []
        for port_code, port_fx in self.data.ports.items():
            departing_legs = [
                l for l in self.data.voyage_legs
                if l.from_port_unlocode == port_code and l.departure_day == t
            ]

            if not departing_legs:
                empty_reposition_directives.append(
                    EmptyRepositionDirective(
                        port_unlocode=port_code,
                        port_name=port_fx.name,
                        has_departing_vessel=False,
                        voyage_number=None,
                        leg_id=None,
                        destination_port=None,
                        should_load_empties=False,
                        reposition_quantities={"20FT_DRY": 0, "40FT_DRY": 0, "40FT_HIGH_CUBE": 0},
                        total_reposition_teu=0,
                        action_instruction="NO VESSEL DEPARTING TODAY. Maintain empty stock in yard depot.",
                    )
                )
            else:
                for d_leg in departing_legs:
                    repo_moves = [
                        rd for rd in self.master_solution.repositioning_decisions
                        if rd.leg_id == d_leg.leg_id
                    ]
                    repo_qtys = {"20FT_DRY": 0, "40FT_DRY": 0, "40FT_HIGH_CUBE": 0}
                    total_teu = 0
                    for rm in repo_moves:
                        repo_qtys[rm.container_type.value] = rm.quantity
                        c_spec = self.data.container_types[rm.container_type]
                        total_teu += int(rm.quantity * c_spec.teu_factor)

                    should_load = total_teu > 0
                    if should_load:
                        breakdown_str = ", ".join(f"{q} × {ct}" for ct, q in repo_qtys.items() if q > 0)
                        instr = (
                            f"ACTION REQUIRED: LOAD {total_teu} TEU EMPTY CONTAINERS ({breakdown_str}) onto {d_leg.voyage_number} "
                            f"(Leg {d_leg.leg_id}) departing {port_code} for {d_leg.to_port_unlocode}."
                        )
                    else:
                        instr = (
                            f"DO NOT LOAD EMPTIES onto {d_leg.voyage_number} today. "
                            f"Algorithm preserves all empty containers at {port_code} to fulfill upcoming bookings."
                        )

                    empty_reposition_directives.append(
                        EmptyRepositionDirective(
                            port_unlocode=port_code,
                            port_name=port_fx.name,
                            has_departing_vessel=True,
                            voyage_number=d_leg.voyage_number,
                            leg_id=d_leg.leg_id,
                            destination_port=d_leg.to_port_unlocode,
                            should_load_empties=should_load,
                            reposition_quantities=repo_qtys,
                            total_reposition_teu=total_teu,
                            action_instruction=instr,
                        )
                    )

        # 3. Port Daily Action Summaries for all 4 Ports
        port_action_summaries: List[PortDailyActionSummary] = []
        for port_code, port_fx in self.data.ports.items():
            p_inv = port_invs[port_code]
            total_teu = int(p_inv["20FT_DRY"] + p_inv["40FT_DRY"] * 2 + p_inv["40FT_HIGH_CUBE"] * 2)
            ss_target = port_fx.safety_stock_teu
            safety_status = "CRITICAL" if total_teu < ss_target / 2 else "WARNING" if total_teu < ss_target else "HEALTHY"

            # Calculate today's flow activities at this port
            outbound_laden = sum(
                bd.total_quantity for bd in booking_dispatch_directives
                if bd.origin_port == port_code and bd.departure_day == t
            )
            empty_repo_load = sum(
                erd.total_reposition_teu for erd in empty_reposition_directives
                if erd.port_unlocode == port_code
            )
            inbound_devan = sum(
                qty for ret_day, p, ctype, qty in self.devanning_queue
                if p == port_code and ret_day == t
            )
            leased_today = sum(
                bd.leased_quantity for bd in booking_dispatch_directives
                if bd.origin_port == port_code and bd.departure_day == t
            )

            # Recommend composite summary action
            if outbound_laden > 0 and empty_repo_load > 0:
                rec_action = f"DUAL DISPATCH: Load {outbound_laden} laden bookings + {empty_repo_load} TEU empties onto departing vessel."
            elif outbound_laden > 0:
                rec_action = f"LADEN DISPATCH: Gate & load {outbound_laden} laden bookings. Zero empty repositioning."
            elif empty_repo_load > 0:
                rec_action = f"EMPTY REPOSITION: Load {empty_repo_load} TEU empty containers to balance downstream ports."
            elif inbound_devan > 0:
                rec_action = f"INBOUND RECEIVING: Process {inbound_devan} devanned empty containers into usable yard inventory."
            else:
                rec_action = "YARD HOLDING: Maintain depot inventory. No vessel departures today."

            port_action_summaries.append(
                PortDailyActionSummary(
                    port_unlocode=port_code,
                    port_name=port_fx.name,
                    current_stock=p_inv,
                    total_stock_teu=total_teu,
                    safety_stock_teu=ss_target,
                    safety_status=safety_status,
                    outbound_laden_units=outbound_laden,
                    empty_reposition_load_units=empty_repo_load,
                    inbound_devanning_units=inbound_devan,
                    leased_units=leased_today,
                    recommended_action=rec_action,
                )
            )

        active_repos = [
            {
                "leg_id": rd.leg_id,
                "voyage_number": rd.voyage_number,
                "from_port": rd.from_port,
                "to_port": rd.to_port,
                "departure_day": rd.departure_day,
                "arrival_day": rd.arrival_day,
                "container_type": rd.container_type.value,
                "quantity": rd.quantity,
                "is_active": rd.departure_day <= t <= rd.arrival_day,
            }
            for rd in self.master_solution.repositioning_decisions
        ]

        total_cum_cost = (
            self.cumulative_hold_cost
            + self.cumulative_repo_cost
            + self.cumulative_lease_cost
        )

        snapshot = DaySimulationSnapshot(
            day=t,
            simulation_date=sim_date,
            port_inventories=port_invs,
            port_safety_stocks=port_ss,
            vessels=vessel_states,
            bookings=[copy.deepcopy(b) for b in self.booking_states.values()],
            active_repositions=active_repos,
            port_action_summaries=port_action_summaries,
            empty_reposition_directives=empty_reposition_directives,
            booking_dispatch_directives=booking_dispatch_directives,
            daily_holding_cost=daily_hold,
            daily_repositioning_cost=daily_repo,
            daily_leasing_cost=daily_lease,
            cumulative_total_cost=total_cum_cost,
            alerts=alerts,
        )
        self.history.append(snapshot)
        return snapshot

    def run_all(self) -> List[DaySimulationSnapshot]:
        """Runs the entire 40-day horizon sequentially."""
        while self.current_day < self.data.horizon_days:
            self.step()
        return self.history
