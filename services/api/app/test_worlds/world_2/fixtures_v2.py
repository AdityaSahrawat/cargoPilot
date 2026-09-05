"""
CargoPilot Test World 2 — Full-Scale Global Fixture
====================================================
Implements EVERY parameter, variable seed, and dataset described in the
CargoPilot documentation that was missing from Test World 1.

Scale:
  - 55 ports (global network)
  - 18 vessels (ULCV to feeder)
  - 5 container types (20DC, 40DC, 40HC, REEFER_40FT, DRY_45FT)
  - 18 service lines with recurring rotations (383+ legs over 84-day horizon)
  - ~190 bookings (auto-generated from service patterns)
  - 12 weeks of historical data baked in
  - Full forecast parameters (D, R, G, μ, σ)
  - Precomputed safety stocks SS[i,k,t]
  - Long-term and short-term lease caps
  - Storage capacity per port/type
  - Handling costs (lift-on / lift-off)
  - Booking delay penalties
"""

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Tuple, Optional

from app.test_worlds.world_1.fixtures import (
    ContainerTypeSpec,
    PortFixture,
    VesselFixture,
    VoyageLegFixture,
    BookingFixture,
)
from app.db.enums import ContainerType, BookingPriority, VesselType


# ============================================================
# WORLD-2 DATA CONTAINER
# ============================================================

@dataclass
class World2Data:
    """Superset of World1Data — adds all missing MILP parameters from documentation."""

    # ── shared with World1 ──────────────────────────────────────────────────
    base_date: date
    horizon_days: int  # 84 days (12 weeks)
    ports: Dict[str, PortFixture]
    container_types: Dict[ContainerType, ContainerTypeSpec]
    vessels: List[VesselFixture]
    voyage_legs: List[VoyageLegFixture]
    bookings: List[BookingFixture]
    initial_inventory: Dict[Tuple[str, ContainerType], int]
    repositioning_costs: Dict[Tuple[str, str, ContainerType], float]
    leasing_costs: Dict[Tuple[str, ContainerType], float]        # short-term per container
    holding_costs: Dict[Tuple[str, ContainerType], float]        # per container per day
    shortage_penalties: Dict[BookingPriority, float]
    safety_stock_penalty: float                                   # global fallback scalar

    # ── NEW: extended cost parameters ──────────────────────────────────────
    leasing_costs_long: Dict[Tuple[str, ContainerType], float]   # c^long  [i,k] per container per day
    lift_on_costs: Dict[Tuple[str, ContainerType], float]        # c^load  [i,k]
    lift_off_costs: Dict[Tuple[str, ContainerType], float]       # c^unload[i,k]
    delay_penalties: Dict[str, float]                             # c^delay [booking_id] per day late

    # ── NEW: forecast parameters (enter MILP as fixed RHS values) ──────────
    demand_forecast: Dict[Tuple[str, ContainerType, int], float]    # D[i,k,t]
    return_forecast: Dict[Tuple[str, ContainerType, int], float]    # R[i,k,t]
    in_transit_pipeline: Dict[Tuple[str, ContainerType, int], int]  # G[i,k,t]

    # ── NEW: forecast error statistics (used to precompute SS) ─────────────
    demand_error_mean: Dict[Tuple[str, ContainerType, int], float]  # μ^D[i,k,t]
    demand_error_std: Dict[Tuple[str, ContainerType, int], float]   # σ^D[i,k,t]
    return_error_mean: Dict[Tuple[str, ContainerType, int], float]  # μ^R[i,k,t]
    return_error_std: Dict[Tuple[str, ContainerType, int], float]   # σ^R[i,k,t]

    # ── NEW: precomputed safety stocks SS[i,k,t] ───────────────────────────
    # SS = z_alpha * sqrt(lead_time * σ_D² + μ_D² * σ_vessel² + σ_R²)
    safety_stocks: Dict[Tuple[str, ContainerType, int], float]

    # ── NEW: lease availability caps ───────────────────────────────────────
    lease_cap_short: Dict[Tuple[str, ContainerType], int]           # total containers per horizon
    lease_cap_long: Dict[Tuple[str, ContainerType, int], int]       # containers injectable per period

    # ── NEW: storage capacity  (enforced as I ≤ StorageCap) ───────────────
    storage_capacity: Dict[Tuple[str, ContainerType], int]

    # ── NEW: 12 weeks of pre-simulation historical data ────────────────────
    # Keys use negative day indices: t ∈ {-84, -77, ..., -7} (weekly)
    historical_demand: Dict[Tuple[str, ContainerType, int], float]
    historical_returns: Dict[Tuple[str, ContainerType, int], float]
    historical_inventory: Dict[Tuple[str, ContainerType, int], float]


# ============================================================
# CONSTANTS — PORT TIERS, REGIONS, TYPE SHARES
# ============================================================

# Normalised throughput tier [0,1]
_PORT_TIER: Dict[str, float] = {
    "CNSHA": 1.00, "SGSIN": 1.00, "NLRTM": 0.95, "USLAX": 0.90, "AEDXB": 0.88,
    "CNNGB": 0.82, "CNTAO": 0.78, "HKHKG": 0.80, "KRPUS": 0.80, "DEHAM": 0.82,
    "BEANR": 0.75, "USNYC": 0.75, "GBFXT": 0.70, "TWKHH": 0.70, "CNGUZ": 0.65,
    "CNSZX": 0.76, "JPTYO": 0.65, "JPOSA": 0.60, "MYPKG": 0.60, "LKCMB": 0.58,
    "INMAA": 0.55, "INBOM": 0.57, "THBKK": 0.54, "EGPSD": 0.55, "FRLEH": 0.52,
    "USSAV": 0.55, "USHOU": 0.58, "GRPIR": 0.50, "ESBCN": 0.50, "ITGOA": 0.45,
    "PLGDY": 0.45, "MYPEN": 0.40, "BRSSZ": 0.45, "VNHPH": 0.38, "VNSAG": 0.40,
    "IDJKT": 0.48, "PHMNL": 0.46, "BDCGP": 0.38, "INHAL": 0.40, "PKKAR": 0.38,
    "MAPTM": 0.35, "NGAPP": 0.35, "KEYSM": 0.28, "ZADUR": 0.34, "OMPOR": 0.24,
    "IQUMQ": 0.22, "SADAM": 0.28, "IQBAS": 0.22, "KWKWI": 0.24, "AUMEL": 0.46,
    "AUSYD": 0.42, "NZAKL": 0.34, "BRVIX": 0.24, "COBUN": 0.22, "PAMIT": 0.30,
}

_PORT_REGION: Dict[str, str] = {
    "CNSHA": "ASIA", "CNNGB": "ASIA", "CNTAO": "ASIA", "CNSZX": "ASIA",
    "CNGUZ": "ASIA", "HKHKG": "ASIA", "TWKHH": "ASIA", "KRPUS": "ASIA",
    "JPTYO": "ASIA", "JPOSA": "ASIA", "SGSIN": "ASIA", "MYPEN": "ASIA",
    "MYPKG": "ASIA", "THBKK": "ASIA", "VNHPH": "ASIA", "VNSAG": "ASIA",
    "IDJKT": "ASIA", "PHMNL": "ASIA", "LKCMB": "SOUTH_ASIA", "BDCGP": "SOUTH_ASIA",
    "INMAA": "SOUTH_ASIA", "INBOM": "SOUTH_ASIA", "INHAL": "SOUTH_ASIA", "PKKAR": "SOUTH_ASIA",
    "AEDXB": "MIDEAST", "OMPOR": "MIDEAST", "IQUMQ": "MIDEAST",
    "SADAM": "MIDEAST", "IQBAS": "MIDEAST", "KWKWI": "MIDEAST",
    "EGPSD": "AFRICA", "ZADUR": "AFRICA", "NGAPP": "AFRICA",
    "KEYSM": "AFRICA", "MAPTM": "AFRICA",
    "NLRTM": "EUROPE", "DEHAM": "EUROPE", "GBFXT": "EUROPE", "BEANR": "EUROPE",
    "ESBCN": "EUROPE", "ITGOA": "EUROPE", "GRPIR": "EUROPE", "FRLEH": "EUROPE", "PLGDY": "EUROPE",
    "USLAX": "AMERICAS", "USNYC": "AMERICAS", "USSAV": "AMERICAS", "USHOU": "AMERICAS",
    "BRVIX": "AMERICAS", "BRSSZ": "AMERICAS", "PAMIT": "AMERICAS", "COBUN": "AMERICAS",
    "AUMEL": "OCEANIA", "AUSYD": "OCEANIA", "NZAKL": "OCEANIA",
}

# Container type demand share per region [ctype -> fraction]
_TYPE_SHARE: Dict[str, Dict[ContainerType, float]] = {
    "ASIA":       {ContainerType.DRY_40FT: 0.38, ContainerType.HIGH_CUBE_40FT: 0.34,
                   ContainerType.DRY_20FT: 0.21, ContainerType.REEFER_40FT: 0.05, ContainerType.DRY_45FT: 0.02},
    "SOUTH_ASIA": {ContainerType.DRY_40FT: 0.42, ContainerType.HIGH_CUBE_40FT: 0.24,
                   ContainerType.DRY_20FT: 0.28, ContainerType.REEFER_40FT: 0.04, ContainerType.DRY_45FT: 0.02},
    "MIDEAST":    {ContainerType.DRY_40FT: 0.45, ContainerType.HIGH_CUBE_40FT: 0.22,
                   ContainerType.DRY_20FT: 0.28, ContainerType.REEFER_40FT: 0.04, ContainerType.DRY_45FT: 0.01},
    "AFRICA":     {ContainerType.DRY_40FT: 0.40, ContainerType.HIGH_CUBE_40FT: 0.18,
                   ContainerType.DRY_20FT: 0.36, ContainerType.REEFER_40FT: 0.05, ContainerType.DRY_45FT: 0.01},
    "EUROPE":     {ContainerType.DRY_40FT: 0.42, ContainerType.HIGH_CUBE_40FT: 0.32,
                   ContainerType.DRY_20FT: 0.15, ContainerType.REEFER_40FT: 0.08, ContainerType.DRY_45FT: 0.03},
    "AMERICAS":   {ContainerType.DRY_40FT: 0.48, ContainerType.HIGH_CUBE_40FT: 0.28,
                   ContainerType.DRY_20FT: 0.14, ContainerType.REEFER_40FT: 0.08, ContainerType.DRY_45FT: 0.02},
    "OCEANIA":    {ContainerType.DRY_40FT: 0.44, ContainerType.HIGH_CUBE_40FT: 0.30,
                   ContainerType.DRY_20FT: 0.12, ContainerType.REEFER_40FT: 0.12, ContainerType.DRY_45FT: 0.02},
}

# Base daily demand containers for a tier-1 port (multiplied by tier and share)
_BASE_DAILY_DEMAND = 25.0

# Service-level factor for safety stock (95%)
_Z_ALPHA = 1.645

