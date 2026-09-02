import pytest
from app.test_worlds.world_1.fixtures import get_world_1_dataset
from app.optimization.milp_solver import CargoPilotMILPSolver
from app.optimization.network_builder import NetworkBuilder
from app.db.enums import ContainerType, BookingPriority


def test_world_1_network_candidate_paths():
    """Verify that the NetworkBuilder generates valid space-time candidate paths for all 8 bookings."""
    data = get_world_1_dataset()
    builder = NetworkBuilder(data)
    graph = builder.build_network()

    assert len(graph.ports) == 4
    assert len(graph.voyage_legs) == 18
    assert len(graph.booking_candidate_paths) == len(data.bookings)

    # Check each booking has at least one feasible candidate path
    for b in data.bookings:
        paths = graph.booking_candidate_paths.get(b.booking_id, [])
        assert len(paths) >= 1, f"Booking {b.booking_id} ({b.origin_unlocode} -> {b.destination_unlocode}) must have candidate paths"
        for p in paths:
            assert p.origin_unlocode == b.origin_unlocode
            assert p.destination_unlocode == b.destination_unlocode
            assert p.departure_day >= b.cargo_ready_day
            assert p.arrival_day <= b.delivery_deadline_day


def test_world_1_milp_solver_exact_mathematical_optimality():
    """Solve Test World 1 with the MILP Solver and verify exact mathematical properties."""
    data = get_world_1_dataset()
    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    # 1. Optimality check
    assert solution.solver_status == "Optimal", f"Expected Optimal status, got {solution.solver_status}"
    assert solution.optimality_gap == 0.0, f"Optimality gap must be exactly 0.0%, got {solution.optimality_gap}"
    assert solution.objective_value > 0.0, "Objective value must be strictly positive"

    # 2. Demand satisfaction check (Zero shortage on all 8 accepted bookings)
    assert solution.total_shortage_penalty == 0.0, "All bookings should be fulfilled with zero shortage penalties"
    assert len(solution.booking_decisions) >= 8

    total_fulfilled_by_booking = {}
    for bd in solution.booking_decisions:
        total_fulfilled_by_booking[bd.booking_id] = (
            total_fulfilled_by_booking.get(bd.booking_id, 0) + bd.owned_quantity + bd.leased_quantity
        )
        assert bd.unserved_quantity == 0

    for b in data.bookings:
        assert total_fulfilled_by_booking.get(b.booking_id, 0) == b.quantity, (
            f"Booking {b.booking_id} demanded {b.quantity}, fulfilled {total_fulfilled_by_booking.get(b.booking_id, 0)}"
        )

    # 3. Non-negative inventory check across all 4 ports, 3 container types, and 41 days
    assert len(solution.daily_inventories) == 4 * 3 * 41
    for snap in solution.daily_inventories:
        assert snap.ending_inventory >= -1e-5, f"Negative inventory on day {snap.day} at {snap.port_unlocode}"

    # 4. Voyage leg capacity constraints check
    # Recalculate total TEU and Weight on each leg
    for leg in data.voyage_legs:
        leg_teu_used = 0.0
        leg_weight_used = 0.0

        # Add cargo from booking decisions
        for bd in solution.booking_decisions:
            if leg.leg_id in bd.legs_traversed:
                c_spec = data.container_types[bd.container_type]
                units = bd.owned_quantity + bd.leased_quantity
                leg_teu_used += units * c_spec.teu_factor
                leg_weight_used += units * c_spec.total_laden_weight_mt

        # Add empty repositioning on this leg
        for rd in solution.repositioning_decisions:
            if rd.leg_id == leg.leg_id:
                c_spec = data.container_types[rd.container_type]
                leg_teu_used += rd.quantity * c_spec.teu_factor
                leg_weight_used += rd.quantity * c_spec.tare_weight_mt

        assert leg_teu_used <= leg.capacity_teu + 1e-4, f"Leg {leg.leg_id} exceeded TEU capacity: {leg_teu_used} > {leg.capacity_teu}"
        assert leg_weight_used <= leg.capacity_weight_mt + 1e-4, f"Leg {leg.leg_id} exceeded Weight capacity: {leg_weight_used} > {leg.capacity_weight_mt}"


def test_world_1_inventory_conservation_continuity():
    """Verify that daily inventory transitions strictly adhere to: I[t] = I[t-1] + Inflows - Outflows."""
    data = get_world_1_dataset()
    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    # Map inventories by (port, ctype, day)
    inv_map = {
        (s.port_unlocode, s.container_type, s.day): s.ending_inventory
        for s in solution.daily_inventories
    }

    for port_code, port_fx in data.ports.items():
        for ctype in data.container_types.keys():
            init_stock = data.initial_inventory.get((port_code, ctype), 0)

            for t in range(data.horizon_days + 1):
                # Calculate inflows at day t
                repo_in = sum(
                    rd.quantity for rd in solution.repositioning_decisions
                    if rd.to_port == port_code and rd.arrival_day == t and rd.container_type == ctype
                )
                devan_in = sum(
                    bd.owned_quantity for bd in solution.booking_decisions
                    if bd.container_type == ctype and bd.arrival_day + port_fx.devanning_lead_time_days == t
                    and any(leg.to_port_unlocode == port_code for leg in data.voyage_legs if leg.leg_id in bd.legs_traversed[-1:])
                )

                # Calculate outflows at day t
                repo_out = sum(
                    rd.quantity for rd in solution.repositioning_decisions
                    if rd.from_port == port_code and rd.departure_day == t and rd.container_type == ctype
                )
                booking_out = sum(
                    bd.owned_quantity for bd in solution.booking_decisions
                    if bd.container_type == ctype and bd.departure_day == t
                    and any(leg.from_port_unlocode == port_code for leg in data.voyage_legs if leg.leg_id in bd.legs_traversed[:1])
                )

                actual_inv = inv_map[(port_code, ctype, t)]
                prev_inv = init_stock if t == 0 else inv_map[(port_code, ctype, t - 1)]
                expected_inv = prev_inv + repo_in + devan_in - repo_out - booking_out

                assert abs(actual_inv - expected_inv) < 1e-4, (
                    f"Conservation violated at {port_code}, {ctype.value}, day {t}: "
                    f"actual={actual_inv}, expected={expected_inv} (prev={prev_inv}, in={repo_in+devan_in}, out={repo_out+booking_out})"
                )


