from dataclasses import dataclass, field
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Tuple, Optional
from app.db.enums import ContainerType, BookingPriority, LocationType, OperationalStatus, VesselType, VesselStatus, VoyageStatus


@dataclass(frozen=True)
class ContainerTypeSpec:
    container_type: ContainerType
    name: str
    teu_factor: float
    tare_weight_mt: float
    avg_cargo_weight_mt: float
    total_laden_weight_mt: float


@dataclass
class PortFixture:
    unlocode: str
    name: str
    country: str
    region: str
    latitude: float
    longitude: float
    storage_capacity_teu: int
    safety_stock_teu: int
    devanning_lead_time_days: int = 2
    lift_on_cost: float = 50.0
    lift_off_cost: float = 50.0


@dataclass
class VesselFixture:
    imo_number: str
    name: str
    vessel_type: VesselType
    container_capacity_teu: int
    deadweight_capacity_mt: float
    reefer_plugs: int = 100


@dataclass
class VoyageLegFixture:
    leg_id: str
    voyage_number: str
    vessel_name: str
    from_port_unlocode: str
    to_port_unlocode: str
    departure_day: int
    arrival_day: int
    transit_days: int
    capacity_teu: int
    capacity_weight_mt: float
    booked_capacity_teu: int = 0
    booked_weight_mt: float = 0.0


@dataclass
class BookingFixture:
    booking_id: str
    origin_unlocode: str
    destination_unlocode: str
    container_type: ContainerType
    quantity: int
    cargo_ready_day: int
    cutoff_day: int
    delivery_deadline_day: int
    priority: BookingPriority
    cargo_weight_mt: float = 15.0
    is_splittable: bool = False


@dataclass
class World1Data:
    base_date: date = date(2026, 8, 1)
    horizon_days: int = 40
    ports: Dict[str, PortFixture] = field(default_factory=dict)
    container_types: Dict[ContainerType, ContainerTypeSpec] = field(default_factory=dict)
    vessels: List[VesselFixture] = field(default_factory=list)
    voyage_legs: List[VoyageLegFixture] = field(default_factory=list)
    bookings: List[BookingFixture] = field(default_factory=list)
    initial_inventory: Dict[Tuple[str, ContainerType], int] = field(default_factory=dict)
    repositioning_costs: Dict[Tuple[str, str, ContainerType], float] = field(default_factory=dict)
    leasing_costs: Dict[Tuple[str, ContainerType], float] = field(default_factory=dict)
    holding_costs: Dict[Tuple[str, ContainerType], float] = field(default_factory=dict)
    shortage_penalties: Dict[BookingPriority, float] = field(default_factory=dict)
    safety_stock_penalty: float = 500.0