# Vessel arrival time uncertainty (std dev in days)
_SIGMA_VESSEL = 1.5


# ============================================================
# VESSEL SPECS: (TEU capacity, deadweight MT)
# ============================================================
_VESSEL_SPECS: Dict[str, Tuple[int, float]] = {
    "MV Ever Quantum":       (20000, 60000.0),
    "MV Asia Colossus":      (18000, 54000.0),
    "MV Pacific Titan":      (14000, 42000.0),
    "MV Eastern Giant":      (13500, 40500.0),
    "MV Global Express":     (12000, 36000.0),
    "MV Ocean Pioneer":      (11500, 34500.0),
    "MV Atlantic Bridge":    (8500,  25500.0),
    "MV Mediterranean Star": (8000,  24000.0),
    "MV Indian Ocean":       (7500,  22500.0),
    "MV Southern Cross":     (6800,  20400.0),
    "MV Pacific Trader":     (6000,  18000.0),
    "MV Eastern Pioneer":    (5500,  16500.0),
    "MV Silk Road":          (3500,  10500.0),
    "MV Pearl River":        (3200,   9600.0),
    "MV Bengal Star":        (2800,   8400.0),
    "MV Malabar Express":    (2500,   7500.0),
    "MV Arabian Falcon":     (2200,   6600.0),
    "MV Cape Trader":        (2000,   6000.0),
}

def _vessel_type(teu: int) -> VesselType:
    if teu >= 15000: return VesselType.ULCV
    if teu >= 8000:  return VesselType.POST_PANAMAX
    if teu >= 4000:  return VesselType.PANAMAX
    if teu >= 2000:  return VesselType.CONTAINER_SHIP
    return VesselType.FEEDER


# ============================================================
# SERVICE TEMPLATES
# Each route entry: (port_unlocode, offset_days_from_start_of_rotation)
# Legs are generated between consecutive ports.
# ============================================================
_SERVICES: Dict[str, dict] = {
    # ── Asia ↔ Europe ──────────────────────────────────────────────────────
    "AEX1": {
        "vessel": "MV Ever Quantum",
        "first_start": 3, "cycle": 30, "rotations": 3,
        "pre_booked_frac": 0.30,
        "route": [("CNSHA",0),("CNNGB",1),("KRPUS",4),("SGSIN",9),
                  ("LKCMB",12),("EGPSD",20),("NLRTM",27),("DEHAM",28),("BEANR",29)],
    },
    "AEX2": {
        "vessel": "MV Asia Colossus",
        "first_start": 10, "cycle": 29, "rotations": 3,
        "pre_booked_frac": 0.28,
        "route": [("CNTAO",0),("CNSHA",1),("HKHKG",3),("CNSZX",4),("MYPKG",7),
                  ("LKCMB",10),("EGPSD",18),("GBFXT",24),("NLRTM",25),("FRLEH",26)],
    },
    # ── Transpacific ───────────────────────────────────────────────────────
    "TPX1": {
        "vessel": "MV Pacific Titan",
        "first_start": 2, "cycle": 18, "rotations": 5,
        "pre_booked_frac": 0.32,
        "route": [("CNSHA",0),("CNNGB",1),("CNTAO",3),("HKHKG",5),("TWKHH",7),("USLAX",17)],
    },
    "TPX2": {
        "vessel": "MV Eastern Giant",
        "first_start": 20, "cycle": 18, "rotations": 4,
        "pre_booked_frac": 0.30,
        "route": [("KRPUS",0),("TWKHH",2),("PHMNL",4),("USLAX",14),("USNYC",17)],
    },
    "TPX3": {
        "vessel": "MV Pacific Trader",
        "first_start": 50, "cycle": 17, "rotations": 2,
        "pre_booked_frac": 0.25,
        "route": [("USLAX",0),("TWKHH",10),("KRPUS",13),("CNSHA",15),("CNNGB",16)],
    },
    # ── Asia ↔ Middle East ─────────────────────────────────────────────────
    "AME1": {
        "vessel": "MV Global Express",
        "first_start": 1, "cycle": 22, "rotations": 4,
        "pre_booked_frac": 0.30,
        "route": [("CNSHA",0),("SGSIN",5),("LKCMB",8),("INMAA",11),("INBOM",14),("AEDXB",20)],
    },
    "AME2": {
        "vessel": "MV Ocean Pioneer",
        "first_start": 28, "cycle": 21, "rotations": 3,
        "pre_booked_frac": 0.28,
        "route": [("CNGUZ",0),("HKHKG",1),("SGSIN",4),("MYPKG",7),("LKCMB",10),("PKKAR",16),("AEDXB",20)],
    },
    # ── Intra Asia Feeders ─────────────────────────────────────────────────
    "IAF1": {
        "vessel": "MV Silk Road",
        "first_start": 2, "cycle": 17, "rotations": 5,
        "pre_booked_frac": 0.22,
        "route": [("SGSIN",0),("IDJKT",2),("PHMNL",5),("VNSAG",8),("THBKK",11),("MYPEN",14),("SGSIN",16)],
    },
    "IAF2": {
        "vessel": "MV Pearl River",
        "first_start": 22, "cycle": 15, "rotations": 4,
        "pre_booked_frac": 0.20,
        "route": [("SGSIN",0),("VNHPH",3),("THBKK",6),("MYPEN",9),("MYPKG",12),("SGSIN",14)],
    },
    # ── Europe ↔ Americas ─────────────────────────────────────────────────
    "EAX1": {
        "vessel": "MV Atlantic Bridge",
        "first_start": 5, "cycle": 18, "rotations": 5,
        "pre_booked_frac": 0.28,
        "route": [("NLRTM",0),("DEHAM",1),("BEANR",2),("GBFXT",3),("USNYC",12),("USSAV",14),("USHOU",17)],
    },
    "EAX2": {
        "vessel": "MV Mediterranean Star",
        "first_start": 35, "cycle": 29, "rotations": 2,
        "pre_booked_frac": 0.26,
        "route": [("NLRTM",0),("FRLEH",1),("ESBCN",4),("ITGOA",6),("GRPIR",9),
                  ("EGPSD",12),("BRSSZ",22),("BRVIX",23),("COBUN",27)],
    },
    # ── Africa ─────────────────────────────────────────────────────────────
    "AFX1": {
        "vessel": "MV Cape Trader",
        "first_start": 8, "cycle": 42, "rotations": 2,
        "pre_booked_frac": 0.20,
        "route": [("EGPSD",0),("MAPTM",4),("NGAPP",12),("KEYSM",17),("ZADUR",22),
                  ("KEYSM",26),("NGAPP",31),("MAPTM",37),("EGPSD",41)],
    },
    # ── South Asia Feeders ─────────────────────────────────────────────────
    "SAF1": {
        "vessel": "MV Bengal Star",
        "first_start": 5, "cycle": 21, "rotations": 4,
        "pre_booked_frac": 0.22,
        "route": [("LKCMB",0),("BDCGP",4),("INMAA",8),("INBOM",12),("PKKAR",17),("AEDXB",20)],
    },
    "SAF2": {
        "vessel": "MV Malabar Express",
        "first_start": 30, "cycle": 17, "rotations": 3,
        "pre_booked_frac": 0.20,
        "route": [("AEDXB",0),("PKKAR",4),("INBOM",8),("INMAA",12),("LKCMB",16)],
    },
    # ── Oceania ────────────────────────────────────────────────────────────
    "OCX1": {
        "vessel": "MV Southern Cross",
        "first_start": 10, "cycle": 42, "rotations": 2,
        "pre_booked_frac": 0.24,
        "route": [("SGSIN",0),("PHMNL",4),("AUMEL",14),("AUSYD",17),("NZAKL",21),
                  ("AUSYD",25),("AUMEL",28),("PHMNL",37),("SGSIN",41)],
    },
    # ── Middle East Gulf ───────────────────────────────────────────────────
    "MEF1": {
        "vessel": "MV Arabian Falcon",
        "first_start": 3, "cycle": 16, "rotations": 5,
        "pre_booked_frac": 0.18,
        "route": [("AEDXB",0),("IQUMQ",3),("SADAM",6),("KWKWI",9),("IQBAS",12),("AEDXB",16)],
    },
    # ── West Europe Loop ───────────────────────────────────────────────────
    "WEX1": {
        "vessel": "MV Indian Ocean",
        "first_start": 15, "cycle": 20, "rotations": 4,
        "pre_booked_frac": 0.24,
        "route": [("NLRTM",0),("DEHAM",1),("PLGDY",3),("GBFXT",5),("BEANR",6),
                  ("ESBCN",10),("ITGOA",14),("GRPIR",19)],
    },
    # ── South America ──────────────────────────────────────────────────────
    "SAM1": {
        "vessel": "MV Eastern Pioneer",
        "first_start": 20, "cycle": 24, "rotations": 3,
        "pre_booked_frac": 0.22,
        "route": [("USNYC",0),("USSAV",2),("USHOU",5),("PAMIT",9),("BRSSZ",18),("BRVIX",20),("COBUN",23)],
    },
}