def test_world_1_hand_check_decisions():
    """Hand-check and inspect key operational decisions made by the solver."""
    data = get_world_1_dataset()
    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    decisions_by_id = {bd.booking_id: bd for bd in solution.booking_decisions}

    # BK-01: 350 x 40DC Shanghai -> Dubai departing Day 2
    assert "BK-01" in decisions_by_id
    bk01 = decisions_by_id["BK-01"]
    assert bk01.owned_quantity == 350
    assert bk01.departure_day == 2
    assert bk01.arrival_day == 18

    # BK-02: 250 x 20DC Shanghai -> Chennai departing Day 2 (fulfilled by owned + leased)
    assert "BK-02" in decisions_by_id
    bk02 = decisions_by_id["BK-02"]
    assert bk02.owned_quantity + bk02.leased_quantity == 250
    assert bk02.departure_day == 2
    assert bk02.arrival_day == 12

    # Check that total holding cost is calculated accurately
    assert solution.total_holding_cost > 0.0
    assert solution.total_shortage_penalty == 0.0


def test_scenario_capacity_bottleneck():
    """Stress test: Severely bottleneck Leg A1-1 capacity to 700 TEU and verify priority protection."""
    data = get_world_1_dataset()
    # Modify Leg A1-1 capacity to 700 TEU (BK-01 needs 700 TEU, BK-02 needs 250 TEU = 950 TEU total)
    for leg in data.voyage_legs:
        if leg.leg_id == "LEG-A1-1":
            leg.capacity_teu = 700

    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    assert solution.solver_status == "Optimal"
    decisions = {bd.booking_id: bd for bd in solution.booking_decisions}

    # Tier 1 Critical (BK-01) must receive priority over Tier 2 (BK-02)
    assert decisions["BK-01"].owned_quantity == 350, "BK-01 (Tier 1 Critical) must be fully fulfilled"


def test_scenario_demand_surge_with_leasing_tradeoff():
    """Stress test: Inject 800 TEU demand surge at Dubai where local inventory is only 50."""
    data = get_world_1_dataset()
    from app.test_worlds.world_1.fixtures import BookingFixture
    # Constrain Dubai local owned stock to 50 to force leasing for surge demand
    data.initial_inventory[("AEDXB", ContainerType.DRY_40FT)] = 50
    # Inject surge booking at Dubai (400 x 40FT = 800 TEU, fits within remaining vessel capacity)
    data.bookings.append(
        BookingFixture(
            booking_id="BK-SURGE",
            origin_unlocode="AEDXB",
            destination_unlocode="CNSHA",
            container_type=ContainerType.DRY_40FT,
            quantity=400,
            cargo_ready_day=4,
            cutoff_day=4,
            delivery_deadline_day=22,
            priority=BookingPriority.HIGH,
        )
    )

    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    assert solution.solver_status == "Optimal"
    decisions = {bd.booking_id: bd for bd in solution.booking_decisions}
    assert "BK-SURGE" in decisions
    surge_dec = decisions["BK-SURGE"]
    # Should use available owned inventory (up to 50) and lease the remainder locally in Dubai!
    assert surge_dec.owned_quantity + surge_dec.leased_quantity == 400
    assert surge_dec.leased_quantity > 0, "Solver should economically lease locally to satisfy Dubai demand surge"
    assert solution.total_leasing_cost > 0.0


def test_scenario_blank_sailing():
    """Stress test: Blank sailing on VOY_A2 (Legs A2-1, A2-2, A2-3) and verify demand rerouting / shortage detection."""
    data = get_world_1_dataset()
    # Cancel VOY_A2 legs by setting capacity to 0
    for leg in data.voyage_legs:
        if leg.voyage_number == "VOY_A2":
            leg.capacity_teu = 0

    # Allow BK-05 to take subsequent voyage VOY_A3 (arrives Day 44) by adjusting delivery deadline to 46
    for b in data.bookings:
        if b.booking_id == "BK-05":
            b.delivery_deadline_day = 46

    solver = CargoPilotMILPSolver(data)
    solution = solver.solve(time_limit_seconds=30.0)

    assert solution.solver_status == "Optimal"
    decisions = {bd.booking_id: bd for bd in solution.booking_decisions}
    # BK-05 should roll to VOY_A3 (departs Day 28) since VOY_A2 is blanked
    assert "BK-05" in decisions
    assert decisions["BK-05"].departure_day >= 28, "BK-05 should roll to VOY_A3 due to blank sailing on VOY_A2"