def get_world_1_dataset() -> World1Data:
    """Constructs the canonical, verified ground-truth dataset for Test World 1."""
    # 1. Container Specs
    container_types = {
        ContainerType.DRY_20FT: ContainerTypeSpec(
            container_type=ContainerType.DRY_20FT,
            name="20ft Standard Dry",
            teu_factor=1.0,
            tare_weight_mt=2.2,
            avg_cargo_weight_mt=12.0,
            total_laden_weight_mt=14.2,
        ),
        ContainerType.DRY_40FT: ContainerTypeSpec(
            container_type=ContainerType.DRY_40FT,
            name="40ft Standard Dry",
            teu_factor=2.0,
            tare_weight_mt=3.8,
            avg_cargo_weight_mt=18.0,
            total_laden_weight_mt=21.8,
        ),
        ContainerType.HIGH_CUBE_40FT: ContainerTypeSpec(
            container_type=ContainerType.HIGH_CUBE_40FT,
            name="40ft High Cube",
            teu_factor=2.0,
            tare_weight_mt=3.9,
            avg_cargo_weight_mt=17.0,
            total_laden_weight_mt=20.9,
        ),
    }

    # 2. Ports
    ports = {
        "CNSHA": PortFixture(
            unlocode="CNSHA",
            name="Port of Shanghai",
            country="China",
            region="East Asia",
            latitude=31.2304,
            longitude=121.4737,
            storage_capacity_teu=20000,
            safety_stock_teu=300,
            devanning_lead_time_days=2,
        ),
        "SGSIN": PortFixture(
            unlocode="SGSIN",
            name="Port of Singapore",
            country="Singapore",
            region="Southeast Asia",
            latitude=1.3521,
            longitude=103.8198,
            storage_capacity_teu=15000,
            safety_stock_teu=200,
            devanning_lead_time_days=2,
        ),
        "INMAA": PortFixture(
            unlocode="INMAA",
            name="Port of Chennai",
            country="India",
            region="South Asia",
            latitude=13.0827,
            longitude=80.2707,
            storage_capacity_teu=12000,
            safety_stock_teu=150,
            devanning_lead_time_days=2,
        ),
        "AEDXB": PortFixture(
            unlocode="AEDXB",
            name="Port of Jebel Ali (Dubai)",
            country="United Arab Emirates",
            region="Middle East",
            latitude=24.9857,
            longitude=55.0611,
            storage_capacity_teu=15000,
            safety_stock_teu=200,
            devanning_lead_time_days=2,
        ),
    }

    # 3. Vessels
    vessels = [
        VesselFixture(
            imo_number="IMO9812345",
            name="MV Pacific Trader",
            vessel_type=VesselType.CONTAINER_SHIP,
            container_capacity_teu=1200,
            deadweight_capacity_mt=18000.0,
            reefer_plugs=100,
        ),
        VesselFixture(
            imo_number="IMO9823456",
            name="MV Eastern Pioneer",
            vessel_type=VesselType.CONTAINER_SHIP,
            container_capacity_teu=1500,
            deadweight_capacity_mt=22500.0,
            reefer_plugs=150,
        ),
    ]

    # 4. Scheduled Voyage Legs (18 Legs across 6 Voyages over 40 Days)
    voyage_legs = [
        # Voyage 1 (VOY_A1): Vessel 1 Westbound Loop A
        VoyageLegFixture("LEG-A1-1", "VOY_A1", "MV Pacific Trader", "CNSHA", "SGSIN", 2, 7, 5, 1200, 18000.0),
        VoyageLegFixture("LEG-A1-2", "VOY_A1", "MV Pacific Trader", "SGSIN", "INMAA", 8, 12, 4, 1200, 18000.0),
        VoyageLegFixture("LEG-A1-3", "VOY_A1", "MV Pacific Trader", "INMAA", "AEDXB", 13, 18, 5, 1200, 18000.0),

        # Voyage 2 (VOY_B1): Vessel 2 Eastbound Loop B
        VoyageLegFixture("LEG-B1-1", "VOY_B1", "MV Eastern Pioneer", "AEDXB", "INMAA", 4, 9, 5, 1500, 22500.0),
        VoyageLegFixture("LEG-B1-2", "VOY_B1", "MV Eastern Pioneer", "INMAA", "SGSIN", 10, 14, 4, 1500, 22500.0),
        VoyageLegFixture("LEG-B1-3", "VOY_B1", "MV Eastern Pioneer", "SGSIN", "CNSHA", 15, 20, 5, 1500, 22500.0),

        # Voyage 3 (VOY_A2): Vessel 2 Westbound Loop A
        VoyageLegFixture("LEG-A2-1", "VOY_A2", "MV Eastern Pioneer", "CNSHA", "SGSIN", 16, 21, 5, 1500, 22500.0),
        VoyageLegFixture("LEG-A2-2", "VOY_A2", "MV Eastern Pioneer", "SGSIN", "INMAA", 22, 26, 4, 1500, 22500.0),
        VoyageLegFixture("LEG-A2-3", "VOY_A2", "MV Eastern Pioneer", "INMAA", "AEDXB", 27, 32, 5, 1500, 22500.0),

        # Voyage 4 (VOY_B2): Vessel 1 Eastbound Loop B
        VoyageLegFixture("LEG-B2-1", "VOY_B2", "MV Pacific Trader", "AEDXB", "INMAA", 20, 25, 5, 1200, 18000.0),
        VoyageLegFixture("LEG-B2-2", "VOY_B2", "MV Pacific Trader", "INMAA", "SGSIN", 26, 30, 4, 1200, 18000.0),
        VoyageLegFixture("LEG-B2-3", "VOY_B2", "MV Pacific Trader", "SGSIN", "CNSHA", 31, 36, 5, 1200, 18000.0),

        # Voyage 5 (VOY_A3): Vessel 1 Westbound Loop A
        VoyageLegFixture("LEG-A3-1", "VOY_A3", "MV Pacific Trader", "CNSHA", "SGSIN", 28, 33, 5, 1200, 18000.0),
        VoyageLegFixture("LEG-A3-2", "VOY_A3", "MV Pacific Trader", "SGSIN", "INMAA", 34, 38, 4, 1200, 18000.0),
        VoyageLegFixture("LEG-A3-3", "VOY_A3", "MV Pacific Trader", "INMAA", "AEDXB", 39, 44, 5, 1200, 18000.0),

        # Voyage 6 (VOY_B3): Vessel 2 Eastbound Loop B
        VoyageLegFixture("LEG-B3-1", "VOY_B3", "MV Eastern Pioneer", "AEDXB", "INMAA", 34, 39, 5, 1500, 22500.0),
        VoyageLegFixture("LEG-B3-2", "VOY_B3", "MV Eastern Pioneer", "INMAA", "SGSIN", 40, 44, 4, 1500, 22500.0),
        VoyageLegFixture("LEG-B3-3", "VOY_B3", "MV Eastern Pioneer", "SGSIN", "CNSHA", 45, 50, 5, 1500, 22500.0),
    ]

    # 5. Bookings (33 Bookings across 4 Ports sized for 85-99% Vessel Utilization)
    bookings = [
        # --- VOY_A1 Loadings (CNSHA dep D2, SGSIN dep D8, INMAA dep D13) ---
        BookingFixture("BK-01", "CNSHA", "AEDXB", ContainerType.DRY_40FT, 350, 1, 1, 20, BookingPriority.CRITICAL, cargo_weight_mt=12.0),
        BookingFixture("BK-02", "CNSHA", "INMAA", ContainerType.DRY_20FT, 250, 1, 1, 14, BookingPriority.HIGH, cargo_weight_mt=10.0),
        BookingFixture("BK-03", "CNSHA", "SGSIN", ContainerType.DRY_20FT, 150, 1, 2, 10, BookingPriority.NORMAL, cargo_weight_mt=11.0),
        BookingFixture("BK-06", "SGSIN", "INMAA", ContainerType.DRY_40FT, 120, 6, 7, 15, BookingPriority.HIGH, cargo_weight_mt=12.0),
        BookingFixture("BK-11", "INMAA", "AEDXB", ContainerType.DRY_40FT, 220, 11, 12, 20, BookingPriority.NORMAL, cargo_weight_mt=12.0),

        # --- VOY_B1 Loadings (AEDXB dep D4, INMAA dep D10, SGSIN dep D15) ---
        BookingFixture("BK-14", "AEDXB", "CNSHA", ContainerType.HIGH_CUBE_40FT, 400, 3, 3, 22, BookingPriority.NORMAL, cargo_weight_mt=11.0),
        BookingFixture("BK-15", "AEDXB", "INMAA", ContainerType.DRY_20FT, 350, 3, 4, 12, BookingPriority.HIGH, cargo_weight_mt=10.0),
        BookingFixture("BK-16", "AEDXB", "SGSIN", ContainerType.DRY_40FT, 125, 3, 4, 18, BookingPriority.LOW, cargo_weight_mt=12.0),
        BookingFixture("BK-10", "INMAA", "SGSIN", ContainerType.DRY_20FT, 180, 8, 9, 16, BookingPriority.HIGH, cargo_weight_mt=10.0),
        BookingFixture("BK-10B", "INMAA", "CNSHA", ContainerType.DRY_40FT, 100, 8, 9, 22, BookingPriority.NORMAL, cargo_weight_mt=11.0),
        BookingFixture("BK-07", "SGSIN", "CNSHA", ContainerType.DRY_20FT, 220, 13, 14, 22, BookingPriority.NORMAL, cargo_weight_mt=10.0),
        BookingFixture("BK-07B", "SGSIN", "CNSHA", ContainerType.HIGH_CUBE_40FT, 100, 13, 14, 22, BookingPriority.HIGH, cargo_weight_mt=11.0),

        # --- VOY_A2 Loadings (CNSHA dep D16, SGSIN dep D22, INMAA dep D27) ---
        BookingFixture("BK-04", "CNSHA", "AEDXB", ContainerType.HIGH_CUBE_40FT, 450, 14, 15, 34, BookingPriority.CRITICAL, cargo_weight_mt=11.0),
        BookingFixture("BK-04B", "CNSHA", "INMAA", ContainerType.DRY_20FT, 250, 14, 15, 28, BookingPriority.HIGH, cargo_weight_mt=10.0),
        BookingFixture("BK-04C", "CNSHA", "SGSIN", ContainerType.DRY_40FT, 125, 14, 15, 24, BookingPriority.NORMAL, cargo_weight_mt=11.0),
        BookingFixture("BK-08", "SGSIN", "AEDXB", ContainerType.HIGH_CUBE_40FT, 125, 20, 21, 34, BookingPriority.LOW, cargo_weight_mt=11.0),
        BookingFixture("BK-12", "INMAA", "AEDXB", ContainerType.HIGH_CUBE_40FT, 125, 24, 25, 34, BookingPriority.CRITICAL, cargo_weight_mt=11.0),

        # --- VOY_B2 Loadings (AEDXB dep D20, INMAA dep D26, SGSIN dep D31) ---
        BookingFixture("BK-17", "AEDXB", "CNSHA", ContainerType.DRY_20FT, 300, 18, 19, 38, BookingPriority.CRITICAL, cargo_weight_mt=10.0),
        BookingFixture("BK-17B", "AEDXB", "CNSHA", ContainerType.DRY_40FT, 200, 18, 19, 38, BookingPriority.HIGH, cargo_weight_mt=11.0),
        BookingFixture("BK-17C", "AEDXB", "INMAA", ContainerType.DRY_20FT, 200, 18, 19, 28, BookingPriority.NORMAL, cargo_weight_mt=10.0),
        BookingFixture("BK-17D", "AEDXB", "SGSIN", ContainerType.DRY_40FT, 100, 18, 19, 32, BookingPriority.LOW, cargo_weight_mt=11.0),
        BookingFixture("BK-12B", "INMAA", "CNSHA", ContainerType.HIGH_CUBE_40FT, 100, 24, 25, 38, BookingPriority.CRITICAL, cargo_weight_mt=11.0),
        BookingFixture("BK-09", "SGSIN", "CNSHA", ContainerType.DRY_40FT, 110, 29, 30, 38, BookingPriority.HIGH, cargo_weight_mt=11.0),

        # --- VOY_A3 Loadings (CNSHA dep D28, SGSIN dep D34, INMAA dep D39) ---
        BookingFixture("BK-05", "CNSHA", "INMAA", ContainerType.HIGH_CUBE_40FT, 300, 26, 27, 40, BookingPriority.CRITICAL, cargo_weight_mt=11.0),
        BookingFixture("BK-05B", "CNSHA", "AEDXB", ContainerType.DRY_40FT, 250, 26, 27, 44, BookingPriority.HIGH, cargo_weight_mt=11.0),
        BookingFixture("BK-09B", "SGSIN", "AEDXB", ContainerType.DRY_20FT, 30, 32, 33, 44, BookingPriority.NORMAL, cargo_weight_mt=10.0),
        BookingFixture("BK-13B", "INMAA", "AEDXB", ContainerType.DRY_40FT, 280, 37, 38, 44, BookingPriority.HIGH, cargo_weight_mt=11.0),

        # --- VOY_B3 Loadings (AEDXB dep D34, INMAA dep D40, SGSIN dep D45) ---
        BookingFixture("BK-18", "AEDXB", "INMAA", ContainerType.HIGH_CUBE_40FT, 250, 32, 33, 42, BookingPriority.NORMAL, cargo_weight_mt=11.0),
        BookingFixture("BK-18B", "AEDXB", "CNSHA", ContainerType.DRY_40FT, 350, 32, 33, 50, BookingPriority.HIGH, cargo_weight_mt=11.0),
        BookingFixture("BK-18C", "AEDXB", "SGSIN", ContainerType.DRY_20FT, 100, 32, 33, 46, BookingPriority.LOW, cargo_weight_mt=10.0),
        BookingFixture("BK-13", "INMAA", "SGSIN", ContainerType.DRY_20FT, 300, 38, 39, 46, BookingPriority.NORMAL, cargo_weight_mt=10.0),
        BookingFixture("BK-13C", "INMAA", "CNSHA", ContainerType.DRY_40FT, 150, 38, 39, 50, BookingPriority.HIGH, cargo_weight_mt=11.0),
        BookingFixture("BK-09C", "SGSIN", "CNSHA", ContainerType.HIGH_CUBE_40FT, 200, 43, 44, 50, BookingPriority.HIGH, cargo_weight_mt=11.0),
    ]

    # 6. Initial Inventories (t=0)
    initial_inventory = {
        ("CNSHA", ContainerType.DRY_20FT): 700,
        ("CNSHA", ContainerType.DRY_40FT): 800,
        ("CNSHA", ContainerType.HIGH_CUBE_40FT): 900,

        ("SGSIN", ContainerType.DRY_20FT): 400,
        ("SGSIN", ContainerType.DRY_40FT): 450,
        ("SGSIN", ContainerType.HIGH_CUBE_40FT): 400,

        ("INMAA", ContainerType.DRY_20FT): 500,
        ("INMAA", ContainerType.DRY_40FT): 450,
        ("INMAA", ContainerType.HIGH_CUBE_40FT): 350,

        ("AEDXB", ContainerType.DRY_20FT): 550,
        ("AEDXB", ContainerType.DRY_40FT): 600,
        ("AEDXB", ContainerType.HIGH_CUBE_40FT): 700,
    }

    # 7. Unit Costs ($/container)
    repositioning_costs = {}
    port_pairs = [
        ("CNSHA", "SGSIN", 50.0, 80.0, 85.0),
        ("SGSIN", "INMAA", 40.0, 65.0, 70.0),
        ("INMAA", "AEDXB", 50.0, 80.0, 85.0),
        ("AEDXB", "INMAA", 45.0, 70.0, 75.0),
        ("INMAA", "SGSIN", 40.0, 65.0, 70.0),
        ("SGSIN", "CNSHA", 50.0, 80.0, 85.0),
    ]
    for o, d, c20, c40, c40hc in port_pairs:
        repositioning_costs[(o, d, ContainerType.DRY_20FT)] = c20
        repositioning_costs[(o, d, ContainerType.DRY_40FT)] = c40
        repositioning_costs[(o, d, ContainerType.HIGH_CUBE_40FT)] = c40hc

    leasing_costs = {}
    for p in ports:
        leasing_costs[(p, ContainerType.DRY_20FT)] = 350.0 if p == "CNSHA" else 400.0
        leasing_costs[(p, ContainerType.DRY_40FT)] = 600.0 if p == "CNSHA" else 680.0
        leasing_costs[(p, ContainerType.HIGH_CUBE_40FT)] = 650.0 if p == "CNSHA" else 720.0

    holding_costs = {}
    for p in ports:
        holding_costs[(p, ContainerType.DRY_20FT)] = 2.0
        holding_costs[(p, ContainerType.DRY_40FT)] = 3.5
        holding_costs[(p, ContainerType.HIGH_CUBE_40FT)] = 3.8

    shortage_penalties = {
        BookingPriority.CRITICAL: 25000.0,
        BookingPriority.HIGH: 10000.0,
        BookingPriority.NORMAL: 3000.0,
        BookingPriority.LOW: 1000.0,
    }

    return World1Data(
        ports=ports,
        container_types=container_types,
        vessels=vessels,
        voyage_legs=voyage_legs,
        bookings=bookings,
        initial_inventory=initial_inventory,
        repositioning_costs=repositioning_costs,
        leasing_costs=leasing_costs,
        holding_costs=holding_costs,
        shortage_penalties=shortage_penalties,
        safety_stock_penalty=500.0,
    )