# Booking patterns per service:
# (origin, destination, ctype, qty, priority_str, cargo_offset_before_departure)
_BOOKING_PATTERNS: Dict[str, List[tuple]] = {
    # ──────────────────────────────────────────────────────────────────────────
    # AEX1  MV Ever Quantum 20,000 TEU  |  China → Europe  (70% pre+bk target)
    # Free after pre-booked: ~14,000 TEU per leg → load ~9,000 TEU in bookings
    # ──────────────────────────────────────────────────────────────────────────
    "AEX1": [
        ("CNSHA", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 1800, "CRITICAL", 3),  # 3,600 TEU
        ("CNSHA", "DEHAM",  ContainerType.HIGH_CUBE_40FT, 1400, "CRITICAL", 3),  # 2,800 TEU
        ("CNSHA", "BEANR",  ContainerType.DRY_40FT,       1200, "HIGH",     2),  # 2,400 TEU
        ("CNSHA", "GBFXT",  ContainerType.DRY_20FT,       1500, "HIGH",     2),  # 1,500 TEU
        ("KRPUS", "NLRTM",  ContainerType.DRY_40FT,        800, "HIGH",     2),  # 1,600 TEU
        ("KRPUS", "DEHAM",  ContainerType.HIGH_CUBE_40FT,  600, "NORMAL",   2),  # 1,200 TEU
        ("CNNGB", "NLRTM",  ContainerType.DRY_40FT,        900, "HIGH",     2),  # 1,800 TEU
        ("SGSIN", "DEHAM",  ContainerType.HIGH_CUBE_40FT,  400, "NORMAL",   2),  #   800 TEU
        ("HKHKG", "NLRTM",  ContainerType.DRY_40FT,        500, "NORMAL",   2),  # 1,000 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # AEX2  MV Asia Colossus 18,000 TEU  |  China → Europe  (72% target)
    # Free: ~13,000 TEU per leg → book ~9,400 TEU
    # ──────────────────────────────────────────────────────────────────────────
    "AEX2": [
        ("CNTAO", "NLRTM",  ContainerType.DRY_40FT,       1600, "HIGH",     3),  # 3,200 TEU
        ("CNSHA", "GBFXT",  ContainerType.HIGH_CUBE_40FT, 1400, "CRITICAL", 3),  # 2,800 TEU
        ("CNGUZ", "DEHAM",  ContainerType.DRY_40FT,       1100, "HIGH",     2),  # 2,200 TEU
        ("HKHKG", "NLRTM",  ContainerType.DRY_20FT,       1200, "NORMAL",   2),  # 1,200 TEU
        ("MYPKG", "GBFXT",  ContainerType.DRY_40FT,        700, "NORMAL",   2),  # 1,400 TEU
        ("LKCMB", "FRLEH",  ContainerType.HIGH_CUBE_40FT,  600, "HIGH",     2),  # 1,200 TEU
        ("CNNGB", "BEANR",  ContainerType.HIGH_CUBE_40FT,  700, "HIGH",     2),  # 1,400 TEU
        ("SGSIN", "NLRTM",  ContainerType.DRY_40FT,        500, "NORMAL",   2),  # 1,000 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # TPX1  MV Pacific Titan 14,000 TEU  |  China → US West Coast  (80% target)
    # Free: ~9,520 TEU → book ~6,720 TEU  — OVERBOOKED: forces leasing
    # ──────────────────────────────────────────────────────────────────────────
    "TPX1": [
        ("CNSHA", "USLAX",  ContainerType.HIGH_CUBE_40FT, 1800, "CRITICAL", 3),  # 3,600 TEU
        ("CNSHA", "USNYC",  ContainerType.HIGH_CUBE_40FT, 1200, "CRITICAL", 3),  # 2,400 TEU
        ("CNNGB", "USLAX",  ContainerType.DRY_40FT,       1100, "HIGH",     2),  # 2,200 TEU
        ("CNTAO", "USLAX",  ContainerType.DRY_40FT,        900, "HIGH",     2),  # 1,800 TEU
        ("HKHKG", "USLAX",  ContainerType.DRY_20FT,        800, "NORMAL",   2),  #   800 TEU
        ("KRPUS", "USLAX",  ContainerType.DRY_40FT,        700, "HIGH",     2),  # 1,400 TEU
        ("CNSHA", "USLAX",  ContainerType.REEFER_40FT,     350, "CRITICAL", 3),  #   700 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # TPX2  MV Eastern Giant 13,500 TEU  |  NE Asia → US  (78% target)
    # ──────────────────────────────────────────────────────────────────────────
    "TPX2": [
        ("KRPUS", "USLAX",  ContainerType.DRY_40FT,       1600, "HIGH",     2),  # 3,200 TEU
        ("TWKHH", "USNYC",  ContainerType.HIGH_CUBE_40FT, 1200, "CRITICAL", 2),  # 2,400 TEU
        ("JPTYO", "USLAX",  ContainerType.DRY_40FT,        900, "HIGH",     2),  # 1,800 TEU
        ("JPOSA", "USLAX",  ContainerType.HIGH_CUBE_40FT,  700, "NORMAL",   2),  # 1,400 TEU
        ("PHMNL", "USLAX",  ContainerType.DRY_20FT,        600, "NORMAL",   2),  #   600 TEU
        ("KRPUS", "USNYC",  ContainerType.REEFER_40FT,     300, "HIGH",     2),  #   600 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # TPX3  MV Pacific Trader 6,000 TEU  |  US → China return  (74% target)
    # ──────────────────────────────────────────────────────────────────────────
    "TPX3": [
        ("USLAX", "CNSHA",  ContainerType.HIGH_CUBE_40FT,  800, "HIGH",     3),  # 1,600 TEU
        ("USLAX", "CNNGB",  ContainerType.DRY_40FT,        700, "NORMAL",   2),  # 1,400 TEU
        ("TWKHH", "CNSHA",  ContainerType.DRY_40FT,        600, "NORMAL",   2),  # 1,200 TEU
        ("USNYC", "CNSHA",  ContainerType.DRY_20FT,        700, "NORMAL",   2),  #   700 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # AME1  MV Global Express 12,000 TEU  |  China/SE-Asia → Middle East  (80%)
    # India/South Asia demand concentrated here — CREATES SHORTAGE at CNSHA/SGSIN
    # ──────────────────────────────────────────────────────────────────────────
    "AME1": [
        ("CNSHA", "AEDXB",  ContainerType.HIGH_CUBE_40FT, 1600, "CRITICAL", 3),  # 3,200 TEU
        ("CNSHA", "AEDXB",  ContainerType.DRY_40FT,       1100, "HIGH",     3),  # 2,200 TEU
        ("SGSIN", "AEDXB",  ContainerType.DRY_40FT,        900, "HIGH",     2),  # 1,800 TEU
        ("LKCMB", "AEDXB",  ContainerType.DRY_20FT,        700, "NORMAL",   2),  #   700 TEU
        ("INMAA", "AEDXB",  ContainerType.DRY_40FT,        500, "HIGH",     2),  # 1,000 TEU  ← INDIA
        ("INBOM", "AEDXB",  ContainerType.HIGH_CUBE_40FT,  400, "HIGH",     2),  #   800 TEU  ← INDIA
        ("HKHKG", "AEDXB",  ContainerType.DRY_40FT,        400, "NORMAL",   2),  #   800 TEU
        ("CNSHA", "AEDXB",  ContainerType.REEFER_40FT,     200, "CRITICAL", 3),  #   400 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # AME2  MV Ocean Pioneer 11,500 TEU  |  South China/SE-Asia → ME  (76%)
    # ──────────────────────────────────────────────────────────────────────────
    "AME2": [
        ("CNGUZ", "AEDXB",  ContainerType.HIGH_CUBE_40FT, 1400, "HIGH",     3),  # 2,800 TEU
        ("HKHKG", "AEDXB",  ContainerType.DRY_40FT,       1100, "CRITICAL", 2),  # 2,200 TEU
        ("CNSZX", "AEDXB",  ContainerType.DRY_40FT,        900, "HIGH",     2),  # 1,800 TEU
        ("SGSIN", "PKKAR",  ContainerType.DRY_20FT,        700, "NORMAL",   2),  #   700 TEU
        ("LKCMB", "AEDXB",  ContainerType.HIGH_CUBE_40FT,  500, "NORMAL",   2),  # 1,000 TEU
        ("INMAA", "PKKAR",  ContainerType.DRY_40FT,        400, "NORMAL",   2),  #   800 TEU  ← INDIA
        ("INBOM", "PKKAR",  ContainerType.DRY_20FT,        500, "NORMAL",   2),  #   500 TEU  ← INDIA
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # IAF1  MV Silk Road 3,500 TEU  |  Intra-Asia  (75% target)
    # ──────────────────────────────────────────────────────────────────────────
    "IAF1": [
        ("SGSIN", "IDJKT",  ContainerType.DRY_20FT,        650, "NORMAL",   2),  #   650 TEU
        ("PHMNL", "VNSAG",  ContainerType.DRY_40FT,        450, "HIGH",     2),  #   900 TEU
        ("THBKK", "IDJKT",  ContainerType.DRY_40FT,        350, "NORMAL",   2),  #   700 TEU
        ("VNSAG", "SGSIN",  ContainerType.DRY_20FT,        300, "LOW",      1),  #   300 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # IAF2  MV Pearl River 3,200 TEU  |  Intra-Asia  (72% target)
    # ──────────────────────────────────────────────────────────────────────────
    "IAF2": [
        ("SGSIN", "VNHPH",  ContainerType.DRY_20FT,        550, "NORMAL",   2),  #   550 TEU
        ("THBKK", "MYPKG",  ContainerType.DRY_40FT,        450, "HIGH",     2),  #   900 TEU
        ("MYPKG", "VNHPH",  ContainerType.DRY_20FT,        300, "LOW",      1),  #   300 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # EAX1  MV Atlantic Bridge 8,500 TEU  |  Europe → Americas  (70% target)
    # ──────────────────────────────────────────────────────────────────────────
    "EAX1": [
        ("NLRTM", "USNYC",  ContainerType.HIGH_CUBE_40FT,  900, "HIGH",     3),  # 1,800 TEU
        ("DEHAM", "USSAV",  ContainerType.DRY_40FT,        800, "CRITICAL", 2),  # 1,600 TEU
        ("BEANR", "USHOU",  ContainerType.DRY_20FT,        700, "NORMAL",   2),  #   700 TEU
        ("GBFXT", "USNYC",  ContainerType.HIGH_CUBE_40FT,  500, "HIGH",     2),  # 1,000 TEU
        ("FRLEH", "USNYC",  ContainerType.DRY_40FT,        400, "NORMAL",   2),  #   800 TEU
        ("NLRTM", "USSAV",  ContainerType.DRY_45FT,        200, "HIGH",     2),  #   450 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # EAX2  MV Mediterranean Star 8,000 TEU  |  Europe → S. America  (68%)
    # ──────────────────────────────────────────────────────────────────────────
    "EAX2": [
        ("NLRTM", "BRSSZ",  ContainerType.DRY_40FT,        900, "HIGH",     3),  # 1,800 TEU
        ("ESBCN", "BRSSZ",  ContainerType.HIGH_CUBE_40FT,  700, "NORMAL",   2),  # 1,400 TEU
        ("GRPIR", "EGPSD",  ContainerType.DRY_20FT,        500, "NORMAL",   2),  #   500 TEU
        ("FRLEH", "BRVIX",  ContainerType.DRY_40FT,        400, "HIGH",     2),  #   800 TEU
        ("DEHAM", "BRSSZ",  ContainerType.DRY_45FT,        200, "HIGH",     2),  #   450 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # AFX1  MV Cape Trader 2,000 TEU  |  Africa  (70% target)
    # ──────────────────────────────────────────────────────────────────────────
    "AFX1": [
        ("EGPSD", "ZADUR",  ContainerType.DRY_40FT,        350, "HIGH",     3),  #   700 TEU
        ("MAPTM", "NGAPP",  ContainerType.DRY_20FT,        280, "NORMAL",   2),  #   280 TEU
        ("ZADUR", "NGAPP",  ContainerType.DRY_40FT,        200, "NORMAL",   2),  #   400 TEU
        ("KEYSM", "EGPSD",  ContainerType.DRY_20FT,        150, "LOW",      2),  #   150 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # SAF1  MV Bengal Star 2,800 TEU  |  India/Sri Lanka → Middle East  (82%)
    # INDIA CORRIDOR — designed to create heavy equipment pressure at INMAA/INBOM
    # ──────────────────────────────────────────────────────────────────────────
    "SAF1": [
        ("LKCMB", "AEDXB",  ContainerType.DRY_40FT,        550, "HIGH",     2),  # 1,100 TEU ← India subcontinent
        ("INMAA", "AEDXB",  ContainerType.HIGH_CUBE_40FT,  450, "CRITICAL", 2),  #   900 TEU ← INDIA
        ("BDCGP", "AEDXB",  ContainerType.DRY_20FT,        400, "NORMAL",   2),  #   400 TEU
        ("INHAL", "AEDXB",  ContainerType.DRY_40FT,        350, "HIGH",     2),  #   700 TEU ← INDIA
        ("INMAA", "PKKAR",  ContainerType.DRY_40FT,        250, "NORMAL",   2),  #   500 TEU ← INDIA
        ("PKKAR", "AEDXB",  ContainerType.DRY_20FT,        300, "NORMAL",   2),  #   300 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # SAF2  MV Malabar Express 2,500 TEU  |  Middle East → India return  (80%)
    # Return corridor — brings equipment back from Gulf to India
    # ──────────────────────────────────────────────────────────────────────────
    "SAF2": [
        ("AEDXB", "INMAA",  ContainerType.HIGH_CUBE_40FT,  500, "HIGH",     2),  # 1,000 TEU
        ("AEDXB", "INBOM",  ContainerType.DRY_40FT,        400, "HIGH",     2),  #   800 TEU
        ("PKKAR", "INMAA",  ContainerType.DRY_20FT,        350, "NORMAL",   2),  #   350 TEU
        ("INBOM", "LKCMB",  ContainerType.DRY_40FT,        250, "HIGH",     2),  #   500 TEU
        ("AEDXB", "INHAL",  ContainerType.DRY_40FT,        200, "NORMAL",   2),  #   400 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # OCX1  MV Southern Cross 6,800 TEU  |  SE-Asia → Oceania  (72%)
    # ──────────────────────────────────────────────────────────────────────────
    "OCX1": [
        ("SGSIN", "AUMEL",  ContainerType.DRY_40FT,        800, "HIGH",     3),  # 1,600 TEU
        ("PHMNL", "AUSYD",  ContainerType.HIGH_CUBE_40FT,  600, "NORMAL",   2),  # 1,200 TEU
        ("IDJKT", "AUMEL",  ContainerType.DRY_20FT,        500, "NORMAL",   2),  #   500 TEU
        ("SGSIN", "NZAKL",  ContainerType.DRY_40FT,        400, "NORMAL",   3),  #   800 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # MEF1  MV Arabian Falcon 2,200 TEU  |  Intra-Gulf  (75% target)
    # ──────────────────────────────────────────────────────────────────────────
    "MEF1": [
        ("AEDXB", "SADAM",  ContainerType.DRY_20FT,        400, "NORMAL",   2),  #   400 TEU
        ("AEDXB", "KWKWI",  ContainerType.DRY_40FT,        250, "NORMAL",   2),  #   500 TEU
        ("SADAM", "IQUMQ",  ContainerType.DRY_20FT,        200, "LOW",      2),  #   200 TEU
        ("OMPOR", "AEDXB",  ContainerType.DRY_40FT,        150, "NORMAL",   2),  #   300 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # WEX1  MV Indian Ocean 7,500 TEU  |  Intra-Europe  (70% target)
    # ──────────────────────────────────────────────────────────────────────────
    "WEX1": [
        ("NLRTM", "GRPIR",  ContainerType.DRY_40FT,        700, "HIGH",     3),  # 1,400 TEU
        ("DEHAM", "ESBCN",  ContainerType.HIGH_CUBE_40FT,  600, "NORMAL",   2),  # 1,200 TEU
        ("BEANR", "ITGOA",  ContainerType.DRY_20FT,        550, "NORMAL",   2),  #   550 TEU
        ("NLRTM", "PLGDY",  ContainerType.DRY_40FT,        400, "NORMAL",   2),  #   800 TEU
        ("GBFXT", "GRPIR",  ContainerType.HIGH_CUBE_40FT,  300, "LOW",      2),  #   600 TEU
        ("FRLEH", "ESBCN",  ContainerType.DRY_40FT,        250, "LOW",      2),  #   500 TEU
    ],
    # ──────────────────────────────────────────────────────────────────────────
    # SAM1  MV Eastern Pioneer 5,500 TEU  |  US → South America  (74%)
    # ──────────────────────────────────────────────────────────────────────────
    "SAM1": [
        ("USNYC", "BRSSZ",  ContainerType.DRY_40FT,        700, "HIGH",     2),  # 1,400 TEU
        ("USSAV", "BRVIX",  ContainerType.HIGH_CUBE_40FT,  550, "NORMAL",   2),  # 1,100 TEU
        ("USHOU", "COBUN",  ContainerType.DRY_20FT,        500, "NORMAL",   2),  #   500 TEU
        ("USHOU", "BRSSZ",  ContainerType.DRY_40FT,        400, "HIGH",     2),  #   800 TEU
        ("PAMIT", "BRSSZ",  ContainerType.DRY_20FT,        300, "LOW",      2),  #   300 TEU
    ],
}

_PRIORITY_MAP = {
    "CRITICAL": BookingPriority.CRITICAL,
    "HIGH":     BookingPriority.HIGH,
    "NORMAL":   BookingPriority.NORMAL,
    "LOW":      BookingPriority.LOW,
}

# ──────────────────────────────────────────────────────────────────────────────
# STRESS BOOKINGS — hardcoded extra demand that deliberately creates shortages
# at the major export hubs, forcing the MILP to reposition empties or lease.
# Each entry: (booking_id, origin, dest, ctype, qty, cargo_ready, cutoff, deadline, priority, wt_mt)
# ──────────────────────────────────────────────────────────────────────────────
_STRESS_BOOKINGS_RAW: List[tuple] = [
    # ── CNSHA surge — drains Shanghai 40HC and 40DC stock on days 1-15 ────────
    ("BK2-S001", "CNSHA", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 420, 1,  3,  40, "CRITICAL", 20.9),
    ("BK2-S002", "CNSHA", "DEHAM",  ContainerType.HIGH_CUBE_40FT, 380, 2,  4,  38, "CRITICAL", 20.9),
    ("BK2-S003", "CNSHA", "USLAX",  ContainerType.HIGH_CUBE_40FT, 450, 1,  3,  35, "CRITICAL", 20.9),
    ("BK2-S004", "CNSHA", "USNYC",  ContainerType.DRY_40FT,       350, 3,  5,  38, "CRITICAL", 21.8),
    ("BK2-S005", "CNSHA", "AEDXB",  ContainerType.DRY_40FT,       300, 1,  3,  32, "HIGH",     21.8),
    ("BK2-S006", "CNSHA", "GBFXT",  ContainerType.DRY_40FT,       280, 4,  6,  40, "HIGH",     21.8),
    ("BK2-S007", "CNSHA", "BEANR",  ContainerType.DRY_20FT,       500, 2,  4,  38, "HIGH",     14.2),
    ("BK2-S008", "CNSHA", "NLRTM",  ContainerType.DRY_40FT,       320, 5,  7,  42, "HIGH",     21.8),
    ("BK2-S009", "CNSHA", "DEHAM",  ContainerType.DRY_20FT,       450, 3,  5,  38, "NORMAL",   14.2),
    ("BK2-S010", "CNSHA", "FRLEH",  ContainerType.HIGH_CUBE_40FT, 210, 6,  8,  42, "HIGH",     20.9),
    # ── CNNGB / CNTAO surge ────────────────────────────────────────────────────
    ("BK2-S011", "CNNGB", "USLAX",  ContainerType.HIGH_CUBE_40FT, 390, 2,  4,  35, "CRITICAL", 20.9),
    ("BK2-S012", "CNNGB", "NLRTM",  ContainerType.DRY_40FT,       310, 1,  3,  38, "HIGH",     21.8),
    ("BK2-S013", "CNTAO", "DEHAM",  ContainerType.HIGH_CUBE_40FT, 340, 3,  5,  40, "HIGH",     20.9),
    ("BK2-S014", "CNTAO", "USLAX",  ContainerType.DRY_40FT,       290, 4,  6,  38, "CRITICAL", 21.8),
    ("BK2-S015", "CNTAO", "NLRTM",  ContainerType.DRY_20FT,       420, 2,  4,  40, "HIGH",     14.2),
    # ── HKHKG surge ────────────────────────────────────────────────────────────
    ("BK2-S016", "HKHKG", "USLAX",  ContainerType.HIGH_CUBE_40FT, 360, 1,  3,  35, "CRITICAL", 20.9),
    ("BK2-S017", "HKHKG", "NLRTM",  ContainerType.DRY_40FT,       290, 2,  4,  40, "HIGH",     21.8),
    ("BK2-S018", "HKHKG", "AEDXB",  ContainerType.DRY_40FT,       250, 3,  5,  35, "HIGH",     21.8),
    ("BK2-S019", "HKHKG", "GBFXT",  ContainerType.HIGH_CUBE_40FT, 200, 5,  7,  42, "NORMAL",   20.9),
    # ── KRPUS surge ────────────────────────────────────────────────────────────
    ("BK2-S020", "KRPUS", "USLAX",  ContainerType.DRY_40FT,       400, 1,  3,  35, "CRITICAL", 21.8),
    ("BK2-S021", "KRPUS", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 310, 2,  4,  40, "HIGH",     20.9),
    ("BK2-S022", "KRPUS", "DEHAM",  ContainerType.DRY_20FT,       380, 4,  6,  42, "HIGH",     14.2),
    # ── SGSIN surge ────────────────────────────────────────────────────────────
    ("BK2-S023", "SGSIN", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 340, 2,  4,  38, "CRITICAL", 20.9),
    ("BK2-S024", "SGSIN", "DEHAM",  ContainerType.DRY_40FT,       280, 3,  5,  40, "HIGH",     21.8),
    ("BK2-S025", "SGSIN", "AEDXB",  ContainerType.HIGH_CUBE_40FT, 240, 1,  3,  32, "HIGH",     20.9),
    ("BK2-S026", "SGSIN", "USNYC",  ContainerType.DRY_40FT,       220, 5,  7,  42, "NORMAL",   21.8),
    ("BK2-S027", "SGSIN", "AUMEL",  ContainerType.DRY_40FT,       195, 4,  6,  35, "HIGH",     21.8),
    # ── NLRTM import-turns-export: Rotterdam HC shortage ───────────────────────
    ("BK2-S028", "NLRTM", "USNYC",  ContainerType.HIGH_CUBE_40FT, 380, 1,  3,  35, "CRITICAL", 20.9),
    ("BK2-S029", "NLRTM", "USSAV",  ContainerType.DRY_40FT,       300, 2,  4,  38, "HIGH",     21.8),
    ("BK2-S030", "NLRTM", "BRSSZ",  ContainerType.DRY_40FT,       260, 3,  5,  42, "HIGH",     21.8),
    ("BK2-S031", "DEHAM", "USNYC",  ContainerType.HIGH_CUBE_40FT, 320, 1,  3,  38, "CRITICAL", 20.9),
    ("BK2-S032", "DEHAM", "USLAX",  ContainerType.DRY_40FT,       260, 4,  6,  42, "HIGH",     21.8),
    ("BK2-S033", "BEANR", "USHOU",  ContainerType.DRY_20FT,       440, 2,  4,  40, "HIGH",     14.2),
    # ── USLAX / USNYC return surge: drain US inventories ──────────────────────
    ("BK2-S034", "USLAX", "CNSHA",  ContainerType.HIGH_CUBE_40FT, 350, 5,  7,  42, "HIGH",     20.9),
    ("BK2-S035", "USLAX", "CNNGB",  ContainerType.DRY_40FT,       280, 6,  8,  44, "NORMAL",   21.8),
    ("BK2-S036", "USNYC", "BRSSZ",  ContainerType.DRY_40FT,       310, 3,  5,  40, "HIGH",     21.8),
    ("BK2-S037", "USNYC", "BRVIX",  ContainerType.HIGH_CUBE_40FT, 240, 4,  6,  42, "NORMAL",   20.9),
    ("BK2-S038", "USSAV", "BRVIX",  ContainerType.HIGH_CUBE_40FT, 200, 5,  7,  44, "NORMAL",   20.9),
    ("BK2-S039", "USHOU", "COBUN",  ContainerType.DRY_20FT,       280, 3,  5,  40, "HIGH",     14.2),
    # ── AEDXB / Jebel Ali outbound surge ───────────────────────────────────────
    ("BK2-S040", "AEDXB", "NLRTM",  ContainerType.DRY_40FT,       250, 8, 10,  45, "HIGH",     21.8),
    ("BK2-S041", "AEDXB", "INMAA",  ContainerType.HIGH_CUBE_40FT, 210, 5,  7,  40, "HIGH",     20.9),
    ("BK2-S042", "AEDXB", "PKKAR",  ContainerType.DRY_20FT,       300, 4,  6,  38, "NORMAL",   14.2),
    ("BK2-S043", "AEDXB", "SADAM",  ContainerType.DRY_20FT,       200, 3,  5,  35, "NORMAL",   14.2),
    # ── LKCMB / Colombo transship surge ────────────────────────────────────────
    ("BK2-S044", "LKCMB", "AEDXB",  ContainerType.DRY_40FT,       280, 2,  4,  35, "HIGH",     21.8),
    ("BK2-S045", "LKCMB", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 220, 6,  8,  45, "HIGH",     20.9),
    ("BK2-S046", "INMAA", "AEDXB",  ContainerType.DRY_40FT,       230, 3,  5,  38, "HIGH",     21.8),
    ("BK2-S047", "INBOM", "AEDXB",  ContainerType.DRY_40FT,       200, 2,  4,  36, "HIGH",     21.8),
    ("BK2-S048", "INMAA", "LKCMB",  ContainerType.HIGH_CUBE_40FT, 165, 4,  6,  38, "NORMAL",   20.9),
    # ── Reefer demand at cold-chain ports ──────────────────────────────────────
    ("BK2-S049", "AUMEL", "JPTYO",  ContainerType.REEFER_40FT,    180, 5,  7,  42, "CRITICAL", 18.5),
    ("BK2-S050", "AUSYD", "SGSIN",  ContainerType.REEFER_40FT,    150, 4,  6,  40, "HIGH",     18.5),
    ("BK2-S051", "NZAKL", "JPTYO",  ContainerType.REEFER_40FT,    120, 28, 30,  65, "HIGH",     18.5),
    ("BK2-S052", "CNSHA", "USNYC",  ContainerType.REEFER_40FT,    200, 3,  5,  40, "CRITICAL", 18.5),
    # ── 45FT pallet-wide surge (Europe to Americas) ────────────────────────────
    ("BK2-S053", "NLRTM", "USHOU",  ContainerType.DRY_45FT,       150, 4,  6,  42, "HIGH",     20.2),
    ("BK2-S054", "DEHAM", "USNYC",  ContainerType.DRY_45FT,       130, 3,  5,  40, "HIGH",     20.2),
    ("BK2-S055", "BEANR", "USSAV",  ContainerType.DRY_45FT,       110, 5,  7,  44, "NORMAL",   20.2),
    # ── Late-horizon second wave — days 30-60 ──────────────────────────────────
    ("BK2-S056", "CNSHA", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 400, 30, 32,  65, "CRITICAL", 20.9),
    ("BK2-S057", "CNSHA", "USLAX",  ContainerType.DRY_40FT,       360, 32, 34,  65, "CRITICAL", 21.8),
    ("BK2-S058", "KRPUS", "USNYC",  ContainerType.HIGH_CUBE_40FT, 310, 35, 37,  68, "HIGH",     20.9),
    ("BK2-S059", "SGSIN", "DEHAM",  ContainerType.DRY_40FT,       290, 28, 30,  62, "HIGH",     21.8),
    ("BK2-S060", "HKHKG", "NLRTM",  ContainerType.HIGH_CUBE_40FT, 320, 30, 32,  65, "HIGH",     20.9),
    ("BK2-S061", "CNNGB", "BEANR",  ContainerType.DRY_40FT,       280, 35, 37,  68, "HIGH",     21.8),
    ("BK2-S062", "CNTAO", "DEHAM",  ContainerType.HIGH_CUBE_40FT, 250, 40, 42,  72, "NORMAL",   20.9),
    ("BK2-S063", "NLRTM", "USNYC",  ContainerType.DRY_40FT,       230, 30, 32,  62, "HIGH",     21.8),
    ("BK2-S064", "DEHAM", "BRSSZ",  ContainerType.DRY_40FT,       200, 35, 37,  68, "NORMAL",   21.8),
    ("BK2-S065", "USLAX", "CNSHA",  ContainerType.HIGH_CUBE_40FT, 280, 40, 42,  72, "HIGH",     20.9),
]


# ============================================================
# BUILDER FUNCTIONS
# ============================================================

def _build_container_types() -> Dict[ContainerType, ContainerTypeSpec]:
    return {
        ContainerType.DRY_20FT: ContainerTypeSpec(
            container_type=ContainerType.DRY_20FT, name="20ft Standard Dry",
            teu_factor=1.0, tare_weight_mt=2.2, avg_cargo_weight_mt=12.0, total_laden_weight_mt=14.2),
        ContainerType.DRY_40FT: ContainerTypeSpec(
            container_type=ContainerType.DRY_40FT, name="40ft Standard Dry",
            teu_factor=2.0, tare_weight_mt=3.8, avg_cargo_weight_mt=18.0, total_laden_weight_mt=21.8),
        ContainerType.HIGH_CUBE_40FT: ContainerTypeSpec(
            container_type=ContainerType.HIGH_CUBE_40FT, name="40ft High Cube",
            teu_factor=2.0, tare_weight_mt=3.9, avg_cargo_weight_mt=17.0, total_laden_weight_mt=20.9),
        ContainerType.REEFER_40FT: ContainerTypeSpec(
            container_type=ContainerType.REEFER_40FT, name="40ft Reefer",
            teu_factor=2.0, tare_weight_mt=4.5, avg_cargo_weight_mt=14.0, total_laden_weight_mt=18.5),
        ContainerType.DRY_45FT: ContainerTypeSpec(
            container_type=ContainerType.DRY_45FT, name="45ft Pallet Wide",
            teu_factor=2.25, tare_weight_mt=4.2, avg_cargo_weight_mt=16.0, total_laden_weight_mt=20.2),
    }


def _build_ports() -> Dict[str, PortFixture]:
    """55 global ports with full parameter set."""
    _raw = [
        # (unlocode, name, country, region, lat, lon, storage_teu, ss_teu, devan_days, liftOn, liftOff)
        ("CNSHA","Port of Shanghai","China","East Asia",31.23,121.47,50000,500,2,45.0,45.0),
        ("CNNGB","Port of Ningbo","China","East Asia",29.86,121.55,35000,350,2,47.0,47.0),
        ("CNTAO","Port of Qingdao","China","East Asia",36.07,120.38,25000,250,2,48.0,48.0),
        ("CNSZX","Port of Shenzhen","China","East Asia",22.50,113.90,22000,220,2,46.0,46.0),
        ("CNGUZ","Port of Guangzhou","China","East Asia",23.13,113.26,18000,180,2,48.0,48.0),
        ("HKHKG","Port of Hong Kong","China","East Asia",22.28,114.17,20000,200,2,55.0,55.0),
        ("TWKHH","Port of Kaohsiung","Taiwan","East Asia",22.62,120.30,12000,120,2,50.0,50.0),
        ("KRPUS","Port of Busan","South Korea","Northeast Asia",35.10,129.04,18000,180,2,52.0,52.0),
        ("JPTYO","Port of Tokyo","Japan","Northeast Asia",35.63,139.78,8000,80,2,58.0,58.0),
        ("JPOSA","Port of Osaka","Japan","Northeast Asia",34.65,135.43,6500,65,2,56.0,56.0),
        ("SGSIN","Port of Singapore","Singapore","Southeast Asia",1.35,103.82,40000,400,2,60.0,60.0),
        ("MYPEN","Port of Penang","Malaysia","Southeast Asia",5.41,100.33,5000,50,2,42.0,42.0),
        ("MYPKG","Port of Klang","Malaysia","Southeast Asia",3.00,101.39,12000,120,2,43.0,43.0),
        ("THBKK","Laem Chabang","Thailand","Southeast Asia",13.07,100.90,8000,80,2,44.0,44.0),
        ("VNHPH","Port of Hai Phong","Vietnam","Southeast Asia",20.84,106.69,5000,50,2,38.0,38.0),
        ("VNSAG","Port of Ho Chi Minh","Vietnam","Southeast Asia",10.78,106.70,7500,75,2,40.0,40.0),
        ("IDJKT","Port of Jakarta","Indonesia","Southeast Asia",-6.10,106.88,8500,85,3,40.0,40.0),
        ("PHMNL","Port of Manila","Philippines","Southeast Asia",14.59,120.97,7000,70,3,40.0,40.0),
        ("LKCMB","Port of Colombo","Sri Lanka","South Asia",6.93,79.85,10000,100,2,42.0,42.0),
        ("BDCGP","Port of Chittagong","Bangladesh","South Asia",22.34,91.83,5000,50,3,35.0,35.0),
        ("INMAA","Port of Chennai","India","South Asia",13.08,80.27,12000,120,2,40.0,40.0),
        ("INBOM","Port of Mumbai","India","South Asia",18.96,72.82,14000,140,2,40.0,40.0),
        ("INHAL","Nhava Sheva","India","South Asia",18.95,72.95,10000,100,2,40.0,40.0),
        ("PKKAR","Port of Karachi","Pakistan","South Asia",24.85,66.98,7000,70,3,35.0,35.0),
        ("AEDXB","Jebel Ali","UAE","Middle East",25.01,55.06,20000,200,2,50.0,50.0),
        ("OMPOR","Port of Salalah","Oman","Middle East",17.00,54.07,4000,40,2,45.0,45.0),
        ("IQUMQ","Umm Qasr","Iraq","Middle East",30.03,47.92,3000,30,4,32.0,32.0),
        ("SADAM","Port of Dammam","Saudi Arabia","Middle East",26.44,50.00,6000,60,3,38.0,38.0),
        ("IQBAS","Port of Basra","Iraq","Middle East",30.52,47.78,3000,30,4,30.0,30.0),
        ("KWKWI","Port of Kuwait","Kuwait","Middle East",29.37,47.98,4000,40,3,35.0,35.0),
        ("EGPSD","Port Said","Egypt","Africa",31.26,32.30,10000,100,2,40.0,40.0),
        ("ZADUR","Port of Durban","South Africa","Africa",-29.86,31.02,6000,60,2,38.0,38.0),
        ("NGAPP","Apapa (Lagos)","Nigeria","Africa",6.45,3.41,5000,50,4,32.0,32.0),
        ("KEYSM","Port of Mombasa","Kenya","Africa",-4.05,39.67,4000,40,3,35.0,35.0),
        ("MAPTM","Tanger Med","Morocco","Africa",35.87,-5.50,8000,80,2,42.0,42.0),
        ("NLRTM","Port of Rotterdam","Netherlands","Europe",51.90,4.48,35000,350,1,65.0,65.0),
        ("DEHAM","Port of Hamburg","Germany","Europe",53.54,9.97,18000,180,1,62.0,62.0),
        ("GBFXT","Port of Felixstowe","UK","Europe",51.96,1.35,10000,100,1,60.0,60.0),
        ("BEANR","Port of Antwerp","Belgium","Europe",51.22,4.40,18000,180,1,63.0,63.0),
        ("ESBCN","Port of Barcelona","Spain","Europe",41.34,2.16,8000,80,1,55.0,55.0),
        ("ITGOA","Port of Genoa","Italy","Europe",44.41,8.93,7000,70,1,55.0,55.0),
        ("GRPIR","Port of Piraeus","Greece","Europe",37.94,23.63,7500,75,1,55.0,55.0),
        ("FRLEH","Port of Le Havre","France","Europe",49.49,0.11,9000,90,1,60.0,60.0),
        ("PLGDY","Port of Gdansk","Poland","Europe",54.38,18.66,5000,50,1,55.0,55.0),
        ("USLAX","Port of Los Angeles","USA","Americas",33.74,-118.27,25000,250,1,65.0,65.0),
        ("USNYC","Port of New York","USA","Americas",40.66,-74.04,15000,150,1,65.0,65.0),
        ("USSAV","Port of Savannah","USA","Americas",31.97,-81.10,10000,100,1,62.0,62.0),
        ("USHOU","Port of Houston","USA","Americas",29.73,-95.26,8000,80,1,62.0,62.0),
        ("BRVIX","Port of Vitoria","Brazil","Americas",-20.31,-40.33,4000,40,2,45.0,45.0),
        ("BRSSZ","Port of Santos","Brazil","Americas",-23.95,-46.33,9000,90,2,48.0,48.0),
        ("PAMIT","Manzanillo (Panama)","Panama","Americas",9.37,-79.90,5000,50,2,50.0,50.0),
        ("COBUN","Port of Buenaventura","Colombia","Americas",3.87,-77.06,3500,35,3,42.0,42.0),
        ("AUMEL","Port of Melbourne","Australia","Oceania",-37.82,144.92,8000,80,2,60.0,60.0),
        ("AUSYD","Port of Sydney","Australia","Oceania",-33.87,151.21,6000,60,2,60.0,60.0),
        ("NZAKL","Port of Auckland","New Zealand","Oceania",-36.84,174.76,4500,45,2,58.0,58.0),
    ]
    result = {}
    for row in _raw:
        code, name, country, region, lat, lon, storage, ss, devan, liftOn, liftOff = row
        result[code] = PortFixture(
            unlocode=code, name=name, country=country, region=region,
            latitude=lat, longitude=lon,
            storage_capacity_teu=storage,
            safety_stock_teu=ss,
            devanning_lead_time_days=devan,
            lift_on_cost=liftOn,
            lift_off_cost=liftOff,
        )
    return result


def _build_vessels() -> List[VesselFixture]:
    entries = [
        ("IMO2000001", "MV Ever Quantum"),
        ("IMO2000002", "MV Asia Colossus"),
        ("IMO2000003", "MV Pacific Titan"),
        ("IMO2000004", "MV Eastern Giant"),
        ("IMO2000005", "MV Global Express"),
        ("IMO2000006", "MV Ocean Pioneer"),
        ("IMO2000007", "MV Atlantic Bridge"),
        ("IMO2000008", "MV Mediterranean Star"),
        ("IMO2000009", "MV Indian Ocean"),
        ("IMO2000010", "MV Southern Cross"),
        ("IMO2000011", "MV Pacific Trader"),
        ("IMO2000012", "MV Eastern Pioneer"),
        ("IMO2000013", "MV Silk Road"),
        ("IMO2000014", "MV Pearl River"),
        ("IMO2000015", "MV Bengal Star"),
        ("IMO2000016", "MV Malabar Express"),
        ("IMO2000017", "MV Arabian Falcon"),
        ("IMO2000018", "MV Cape Trader"),
    ]
    vessels = []
    for imo, name in entries:
        teu, dwt = _VESSEL_SPECS[name]
        reefer = int(teu * 0.08)
        vessels.append(VesselFixture(
            imo_number=imo, name=name,
            vessel_type=_vessel_type(teu),
            container_capacity_teu=teu,
            deadweight_capacity_mt=dwt,
            reefer_plugs=reefer,
        ))
    return vessels


def _build_voyage_legs(horizon: int) -> List[VoyageLegFixture]:
    """Generate recurring vessel rotation legs for all 18 services."""
    legs: List[VoyageLegFixture] = []
    for svc_code, svc in _SERVICES.items():
        teu, dwt = _VESSEL_SPECS[svc["vessel"]]
        pre_frac = svc["pre_booked_frac"]
        route = svc["route"]
        for rot in range(svc["rotations"]):
            start = svc["first_start"] + rot * svc["cycle"]
            voy_num = f"VOY_{svc_code}_R{rot + 1}"
            for seg in range(len(route) - 1):
                fp, f_off = route[seg]
                tp, t_off = route[seg + 1]
                dep_day = start + f_off
                arr_day = start + t_off
                # Include leg if departure is within horizon (arrivals can slightly exceed)
                if dep_day > horizon:
                    continue
                legs.append(VoyageLegFixture(
                    leg_id=f"LEG-{svc_code}-R{rot+1}-S{seg+1}",
                    voyage_number=voy_num,
                    vessel_name=svc["vessel"],
                    from_port_unlocode=fp,
                    to_port_unlocode=tp,
                    departure_day=dep_day,
                    arrival_day=arr_day,
                    transit_days=t_off - f_off,
                    capacity_teu=teu,
                    capacity_weight_mt=float(dwt),
                    booked_capacity_teu=int(teu * pre_frac),
                    booked_weight_mt=float(dwt * pre_frac),
                ))
    return legs


def _build_bookings(horizon: int) -> List[BookingFixture]:
    """Auto-generate bookings from service patterns + stress bookings that create shortages."""
    bookings: List[BookingFixture] = []
    bk_num = 1
    for svc_code, patterns in _BOOKING_PATTERNS.items():
        svc = _SERVICES[svc_code]
        route = svc["route"]
        port_offset = {p: off for p, off in route}
        for rot in range(svc["rotations"]):
            start = svc["first_start"] + rot * svc["cycle"]
            for (origin, dest, ctype, qty, prio_str, cargo_off) in patterns:
                if origin not in port_offset or dest not in port_offset:
                    continue
                dep_day = start + port_offset[origin]
                arr_day = start + port_offset[dest]
                if dep_day > horizon:
                    continue
                cargo_ready = max(1, dep_day - cargo_off)
                cutoff = max(cargo_ready, dep_day - 1)
                # Deadline must be >= arrival + delivery buffer AND >= cutoff + 3
                deadline = max(arr_day + 6, cutoff + 3)
                wt = 18.0 if ctype in (ContainerType.DRY_40FT, ContainerType.HIGH_CUBE_40FT,
                                        ContainerType.REEFER_40FT, ContainerType.DRY_45FT) else 12.0
                bookings.append(BookingFixture(
                    booking_id=f"BK2-{bk_num:03d}",
                    origin_unlocode=origin,
                    destination_unlocode=dest,
                    container_type=ctype,
                    quantity=qty,
                    cargo_ready_day=cargo_ready,
                    cutoff_day=cutoff,
                    delivery_deadline_day=deadline,
                    priority=_PRIORITY_MAP[prio_str],
                    cargo_weight_mt=wt,
                ))
                bk_num += 1

    # ── Append stress bookings (hardcoded to create deliberate shortages) ──
    for row in _STRESS_BOOKINGS_RAW:
        bid, origin, dest, ctype, qty, cargo_ready, cutoff, deadline, prio_str, wt = row
        if cargo_ready > horizon or cutoff > horizon:
            continue
        bookings.append(BookingFixture(
            booking_id=bid,
            origin_unlocode=origin,
            destination_unlocode=dest,
            container_type=ctype,
            quantity=qty,
            cargo_ready_day=cargo_ready,
            cutoff_day=cutoff,
            delivery_deadline_day=deadline,
            priority=_PRIORITY_MAP[prio_str],
            cargo_weight_mt=wt,
        ))

    return bookings


def _daily_demand_rate(port_code: str, ctype: ContainerType, day: int) -> float:
    """Deterministic daily demand rate using port tier, regional type share, and weekly seasonality."""
    tier = _PORT_TIER.get(port_code, 0.25)
    region = _PORT_REGION.get(port_code, "ASIA")
    share = _TYPE_SHARE[region].get(ctype, 0.20)
    base = tier * share * _BASE_DAILY_DEMAND
    # Day-of-week seasonality (0=Mon, 6=Sun) — Mon–Wed are busiest
    dow_factor = [1.08, 1.12, 1.10, 1.05, 0.94, 0.87, 0.84][day % 7]
    return round(base * dow_factor, 3)


def _daily_return_rate(port_code: str, ctype: ContainerType, day: int, horizon: int) -> float:
    """Returns are 65% of demand lagged by 21 days (3-week turnaround)."""
    lag = max(1, day - 21)
    return round(0.65 * _daily_demand_rate(port_code, ctype, lag), 3)


def _build_forecasts(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    horizon: int,
) -> Tuple[
    Dict[Tuple[str, ContainerType, int], float],  # D[i,k,t]
    Dict[Tuple[str, ContainerType, int], float],  # R[i,k,t]
]:
    D: Dict[Tuple[str, ContainerType, int], float] = {}
    R: Dict[Tuple[str, ContainerType, int], float] = {}
    for p in ports:
        for k in ctypes:
            for t in range(horizon + 1):
                D[(p, k, t)] = _daily_demand_rate(p, k, t)
                R[(p, k, t)] = _daily_return_rate(p, k, t, horizon)
    return D, R


def _build_forecast_errors(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    horizon: int,
) -> Tuple[
    Dict[Tuple[str, ContainerType, int], float],  # μ^D
    Dict[Tuple[str, ContainerType, int], float],  # σ^D
    Dict[Tuple[str, ContainerType, int], float],  # μ^R
    Dict[Tuple[str, ContainerType, int], float],  # σ^R
]:
    """
    Forecast errors are modelled as:
      μ^D = 0 (unbiased forecast assumption)
      σ^D = 0.20 * D[i,k,t]   (20% coefficient of variation for demand)
      μ^R = 0
      σ^R = 0.25 * R[i,k,t]   (25% CV for returns — harder to forecast)
    """
    mu_D: Dict[Tuple[str, ContainerType, int], float] = {}
    sg_D: Dict[Tuple[str, ContainerType, int], float] = {}
    mu_R: Dict[Tuple[str, ContainerType, int], float] = {}
    sg_R: Dict[Tuple[str, ContainerType, int], float] = {}
    for p in ports:
        for k in ctypes:
            for t in range(horizon + 1):
                d = _daily_demand_rate(p, k, t)
                r = _daily_return_rate(p, k, t, horizon)
                mu_D[(p, k, t)] = 0.0
                sg_D[(p, k, t)] = round(0.20 * d, 4)
                mu_R[(p, k, t)] = 0.0
                sg_R[(p, k, t)] = round(0.25 * r, 4)
    return mu_D, sg_D, mu_R, sg_R


def _compute_safety_stocks(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    horizon: int,
    sg_D: Dict[Tuple[str, ContainerType, int], float],
    mu_D: Dict[Tuple[str, ContainerType, int], float],
    sg_R: Dict[Tuple[str, ContainerType, int], float],
) -> Dict[Tuple[str, ContainerType, int], float]:
    """
    ECO/Neely safety stock formula:
      SS[i,k,t] = z_alpha * sqrt(lead_time * σ_D^2 + μ_D^2 * σ_vessel^2 + σ_R^2)
    where lead_time = avg replenishment lead time for port (in days).
    """
    # Approximate lead time by port region (days to nearest supply hub)
    _lead = {
        "ASIA": 5, "SOUTH_ASIA": 8, "MIDEAST": 10, "AFRICA": 14,
        "EUROPE": 7, "AMERICAS": 12, "OCEANIA": 15,
    }
    SS: Dict[Tuple[str, ContainerType, int], float] = {}
    for p in ports:
        region = _PORT_REGION.get(p, "ASIA")
        lt = _lead[region]
        for k in ctypes:
            for t in range(horizon + 1):
                sd = sg_D.get((p, k, t), 0.0)
                md = mu_D.get((p, k, t), 0.0)
                sr = sg_R.get((p, k, t), 0.0)
                variance = lt * sd**2 + md**2 * _SIGMA_VESSEL**2 + sr**2
                ss_val = _Z_ALPHA * math.sqrt(max(0.0, variance))
                SS[(p, k, t)] = round(max(ss_val, 2.0), 2)  # minimum 2 containers
    return SS


def _build_in_transit_pipeline(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    horizon: int,
) -> Dict[Tuple[str, ContainerType, int], int]:
    """
    G[i,k,t]: containers already in transit (before simulation start) arriving at port i
    on day t. Hardcoded for first 21 days based on realistic pre-sim shipping schedules.
    Only populated for t ∈ [1, 21] (beyond that, vessels haven't departed yet pre-sim).
    """
    G: Dict[Tuple[str, ContainerType, int], int] = {}
    # Pre-populate to 0
    for p in ports:
        for k in ctypes:
            for t in range(horizon + 1):
                G[(p, k, t)] = 0

    # Hardcoded pre-simulation in-transit arrivals (realistic subset)
    # (port, ctype, day) -> quantity
    _hardcoded: List[Tuple[str, ContainerType, int, int]] = [
        # Major hub pre-transit replenishments
        ("NLRTM", ContainerType.HIGH_CUBE_40FT, 5,  120),
        ("NLRTM", ContainerType.DRY_40FT,        7,   80),
        ("NLRTM", ContainerType.DRY_20FT,         9,   60),
        ("DEHAM", ContainerType.DRY_40FT,          6,   90),
        ("BEANR", ContainerType.HIGH_CUBE_40FT,    8,   70),
        ("USLAX", ContainerType.DRY_40FT,          4,  150),
        ("USLAX", ContainerType.HIGH_CUBE_40FT,    6,  100),
        ("USNYC", ContainerType.DRY_40FT,          7,   80),
        ("AEDXB", ContainerType.DRY_20FT,          3,  110),
        ("AEDXB", ContainerType.DRY_40FT,          5,   70),
        ("SGSIN", ContainerType.HIGH_CUBE_40FT,    2,  130),
        ("SGSIN", ContainerType.DRY_40FT,          4,   90),
        ("CNSHA", ContainerType.DRY_40FT,          3,  100),
        ("CNSHA", ContainerType.HIGH_CUBE_40FT,    5,   80),
        ("KRPUS", ContainerType.DRY_40FT,          4,   60),
        ("INMAA", ContainerType.DRY_20FT,          6,   50),
        ("INBOM", ContainerType.DRY_40FT,          7,   60),
        ("LKCMB", ContainerType.DRY_40FT,          5,   40),
        ("BRSSZ", ContainerType.DRY_40FT,          9,   55),
        ("AUMEL", ContainerType.DRY_40FT,         11,   45),
        ("EGPSD", ContainerType.DRY_20FT,          8,   60),
        ("MYPKG", ContainerType.DRY_40FT,          6,   50),
        ("HKHKG", ContainerType.HIGH_CUBE_40FT,    4,   70),
        ("TWKHH", ContainerType.DRY_40FT,          5,   55),
        # Reefer pre-transit (cold chain)
        ("NLRTM", ContainerType.REEFER_40FT,       7,   25),
        ("USNYC", ContainerType.REEFER_40FT,       8,   20),
        ("SGSIN", ContainerType.REEFER_40FT,       3,   18),
        ("AUMEL", ContainerType.REEFER_40FT,      10,   22),
        # 45ft
        ("NLRTM", ContainerType.DRY_45FT,          6,   15),
        ("DEHAM", ContainerType.DRY_45FT,          7,   12),
    ]
    for p, k, t, qty in _hardcoded:
        if p in ports and k in ctypes and 0 <= t <= horizon:
            G[(p, k, t)] = qty
    return G


def _build_historical_data(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
) -> Tuple[
    Dict[Tuple[str, ContainerType, int], float],  # hist demand (t = -84 to -7, weekly)
    Dict[Tuple[str, ContainerType, int], float],  # hist returns
    Dict[Tuple[str, ContainerType, int], float],  # hist inventory
]:
    """
    12 weeks of historical data (weeks -12 to -1, weekly granularity).
    t values: -84, -77, -70, -63, -56, -49, -42, -35, -28, -21, -14, -7
    Data is generated deterministically using port tier × seasonality + a simple sine trend.
    """
    hist_D: Dict[Tuple[str, ContainerType, int], float] = {}
    hist_R: Dict[Tuple[str, ContainerType, int], float] = {}
    hist_I: Dict[Tuple[str, ContainerType, int], float] = {}

    weeks = [-84, -77, -70, -63, -56, -49, -42, -35, -28, -21, -14, -7]  # start of each historic week

    for p in ports:
        tier = _PORT_TIER.get(p, 0.25)
        region = _PORT_REGION.get(p, "ASIA")
        for k in ctypes:
            share = _TYPE_SHARE[region].get(k, 0.20)
            base_weekly = tier * share * _BASE_DAILY_DEMAND * 7.0
            # Simulate 12 weeks of inventory
            inv = tier * share * 300.0  # starting inventory estimate
            for idx, t in enumerate(weeks):
                # Add slight sinusoidal trend (seasonal cycle of ~12 weeks)
                season = 1.0 + 0.12 * math.sin(2 * math.pi * idx / 12)
                # Add deterministic noise based on port code hash
                noise = 1.0 + 0.05 * math.sin(hash(p + k.value) + idx * 0.7)
                weekly_d = round(base_weekly * season * noise, 2)
                weekly_r = round(weekly_d * 0.65 * (1 + 0.08 * math.sin(idx * 0.5)), 2)
                hist_D[(p, k, t)] = weekly_d
                hist_R[(p, k, t)] = weekly_r
                # Inventory evolves: prev + returns - demand + small noise
                inv = max(5.0, inv + weekly_r - weekly_d * 0.9 + base_weekly * 0.05)
                hist_I[(p, k, t)] = round(inv, 2)

    return hist_D, hist_R, hist_I


def _build_costs(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    bookings: List[BookingFixture],
) -> Tuple[
    Dict[Tuple[str, str, ContainerType], float],   # repositioning_costs
    Dict[Tuple[str, ContainerType], float],         # leasing_costs (short)
    Dict[Tuple[str, ContainerType], float],         # leasing_costs_long
    Dict[Tuple[str, ContainerType], float],         # holding_costs
    Dict[Tuple[str, ContainerType], float],         # lift_on_costs
    Dict[Tuple[str, ContainerType], float],         # lift_off_costs
    Dict[str, float],                               # delay_penalties
    Dict[BookingPriority, float],                   # shortage_penalties
]:
    # ── Repositioning costs (by route type) ───────────────────────────────
    _repo_base = {
        ContainerType.DRY_20FT:       1.0,
        ContainerType.DRY_40FT:       1.8,
        ContainerType.HIGH_CUBE_40FT: 1.9,
        ContainerType.REEFER_40FT:    2.5,
        ContainerType.DRY_45FT:       2.0,
    }
    # Distance-based multiplier per region pair
    _route_multiplier = {
        ("ASIA", "ASIA"): 0.6, ("ASIA", "SOUTH_ASIA"): 0.8, ("ASIA", "MIDEAST"): 1.0,
        ("ASIA", "EUROPE"): 1.8, ("ASIA", "AMERICAS"): 2.0, ("ASIA", "AFRICA"): 1.6,
        ("ASIA", "OCEANIA"): 1.2, ("SOUTH_ASIA", "MIDEAST"): 0.8,
        ("SOUTH_ASIA", "EUROPE"): 1.6, ("SOUTH_ASIA", "AFRICA"): 1.2,
        ("MIDEAST", "EUROPE"): 1.4, ("MIDEAST", "AFRICA"): 1.0, ("MIDEAST", "AMERICAS"): 2.2,
        ("EUROPE", "AMERICAS"): 1.6, ("EUROPE", "AFRICA"): 1.2, ("EUROPE", "EUROPE"): 0.5,
        ("AMERICAS", "AMERICAS"): 0.6, ("AMERICAS", "OCEANIA"): 1.8, ("AFRICA", "AFRICA"): 0.7,
        ("OCEANIA", "ASIA"): 1.2, ("OCEANIA", "AMERICAS"): 1.8,
    }
    repo_costs: Dict[Tuple[str, str, ContainerType], float] = {}
    port_list = list(ports.keys())
    for o in port_list:
        for d in port_list:
            if o == d:
                continue
            r_o = _PORT_REGION.get(o, "ASIA")
            r_d = _PORT_REGION.get(d, "ASIA")
            key = (r_o, r_d) if (r_o, r_d) in _route_multiplier else (r_d, r_o)
            mult = _route_multiplier.get(key, 1.0)
            for k in ctypes:
                base_cost = 45.0 * _repo_base[k] * mult
                repo_costs[(o, d, k)] = round(base_cost, 2)

    # ── Short-term leasing costs ────────────────────────────────────────────
    _lease_short_base = {
        ContainerType.DRY_20FT: 350.0, ContainerType.DRY_40FT: 600.0,
        ContainerType.HIGH_CUBE_40FT: 650.0, ContainerType.REEFER_40FT: 950.0,
        ContainerType.DRY_45FT: 700.0,
    }
    _region_lease_premium = {
        "ASIA": 1.0, "SOUTH_ASIA": 1.05, "MIDEAST": 1.10, "AFRICA": 1.15,
        "EUROPE": 1.08, "AMERICAS": 1.12, "OCEANIA": 1.18,
    }
    lease_short: Dict[Tuple[str, ContainerType], float] = {}
    for p in ports:
        region = _PORT_REGION.get(p, "ASIA")
        prem = _region_lease_premium[region]
        for k in ctypes:
            lease_short[(p, k)] = round(_lease_short_base[k] * prem, 2)

    # ── Long-term leasing costs (per container per day) ─────────────────────
    _lease_long_base = {
        ContainerType.DRY_20FT: 1.80, ContainerType.DRY_40FT: 3.20,
        ContainerType.HIGH_CUBE_40FT: 3.50, ContainerType.REEFER_40FT: 5.50,
        ContainerType.DRY_45FT: 3.80,
    }
    lease_long: Dict[Tuple[str, ContainerType], float] = {}
    for p in ports:
        region = _PORT_REGION.get(p, "ASIA")
        prem = _region_lease_premium[region]
        for k in ctypes:
            lease_long[(p, k)] = round(_lease_long_base[k] * prem, 3)

    # ── Holding costs (per container per day) ───────────────────────────────
    _hold_base = {
        ContainerType.DRY_20FT: 1.80, ContainerType.DRY_40FT: 3.20,
        ContainerType.HIGH_CUBE_40FT: 3.50, ContainerType.REEFER_40FT: 6.00,
        ContainerType.DRY_45FT: 3.80,
    }
    hold_costs: Dict[Tuple[str, ContainerType], float] = {}
    for p in ports:
        for k in ctypes:
            hold_costs[(p, k)] = _hold_base[k]

    # ── Lift-on / lift-off costs (from PortFixture) ─────────────────────────
    _liftOn_multi = {
        ContainerType.DRY_20FT: 1.0, ContainerType.DRY_40FT: 1.6,
        ContainerType.HIGH_CUBE_40FT: 1.65, ContainerType.REEFER_40FT: 2.10,
        ContainerType.DRY_45FT: 1.75,
    }
    lift_on: Dict[Tuple[str, ContainerType], float] = {}
    lift_off: Dict[Tuple[str, ContainerType], float] = {}
    for p, pfx in ports.items():
        for k in ctypes:
            lift_on[(p, k)]  = round(pfx.lift_on_cost  * _liftOn_multi[k], 2)
            lift_off[(p, k)] = round(pfx.lift_off_cost * _liftOn_multi[k], 2)

    # ── Booking delay penalties (per booking per day late) ───────────────────
    _delay_base = {
        BookingPriority.CRITICAL: 800.0, BookingPriority.HIGH: 300.0,
        BookingPriority.NORMAL: 100.0,   BookingPriority.LOW: 30.0,
    }
    delay_penalties: Dict[str, float] = {}
    for b in bookings:
        delay_penalties[b.booking_id] = _delay_base[b.priority]

    # ── Shortage penalties ───────────────────────────────────────────────────
    shortage_pens = {
        BookingPriority.CRITICAL: 30000.0, BookingPriority.HIGH: 12000.0,
        BookingPriority.NORMAL:   4000.0,  BookingPriority.LOW:  1200.0,
    }
    return repo_costs, lease_short, lease_long, hold_costs, lift_on, lift_off, delay_penalties, shortage_pens


def _build_initial_inventory(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
) -> Dict[Tuple[str, ContainerType], int]:
    """
    Initial empty container inventory at t=0.
    Major export hubs (CNSHA, CNNGB, CNTAO, HKHKG, KRPUS, SGSIN, NLRTM, DEHAM)
    start with REDUCED stock (≈40% of normal) to guarantee shortages and force
    the MILP to either reposition empties or lease containers.
    """
    # Ports where we deliberately under-stock to create pressure
    _TIGHT_STOCK_PORTS = {
        "CNSHA", "CNNGB", "CNTAO", "CNSZX", "CNGUZ",
        "HKHKG", "TWKHH", "KRPUS", "SGSIN",
        "NLRTM", "DEHAM", "BEANR", "GBFXT",
        "USLAX", "USNYC",
    }
    inv: Dict[Tuple[str, ContainerType], int] = {}
    for p in ports:
        tier = _PORT_TIER.get(p, 0.25)
        region = _PORT_REGION.get(p, "ASIA")
        for k in ctypes:
            share = _TYPE_SHARE[region].get(k, 0.20)
            # 4-6 weeks of inventory at base demand rate
            weeks_stock = 4.0 + tier * 2.0
            qty = int(tier * share * _BASE_DAILY_DEMAND * 7 * weeks_stock)
            if p in _TIGHT_STOCK_PORTS:
                # Reduce to ~40% — guarantees demand will outrun stock early
                qty = int(qty * 0.40)
            inv[(p, k)] = max(5, qty)
    return inv


def _build_storage_caps(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
) -> Dict[Tuple[str, ContainerType], int]:
    """StorageCap[i,k]: physical storage limit per port per type (TEU-equivalent split)."""
    caps: Dict[Tuple[str, ContainerType], int] = {}
    teu_share = {
        ContainerType.DRY_20FT: 0.20, ContainerType.DRY_40FT: 0.36,
        ContainerType.HIGH_CUBE_40FT: 0.32, ContainerType.REEFER_40FT: 0.08,
        ContainerType.DRY_45FT: 0.04,
    }
    for p, pfx in ports.items():
        for k in ctypes:
            # storage_capacity_teu is in TEU; convert to containers
            share = teu_share.get(k, 0.20)
            teu_factor = 1.0 if k == ContainerType.DRY_20FT else 2.0
            teu_alloc = pfx.storage_capacity_teu * share
            caps[(p, k)] = max(100, int(teu_alloc / teu_factor))
    return caps


def _build_lease_caps(
    ports: Dict[str, PortFixture],
    ctypes: Dict[ContainerType, ContainerTypeSpec],
    horizon: int,
) -> Tuple[
    Dict[Tuple[str, ContainerType], int],         # lease_cap_short (per horizon)
    Dict[Tuple[str, ContainerType, int], int],    # lease_cap_long (per day)
]:
    """Lease availability caps based on port tier and market liquidity."""
    cap_short: Dict[Tuple[str, ContainerType], int] = {}
    cap_long:  Dict[Tuple[str, ContainerType, int], int] = {}

    _market_liquidity = {
        ContainerType.DRY_20FT: 0.40, ContainerType.DRY_40FT: 0.35,
        ContainerType.HIGH_CUBE_40FT: 0.30, ContainerType.REEFER_40FT: 0.15,
        ContainerType.DRY_45FT: 0.10,
    }
    for p in ports:
        tier = _PORT_TIER.get(p, 0.25)
        for k in ctypes:
            liq = _market_liquidity[k]
            # Short-term: max containers leasable over entire horizon
            cap_short[(p, k)] = int(tier * liq * 2000)
            # Long-term: max injectable per day
            daily_cap = max(5, int(tier * liq * 30))
            for t in range(horizon + 1):
                cap_long[(p, k, t)] = daily_cap

    return cap_short, cap_long


# ============================================================
# MAIN DATASET BUILDER
# ============================================================

def get_world_2_dataset() -> World2Data:
    """
    Constructs and returns the full Test World 2 dataset with all MILP parameters.
    All 20 equation families from the documentation are seeded with data here.
    """
    HORIZON = 84  # 12 weeks

    # ── Core entities ────────────────────────────────────────────────────────
    ctypes  = _build_container_types()
    ports   = _build_ports()
    vessels = _build_vessels()
    legs    = _build_voyage_legs(HORIZON)
    bks     = _build_bookings(HORIZON)

    # ── Cost parameters ──────────────────────────────────────────────────────
    (repo_costs, lease_short, lease_long, hold_costs,
     lift_on, lift_off, delay_pens, shortage_pens) = _build_costs(ports, ctypes, bks)

    # ── Inventory ────────────────────────────────────────────────────────────
    init_inv  = _build_initial_inventory(ports, ctypes)
    store_cap = _build_storage_caps(ports, ctypes)

    # ── Lease caps ───────────────────────────────────────────────────────────
    cap_short, cap_long = _build_lease_caps(ports, ctypes, HORIZON)

    # ── Forecast parameters ──────────────────────────────────────────────────
    D, R = _build_forecasts(ports, ctypes, HORIZON)
    G    = _build_in_transit_pipeline(ports, ctypes, HORIZON)
    mu_D, sg_D, mu_R, sg_R = _build_forecast_errors(ports, ctypes, HORIZON)
    SS   = _compute_safety_stocks(ports, ctypes, HORIZON, sg_D, mu_D, sg_R)

    # ── Historical data ──────────────────────────────────────────────────────
    hist_D, hist_R, hist_I = _build_historical_data(ports, ctypes)

    return World2Data(
        base_date=date(2026, 9, 1),
        horizon_days=HORIZON,
        ports=ports,
        container_types=ctypes,
        vessels=vessels,
        voyage_legs=legs,
        bookings=bks,
        initial_inventory=init_inv,
        repositioning_costs=repo_costs,
        leasing_costs=lease_short,
        holding_costs=hold_costs,
        shortage_penalties=shortage_pens,
        safety_stock_penalty=500.0,
        # World-2 specific
        leasing_costs_long=lease_long,
        lift_on_costs=lift_on,
        lift_off_costs=lift_off,
        delay_penalties=delay_pens,
        demand_forecast=D,
        return_forecast=R,
        in_transit_pipeline=G,
        demand_error_mean=mu_D,
        demand_error_std=sg_D,
        return_error_mean=mu_R,
        return_error_std=sg_R,
        safety_stocks=SS,
        lease_cap_short=cap_short,
        lease_cap_long=cap_long,
        storage_capacity=store_cap,
        historical_demand=hist_D,
        historical_returns=hist_R,
        historical_inventory=hist_I,
    )
