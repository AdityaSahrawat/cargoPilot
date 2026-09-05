"""
CargoPilot Data Validation Engine
==================================
Validates World 1 and World 2 datasets against logistics / business rules.

Severity levels:
  ERROR   — data is fundamentally broken; DO NOT send to optimizer.
  WARNING — plausible but suspicious; flag for investigation.
  INFO    — noteworthy observation for monitoring / demo.

Categories:
  BOOKING | VESSEL | VOYAGE | PORT | INVENTORY | DEMAND | COST | NETWORK | CONTAINER
"""

from __future__ import annotations

import math
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.db.enums import ContainerType, BookingPriority

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

SEVERITY_RANK = {"ERROR": 3, "WARNING": 2, "INFO": 1}

# Known valid TEU factors per type
_EXPECTED_TEU = {
    ContainerType.DRY_20FT:       1.0,
    ContainerType.DRY_40FT:       2.0,
    ContainerType.HIGH_CUBE_40FT: 2.0,
    ContainerType.REEFER_40FT:    2.0,
    ContainerType.DRY_45FT:       2.25,
}
_EXPECTED_TARE = {
    ContainerType.DRY_20FT:       (1.8, 2.6),  # (min, max) MT
    ContainerType.DRY_40FT:       (3.2, 4.5),
    ContainerType.HIGH_CUBE_40FT: (3.4, 4.6),
    ContainerType.REEFER_40FT:    (3.8, 5.2),
    ContainerType.DRY_45FT:       (3.6, 5.0),
}

# Statistical thresholds
Z_WARN  = 2.5   # sigma — demand anomaly warning
Z_ERROR = 4.0   # sigma — demand anomaly error

# Physically plausible transit speed: ~14 knots → ~330 nm/day
# Very rough distance guard: 1 km ≈ 0.54 nm. Typical longest legs ~12,000 km
MIN_TRANSIT_DAYS = 1
MAX_TRANSIT_DAYS = 35

# Reasonable pre-booked fraction on any single leg
MAX_PRE_BOOKED_FRAC = 0.95

# Maximum allowed booking demand as fraction of total voyage capacity
MAX_BOOKING_DEMAND_FRAC = 2.5  # can exceed 1.0 (triggers shortage), but 2.5x is extreme


@dataclass
class ValidationIssue:
    rule_id: str
    severity: str          # ERROR | WARNING | INFO
    category: str          # BOOKING | VESSEL | VOYAGE | PORT | INVENTORY | DEMAND | COST | NETWORK | CONTAINER
    entity_id: str
    message: str
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "rule_id":   self.rule_id,
            "severity":  self.severity,
            "category":  self.category,
            "entity_id": self.entity_id,
            "message":   self.message,
            "context":   self.context,
        }


@dataclass
class ValidationReport:
    world: str
    generated_at: str
    horizon_days: int
    issues: List[ValidationIssue] = field(default_factory=list)
    record_counts: Dict[str, int] = field(default_factory=dict)

    # ---- convenience ---------------------------------------------------------
    @property
    def errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "ERROR"]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "WARNING"]

    @property
    def infos(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == "INFO"]

    @property
    def blocking(self) -> bool:
        return len(self.errors) > 0

    def to_dict(self) -> Dict:
        categories: Dict[str, List] = defaultdict(list)
        for iss in self.issues:
            categories[iss.category].append(iss.to_dict())

        error_breakdown: Dict[str, int] = defaultdict(int)
        warn_breakdown:  Dict[str, int] = defaultdict(int)
        for iss in self.issues:
            if iss.severity == "ERROR":
                error_breakdown[iss.rule_id] += 1
            elif iss.severity == "WARNING":
                warn_breakdown[iss.rule_id] += 1

        total_records = sum(self.record_counts.values())
        n_errors   = len(self.errors)
        n_warnings = len(self.warnings)
        n_infos    = len(self.infos)
        n_ok       = max(0, total_records - n_errors)

        return {
            "world":        self.world,
            "generated_at": self.generated_at,
            "horizon_days": self.horizon_days,
            "blocking":     self.blocking,
            "record_counts": self.record_counts,
            "summary": {
                "total_records":   total_records,
                "records_ok":      n_ok,
                "errors":          n_errors,
                "warnings":        n_warnings,
                "infos":           n_infos,
            },
            "category_breakdown": {
                cat: {
                    "total": len(issues),
                    "errors":   sum(1 for i in issues if i["severity"] == "ERROR"),
                    "warnings": sum(1 for i in issues if i["severity"] == "WARNING"),
                    "infos":    sum(1 for i in issues if i["severity"] == "INFO"),
                }
                for cat, issues in categories.items()
            },
            "error_rule_breakdown":   dict(error_breakdown),
            "warning_rule_breakdown":  dict(warn_breakdown),
            "issues": [i.to_dict() for i in sorted(
                self.issues, key=lambda x: -SEVERITY_RANK[x.severity]
            )],
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class CargoPilotValidator:
    """
    Validates any World 1 or World 2 dataset.

    Usage:
        report = CargoPilotValidator("world_2").validate(data)
        report.to_dict()   # JSON-serialisable
    """

    def __init__(self, world_name: str = "world_2"):
        self.world = world_name
        self._issues: List[ValidationIssue] = []

    # ── public entry point ────────────────────────────────────────────────────

    def validate(self, data: Any) -> ValidationReport:
        self._issues = []
        self._data = data

        # record counts
        counts = {
            "ports":          len(data.ports),
            "vessels":        len(data.vessels),
            "voyage_legs":    len(data.voyage_legs),
            "bookings":       len(data.bookings),
            "container_types": len(data.container_types),
        }
        if hasattr(data, "historical_demand"):
            counts["historical_demand_entries"] = len(data.historical_demand)

        # run all rule groups
        self._validate_ports(data)
        self._validate_container_types(data)
        self._validate_vessels(data)
        self._validate_voyages(data)
        self._validate_bookings(data)
        self._validate_inventory(data)
        self._validate_costs(data)
        self._validate_network(data)
        self._validate_demand(data)
        if hasattr(data, "historical_demand"):
            self._validate_historical_demand(data)

        return ValidationReport(
            world=self.world,
            generated_at=datetime.now(timezone.utc).isoformat(),
            horizon_days=data.horizon_days,
            issues=self._issues,
            record_counts=counts,
        )

    # ── internal helper ───────────────────────────────────────────────────────

    def _add(self, rule_id: str, severity: str, category: str,
             entity_id: str, message: str, **ctx):
        self._issues.append(ValidationIssue(
            rule_id=rule_id, severity=severity, category=category,
            entity_id=entity_id, message=message, context=ctx,
        ))

    # =========================================================================
    # PORT RULES
    # =========================================================================

    def _validate_ports(self, data):
        seen_codes: Set[str] = set()
        for code, port in data.ports.items():
            eid = f"PORT:{code}"

            # P01 — ID uniqueness
            if code in seen_codes:
                self._add("P01", "ERROR", "PORT", eid,
                          f"Port code '{code}' is duplicated in the dataset.")
            seen_codes.add(code)

            # P02 — valid latitude / longitude
            if not (-90 <= port.latitude <= 90):
                self._add("P02", "ERROR", "PORT", eid,
                          f"Port '{code}' has invalid latitude {port.latitude}.",
                          latitude=port.latitude)
            if not (-180 <= port.longitude <= 180):
                self._add("P02", "ERROR", "PORT", eid,
                          f"Port '{code}' has invalid longitude {port.longitude}.",
                          longitude=port.longitude)

            # P03 — storage capacity sanity
            if port.storage_capacity_teu <= 0:
                self._add("P03", "ERROR", "PORT", eid,
                          f"Port '{code}' has non-positive storage capacity {port.storage_capacity_teu} TEU.")
            elif port.storage_capacity_teu < 100:
                self._add("P03", "WARNING", "PORT", eid,
                          f"Port '{code}' has very low storage capacity ({port.storage_capacity_teu} TEU). Likely a data error.",
                          capacity_teu=port.storage_capacity_teu)

            # P04 — safety stock <= storage capacity
            if port.safety_stock_teu > port.storage_capacity_teu:
                self._add("P04", "ERROR", "PORT", eid,
                          f"Port '{code}' safety stock ({port.safety_stock_teu} TEU) exceeds storage capacity "
                          f"({port.storage_capacity_teu} TEU). Constraint is infeasible.",
                          safety_stock=port.safety_stock_teu, capacity=port.storage_capacity_teu)
            elif port.safety_stock_teu > 0.5 * port.storage_capacity_teu:
                self._add("P04", "WARNING", "PORT", eid,
                          f"Port '{code}' safety stock is {port.safety_stock_teu} TEU "
                          f"({100*port.safety_stock_teu/port.storage_capacity_teu:.0f}% of capacity). "
                          f"Very tight operating window.",
                          safety_stock=port.safety_stock_teu, capacity=port.storage_capacity_teu)

            # P05 — lift costs sanity
            if hasattr(port, "lift_on_cost"):
                if port.lift_on_cost <= 0 or port.lift_off_cost <= 0:
                    self._add("P05", "ERROR", "PORT", eid,
                              f"Port '{code}' has non-positive lift cost "
                              f"(on={port.lift_on_cost}, off={port.lift_off_cost}).")
                elif port.lift_on_cost > 500 or port.lift_off_cost > 500:
                    self._add("P05", "WARNING", "PORT", eid,
                              f"Port '{code}' lift costs seem very high "
                              f"(on=${port.lift_on_cost}, off=${port.lift_off_cost}). "
                              f"Verify units — expected USD per move.",
                              lift_on=port.lift_on_cost, lift_off=port.lift_off_cost)

            # P06 — devanning lead time
            if hasattr(port, "devanning_lead_time_days"):
                if port.devanning_lead_time_days < 0:
                    self._add("P06", "ERROR", "PORT", eid,
                              f"Port '{code}' has negative devanning lead time {port.devanning_lead_time_days}.")
                elif port.devanning_lead_time_days > 10:
                    self._add("P06", "WARNING", "PORT", eid,
                              f"Port '{code}' devanning lead time is {port.devanning_lead_time_days} days — unusually long.",
                              lead_time=port.devanning_lead_time_days)

    # =========================================================================
    # CONTAINER TYPE RULES
    # =========================================================================

    def _validate_container_types(self, data):
        for ctype, spec in data.container_types.items():
            eid = f"CTYPE:{ctype.value}"

            # CT01 — TEU factor must match known standard
            expected_teu = _EXPECTED_TEU.get(ctype)
            if expected_teu and abs(spec.teu_factor - expected_teu) > 0.05:
                self._add("CT01", "WARNING", "CONTAINER", eid,
                          f"Container type '{ctype.value}' has teu_factor={spec.teu_factor}, "
                          f"expected {expected_teu}. Non-standard TEU factor will affect all capacity calculations.",
                          actual=spec.teu_factor, expected=expected_teu)

            # CT02 — tare weight in realistic range
            tare_range = _EXPECTED_TARE.get(ctype)
            if tare_range and not (tare_range[0] <= spec.tare_weight_mt <= tare_range[1]):
                self._add("CT02", "WARNING", "CONTAINER", eid,
                          f"'{ctype.value}' tare weight {spec.tare_weight_mt} MT is outside "
                          f"expected range {tare_range[0]}–{tare_range[1]} MT.",
                          tare_weight=spec.tare_weight_mt)

            # CT03 — laden weight > tare weight (obvious physics)
            if spec.total_laden_weight_mt <= spec.tare_weight_mt:
                self._add("CT03", "ERROR", "CONTAINER", eid,
                          f"'{ctype.value}' total laden weight ({spec.total_laden_weight_mt} MT) "
                          f"must exceed tare weight ({spec.tare_weight_mt} MT).",
                          laden=spec.total_laden_weight_mt, tare=spec.tare_weight_mt)

            # CT04 — cargo weight implied = total − tare
            implied_cargo = spec.total_laden_weight_mt - spec.tare_weight_mt
            if abs(implied_cargo - spec.avg_cargo_weight_mt) > 2.0:
                self._add("CT04", "INFO", "CONTAINER", eid,
                          f"'{ctype.value}' avg_cargo_weight_mt={spec.avg_cargo_weight_mt} MT does not match "
                          f"(total_laden − tare)={implied_cargo:.1f} MT. Check consistency.",
                          avg_cargo=spec.avg_cargo_weight_mt, implied=round(implied_cargo, 2))

    # =========================================================================
    # VESSEL RULES
    # =========================================================================

    def _validate_vessels(self, data):
        seen_imo: Set[str] = set()
        seen_names: Set[str] = set()

        for v in data.vessels:
            eid = f"VESSEL:{v.imo_number}"

            # V01 — IMO uniqueness
            if v.imo_number in seen_imo:
                self._add("V01", "ERROR", "VESSEL", eid,
                          f"Vessel IMO '{v.imo_number}' is duplicated.",
                          imo=v.imo_number)
            seen_imo.add(v.imo_number)

            # V02 — name uniqueness (not strictly required but suspicious)
            if v.name in seen_names:
                self._add("V02", "WARNING", "VESSEL", eid,
                          f"Vessel name '{v.name}' appears more than once — are these really different vessels?")
            seen_names.add(v.name)

            # V03 — IMO number format (IMO + 7 digits)
            if not v.imo_number.startswith("IMO") or not v.imo_number[3:].isdigit():
                self._add("V03", "WARNING", "VESSEL", eid,
                          f"IMO number '{v.imo_number}' does not follow standard IMO format (IMO followed by 7 digits).")

            # V04 — capacity > 0
            if v.container_capacity_teu <= 0:
                self._add("V04", "ERROR", "VESSEL", eid,
                          f"Vessel '{v.name}' has non-positive TEU capacity {v.container_capacity_teu}.")

            # V05 — vessel type consistent with capacity
            type_ranges = {
                "ULCV": (14000, 25000), "POST_PANAMAX": (8000, 14999),
                "PANAMAX": (4000, 7999), "CONTAINER_SHIP": (2000, 3999),
                "FEEDER": (1, 1999),
            }
            vtype_str = v.vessel_type.value if hasattr(v.vessel_type, "value") else str(v.vessel_type)
            rng = type_ranges.get(vtype_str)
            if rng and not (rng[0] <= v.container_capacity_teu <= rng[1]):
                self._add("V05", "WARNING", "VESSEL", eid,
                          f"Vessel '{v.name}' type '{vtype_str}' expected capacity {rng[0]}–{rng[1]} TEU, "
                          f"but actual capacity is {v.container_capacity_teu} TEU.",
                          teu=v.container_capacity_teu, expected_range=rng)

            # V06 — reefer plugs sanity (0–15% of TEU capacity is typical)
            if v.reefer_plugs < 0:
                self._add("V06", "ERROR", "VESSEL", eid,
                          f"Vessel '{v.name}' has negative reefer plugs ({v.reefer_plugs}).")
            elif v.reefer_plugs > v.container_capacity_teu * 0.20:
                self._add("V06", "WARNING", "VESSEL", eid,
                          f"Vessel '{v.name}' has {v.reefer_plugs} reefer plugs "
                          f"({100*v.reefer_plugs/v.container_capacity_teu:.1f}% of capacity). "
                          f"Typical is ≤15%.",
                          plugs=v.reefer_plugs, pct=round(100*v.reefer_plugs/v.container_capacity_teu, 1))

            # V07 — DWT / TEU ratio plausibility (typical 2.5–4.0 MT per TEU)
            dwt_per_teu = v.deadweight_capacity_mt / v.container_capacity_teu if v.container_capacity_teu else 0
            if not (2.0 <= dwt_per_teu <= 5.0):
                self._add("V07", "WARNING", "VESSEL", eid,
                          f"Vessel '{v.name}' DWT/TEU ratio is {dwt_per_teu:.2f} MT/TEU "
                          f"(expected 2.0–5.0). Check deadweight or capacity figure.",
                          dwt=v.deadweight_capacity_mt, teu=v.container_capacity_teu, ratio=round(dwt_per_teu, 2))

    # =========================================================================
    # VOYAGE RULES
    # =========================================================================

    def _validate_voyages(self, data):
        seen_legs: Set[str] = set()
        seen_voyages: Set[str] = set()
        vessel_names = {v.name for v in data.vessels}
        port_codes   = set(data.ports.keys())

        # Build vessel capacity lookup
        vessel_teu = {v.name: v.container_capacity_teu for v in data.vessels}
        vessel_reefer = {v.name: v.reefer_plugs for v in data.vessels}

        # Track voyage→legs for sequence validation
        voyage_legs: Dict[str, List] = defaultdict(list)
        for leg in data.voyage_legs:
            voyage_legs[leg.voyage_number].append(leg)

        for leg in data.voyage_legs:
            eid = f"LEG:{leg.leg_id}"

            # VY01 — leg_id uniqueness
            if leg.leg_id in seen_legs:
                self._add("VY01", "ERROR", "VOYAGE", eid,
                          f"Leg ID '{leg.leg_id}' is duplicated.")
            seen_legs.add(leg.leg_id)

            # VY02 — referenced vessel exists
            if leg.vessel_name not in vessel_names:
                self._add("VY02", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' references unknown vessel '{leg.vessel_name}'.",
                          vessel=leg.vessel_name)

            # VY03 — ports exist
            if leg.from_port_unlocode not in port_codes:
                self._add("VY03", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' origin port '{leg.from_port_unlocode}' does not exist.",
                          port=leg.from_port_unlocode)
            if leg.to_port_unlocode not in port_codes:
                self._add("VY03", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' destination port '{leg.to_port_unlocode}' does not exist.",
                          port=leg.to_port_unlocode)

            # VY04 — origin != destination
            if leg.from_port_unlocode == leg.to_port_unlocode:
                self._add("VY04", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' has identical origin and destination: '{leg.from_port_unlocode}'.")

            # VY05 — departure before arrival
            if leg.departure_day >= leg.arrival_day:
                self._add("VY05", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}': departure day {leg.departure_day} ≥ arrival day {leg.arrival_day}. "
                          f"Time paradox — vessel cannot arrive before it departs.",
                          departure=leg.departure_day, arrival=leg.arrival_day)

            # VY06 — transit time plausible
            transit = leg.arrival_day - leg.departure_day
            if transit < MIN_TRANSIT_DAYS:
                self._add("VY06", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' transit of {transit} day(s) is physically impossible.",
                          transit_days=transit)
            elif transit > MAX_TRANSIT_DAYS:
                self._add("VY06", "WARNING", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' transit of {transit} days is unusually long (max expected {MAX_TRANSIT_DAYS}).",
                          transit_days=transit)

            # VY07 — pre-booked fraction
            if leg.capacity_teu > 0:
                pre_frac = leg.booked_capacity_teu / leg.capacity_teu
                if pre_frac > MAX_PRE_BOOKED_FRAC:
                    self._add("VY07", "ERROR", "VOYAGE", eid,
                              f"Leg '{leg.leg_id}' pre-booked {leg.booked_capacity_teu} TEU "
                              f"out of {leg.capacity_teu} TEU capacity ({pre_frac*100:.1f}%) — exceeds {MAX_PRE_BOOKED_FRAC*100:.0f}% limit.",
                              pre_booked=leg.booked_capacity_teu, capacity=leg.capacity_teu)
                elif pre_frac > 0.60:
                    self._add("VY07", "INFO", "VOYAGE", eid,
                              f"Leg '{leg.leg_id}' is already {pre_frac*100:.1f}% pre-booked by 3rd parties. "
                              f"Limited room for CargoPilot bookings.",
                              pre_booked_pct=round(pre_frac * 100, 1))

            # VY08 — pre-booked capacity <= vessel capacity
            vteu = vessel_teu.get(leg.vessel_name, 0)
            if leg.booked_capacity_teu > vteu:
                self._add("VY08", "ERROR", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' pre-booked {leg.booked_capacity_teu} TEU "
                          f"exceeds vessel '{leg.vessel_name}' capacity of {vteu} TEU.",
                          pre_booked=leg.booked_capacity_teu, vessel_capacity=vteu)

            # VY09 — departure within planning horizon
            if leg.departure_day > data.horizon_days + 7:
                self._add("VY09", "WARNING", "VOYAGE", eid,
                          f"Leg '{leg.leg_id}' departs on day {leg.departure_day} which is "
                          f"beyond the planning horizon ({data.horizon_days} days).",
                          departure=leg.departure_day, horizon=data.horizon_days)

        # VY10 — voyage-level: check port sequence continuity
        for voy_num, legs in voyage_legs.items():
            sorted_legs = sorted(legs, key=lambda l: l.departure_day)
            for i in range(len(sorted_legs) - 1):
                curr = sorted_legs[i]
                nxt  = sorted_legs[i + 1]
                if curr.to_port_unlocode != nxt.from_port_unlocode:
                    self._add("VY10", "ERROR", "VOYAGE", f"VOY:{voy_num}",
                              f"Voyage '{voy_num}' has discontinuous port sequence: "
                              f"leg {i+1} arrives at '{curr.to_port_unlocode}' but "
                              f"leg {i+2} departs from '{nxt.from_port_unlocode}'.",
                              leg_a=curr.leg_id, leg_b=nxt.leg_id,
                              arrives_at=curr.to_port_unlocode,
                              next_departs_from=nxt.from_port_unlocode)

            # VY11 — all legs in voyage use same vessel
            vessel_set = {l.vessel_name for l in legs}
            if len(vessel_set) > 1:
                self._add("VY11", "ERROR", "VOYAGE", f"VOY:{voy_num}",
                          f"Voyage '{voy_num}' has inconsistent vessel assignments: {vessel_set}.",
                          vessels=list(vessel_set))

    # =========================================================================
    # BOOKING RULES
    # =========================================================================

    def _validate_bookings(self, data):
        seen_ids: Set[str] = set()
        port_codes = set(data.ports.keys())
        valid_ctypes = set(data.container_types.keys())

        # Build voyage network: set of port pairs reachable (any day)
        reachable_pairs: Set[Tuple[str, str]] = set()
        for leg in data.voyage_legs:
            reachable_pairs.add((leg.from_port_unlocode, leg.to_port_unlocode))

        for b in data.bookings:
            eid = f"BK:{b.booking_id}"

            # BK01 — ID uniqueness
            if b.booking_id in seen_ids:
                self._add("BK01", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' has a duplicate booking_id.")
            seen_ids.add(b.booking_id)

            # BK02 — ports exist
            if b.origin_unlocode not in port_codes:
                self._add("BK02", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' origin port '{b.origin_unlocode}' does not exist.")
            if b.destination_unlocode not in port_codes:
                self._add("BK02", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' destination port '{b.destination_unlocode}' does not exist.")

            # BK03 — origin != destination
            if b.origin_unlocode == b.destination_unlocode:
                self._add("BK03", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' has identical origin and destination: '{b.origin_unlocode}'.")

            # BK04 — quantity > 0
            if b.quantity <= 0:
                self._add("BK04", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' has non-positive quantity {b.quantity}.")

            # BK05 — container type valid
            if b.container_type not in valid_ctypes:
                self._add("BK05", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' references unknown container type '{b.container_type}'.")

            # BK06 — date sequence: cargo_ready ≤ cutoff ≤ deadline
            if b.cargo_ready_day > b.cutoff_day:
                self._add("BK06", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}': cargo_ready_day ({b.cargo_ready_day}) "
                          f"> cutoff_day ({b.cutoff_day}). Cargo can't be ready after cutoff.",
                          cargo_ready=b.cargo_ready_day, cutoff=b.cutoff_day)
            if b.cutoff_day > b.delivery_deadline_day:
                self._add("BK06", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}': cutoff_day ({b.cutoff_day}) "
                          f"> delivery_deadline ({b.delivery_deadline_day}). Deadline before cutoff is impossible.",
                          cutoff=b.cutoff_day, deadline=b.delivery_deadline_day)

            # BK07 — cargo_ready_day >= 1
            if b.cargo_ready_day < 1:
                self._add("BK07", "ERROR", "BOOKING", eid,
                          f"Booking '{b.booking_id}' cargo_ready_day is {b.cargo_ready_day} (must be ≥ 1).")

            # BK08 — deadline within or near planning horizon
            if b.delivery_deadline_day > data.horizon_days + 14:
                self._add("BK08", "WARNING", "BOOKING", eid,
                          f"Booking '{b.booking_id}' deadline day {b.delivery_deadline_day} is "
                          f"far beyond the planning horizon ({data.horizon_days} days). "
                          f"It will never be optimised in this window.",
                          deadline=b.delivery_deadline_day, horizon=data.horizon_days)

            # BK09 — cargo weight plausible
            cspec = data.container_types.get(b.container_type)
            if cspec:
                if b.cargo_weight_mt <= 0:
                    self._add("BK09", "ERROR", "BOOKING", eid,
                              f"Booking '{b.booking_id}' has non-positive cargo weight {b.cargo_weight_mt} MT.")
                elif b.cargo_weight_mt > cspec.total_laden_weight_mt:
                    self._add("BK09", "ERROR", "BOOKING", eid,
                              f"Booking '{b.booking_id}' cargo weight {b.cargo_weight_mt} MT "
                              f"exceeds max laden weight {cspec.total_laden_weight_mt} MT for '{b.container_type.value}'.",
                              cargo_wt=b.cargo_weight_mt, max_wt=cspec.total_laden_weight_mt)

            # BK10 — origin/destination pair must have a direct or 1-hop voyage path
            direct  = (b.origin_unlocode, b.destination_unlocode) in reachable_pairs
            one_hop = any(
                (b.origin_unlocode, mid) in reachable_pairs
                and (mid, b.destination_unlocode) in reachable_pairs
                for mid in port_codes
            )
            if not direct and not one_hop:
                self._add("BK10", "WARNING", "BOOKING", eid,
                          f"Booking '{b.booking_id}' ({b.origin_unlocode}→{b.destination_unlocode}) "
                          f"has no direct or 1-transshipment voyage path. May be unserviceable unless 2+ hop routes exist.",
                          origin=b.origin_unlocode, destination=b.destination_unlocode)

            # BK11 — extremely large quantity warning
            if b.quantity > 2000:
                self._add("BK11", "WARNING", "BOOKING", eid,
                          f"Booking '{b.booking_id}' requests {b.quantity} containers "
                          f"in a single booking — extremely large. Verify this is not a unit error.",
                          quantity=b.quantity)

            # BK12 — window too tight (cutoff - cargo_ready < 1 day)
            window = b.cutoff_day - b.cargo_ready_day
            if window == 0:
                self._add("BK12", "INFO", "BOOKING", eid,
                          f"Booking '{b.booking_id}' has a zero-day cargo acceptance window "
                          f"(ready=cutoff=day {b.cargo_ready_day}). Very tight logistics.",
                          window_days=window)

    # =========================================================================
    # INVENTORY RULES
    # =========================================================================

    def _validate_inventory(self, data):
        port_codes = set(data.ports.keys())
        valid_ctypes = set(data.container_types.keys())

        for (port, ctype), qty in data.initial_inventory.items():
            eid = f"INV:{port}:{ctype.value}"

            # IN01 — referenced port exists
            if port not in port_codes:
                self._add("IN01", "ERROR", "INVENTORY", eid,
                          f"Initial inventory entry references unknown port '{port}'.")

            # IN02 — referenced container type exists
            if ctype not in valid_ctypes:
                self._add("IN02", "ERROR", "INVENTORY", eid,
                          f"Initial inventory entry references unknown container type '{ctype}'.")

            # IN03 — quantity non-negative
            if qty < 0:
                self._add("IN03", "ERROR", "INVENTORY", eid,
                          f"Port '{port}' has negative initial inventory {qty} for '{ctype.value}'.",
                          quantity=qty)

            # IN04 — check against storage capacity
            if hasattr(data, "storage_capacity"):
                cap = data.storage_capacity.get((port, ctype), 0)
                if qty > cap and cap > 0:
                    self._add("IN04", "ERROR", "INVENTORY", eid,
                              f"Port '{port}' initial inventory {qty} units of '{ctype.value}' "
                              f"exceeds storage capacity {cap} units. Infeasible starting state.",
                              initial_inv=qty, capacity=cap)

        # IN05 — all ports should have non-zero inventory for at least one type
        # (a port with zero inventory for all types is suspicious)
        port_has_stock: Dict[str, bool] = defaultdict(bool)
        for (port, ctype), qty in data.initial_inventory.items():
            if qty > 0:
                port_has_stock[port] = True
        for port in data.ports:
            if not port_has_stock[port]:
                self._add("IN05", "WARNING", "INVENTORY", f"PORT:{port}",
                          f"Port '{port}' has zero initial inventory for all container types. "
                          f"Any early demand will immediately require repositioning or leasing.")

    # =========================================================================
    # COST RULES
    # =========================================================================

    def _validate_costs(self, data):
        # CO01 — repositioning costs: non-negative and not absurdly high
        for (o, d, ctype), cost in data.repositioning_costs.items():
            eid = f"COST:REPO:{o}-{d}:{ctype.value}"
            if cost < 0:
                self._add("CO01", "ERROR", "COST", eid,
                          f"Repositioning cost {o}→{d} for '{ctype.value}' is negative ({cost}).",
                          cost=cost)
            elif cost > 15000:
                self._add("CO01", "WARNING", "COST", eid,
                          f"Repositioning cost {o}→{d} for '{ctype.value}' is ${cost:,.0f} — "
                          f"very high. Verify unit is USD per container (not per TEU).",
                          cost=cost)

        # CO02 — short-term lease costs should be > repositioning (otherwise always lease)
        repo_avg = (sum(data.repositioning_costs.values()) / len(data.repositioning_costs)
                    if data.repositioning_costs else 1000)
        for (port, ctype), lease_cost in data.leasing_costs.items():
            eid = f"COST:LEASE-SHORT:{port}:{ctype.value}"
            if lease_cost < 0:
                self._add("CO02", "ERROR", "COST", eid,
                          f"Short-term lease cost at '{port}' for '{ctype.value}' is negative ({lease_cost}).")
            if lease_cost < repo_avg * 0.1:
                self._add("CO02", "WARNING", "COST", eid,
                          f"Short-term lease cost at '{port}' for '{ctype.value}' (${lease_cost:.0f}) is "
                          f"much lower than average repositioning cost (${repo_avg:.0f}). "
                          f"The optimizer will always lease instead of repositioning.",
                          lease_cost=lease_cost, avg_repo=round(repo_avg, 2))

        # CO03 — long-term lease costs (daily) should be lower than short-term equivalent
        if hasattr(data, "leasing_costs_long") and hasattr(data, "leasing_costs"):
            for (port, ctype), long_daily in data.leasing_costs_long.items():
                short_total = data.leasing_costs.get((port, ctype), None)
                if short_total is not None:
                    # If long-term daily cost × 30 days > short-term total, warn
                    if long_daily > 0 and short_total > 0:
                        long_30day = long_daily * 30
                        if long_30day > short_total * 1.5:
                            self._add("CO03", "WARNING", "COST", f"COST:LEASE-LONG:{port}:{ctype.value}",
                                      f"Long-term lease at '{port}' for '{ctype.value}' costs ${long_daily}/day "
                                      f"(${long_30day:.0f}/30 days) which is {long_30day/short_total:.1f}× "
                                      f"the short-term cost (${short_total:.0f}). "
                                      f"Optimizer will never choose long-term leasing.",
                                      long_30day=round(long_30day, 2), short_total=round(short_total, 2))

        # CO04 — shortage penalties should be ordered: CRITICAL > HIGH > NORMAL > LOW
        sp = data.shortage_penalties
        priority_order = [BookingPriority.CRITICAL, BookingPriority.HIGH,
                          BookingPriority.NORMAL, BookingPriority.LOW]
        for i in range(len(priority_order) - 1):
            hi, lo = priority_order[i], priority_order[i + 1]
            if hi in sp and lo in sp:
                if sp[hi] <= sp[lo]:
                    self._add("CO04", "WARNING", "COST", "PENALTIES",
                              f"Shortage penalty for {hi.value} (${sp[hi]:.0f}) is not greater than "
                              f"{lo.value} (${sp[lo]:.0f}). Priority ordering is violated — "
                              f"optimizer may not respect booking priorities.",
                              high_priority=hi.value, low_priority=lo.value,
                              high_penalty=sp[hi], low_penalty=sp[lo])

        # CO05 — holding costs non-negative
        for (port, ctype), hcost in data.holding_costs.items():
            if hcost < 0:
                self._add("CO05", "ERROR", "COST", f"COST:HOLD:{port}:{ctype.value}",
                          f"Holding cost at '{port}' for '{ctype.value}' is negative ({hcost}).",
                          cost=hcost)

    # =========================================================================
    # NETWORK RULES
    # =========================================================================

    def _validate_network(self, data):
        port_codes = set(data.ports.keys())

        # Build adjacency
        outbound: Dict[str, Set[str]] = defaultdict(set)
        inbound:  Dict[str, Set[str]] = defaultdict(set)
        for leg in data.voyage_legs:
            outbound[leg.from_port_unlocode].add(leg.to_port_unlocode)
            inbound[leg.to_port_unlocode].add(leg.from_port_unlocode)

        # NT01 — ports with no voyages at all (completely isolated)
        active_ports = set(outbound.keys()) | set(inbound.keys())
        for port in port_codes:
            if port not in active_ports:
                self._add("NT01", "WARNING", "NETWORK", f"PORT:{port}",
                          f"Port '{port}' ({data.ports[port].name}) has no voyage legs at all. "
                          f"It is completely isolated from the shipping network.")

        # NT02 — ports with only outbound (equipment sinks) or only inbound (equipment sources)
        only_out = {p for p in outbound if p not in inbound and p in port_codes}
        only_in  = {p for p in inbound  if p not in outbound and p in port_codes}
        for port in only_out:
            self._add("NT02", "INFO", "NETWORK", f"PORT:{port}",
                      f"Port '{port}' has only outbound legs (equipment source only). "
                      f"Empty containers must be repositioned IN from other ports — no natural returns.",
                      type="source_only")
        for port in only_in:
            self._add("NT02", "INFO", "NETWORK", f"PORT:{port}",
                      f"Port '{port}' has only inbound legs (equipment sink only). "
                      f"Empty containers will accumulate here and need repositioning OUT.",
                      type="sink_only")

        # NT03 — booking origin ports that have no outbound voyages
        booking_origins = {b.origin_unlocode for b in data.bookings}
        for port in booking_origins:
            if port in port_codes and port not in outbound:
                self._add("NT03", "ERROR", "NETWORK", f"PORT:{port}",
                          f"Port '{port}' has bookings but NO outbound voyage legs. "
                          f"All bookings from this port will be unserviceable.",
                          booking_count=sum(1 for b in data.bookings if b.origin_unlocode == port))

        # NT04 — check that at least one path exists for each booking origin→dest
        # (already done in BK10 — skip duplicate check here)

        # NT05 — flag if total CargoPilot booking demand TEU >> remaining capacity
        teu_f = {
            ContainerType.DRY_20FT: 1.0, ContainerType.DRY_40FT: 2.0,
            ContainerType.HIGH_CUBE_40FT: 2.0, ContainerType.REEFER_40FT: 2.0,
            ContainerType.DRY_45FT: 2.25,
        }
        total_cap  = sum(leg.capacity_teu for leg in data.voyage_legs)
        total_pre  = sum(leg.booked_capacity_teu for leg in data.voyage_legs)
        total_bk   = sum(b.quantity * teu_f.get(b.container_type, 2.0) for b in data.bookings)
        avail      = max(total_cap - total_pre, 1)
        demand_ratio = total_bk / avail

        if demand_ratio > MAX_BOOKING_DEMAND_FRAC:
            self._add("NT05", "WARNING", "NETWORK", "GLOBAL",
                      f"Total booking demand ({total_bk:,.0f} TEU) is {demand_ratio:.1f}× the available "
                      f"capacity after pre-bookings ({avail:,.0f} TEU). "
                      f"Expect very high shortage penalties in the MILP solution.",
                      demand_teu=round(total_bk), available_teu=round(avail), ratio=round(demand_ratio, 2))
        elif demand_ratio < 0.05:
            self._add("NT05", "INFO", "NETWORK", "GLOBAL",
                      f"Total booking demand ({total_bk:,.0f} TEU) is only {demand_ratio*100:.1f}% "
                      f"of available capacity. Very low utilisation — increase bookings for a more realistic test.",
                      demand_teu=round(total_bk), available_teu=round(avail))
        else:
            self._add("NT05", "INFO", "NETWORK", "GLOBAL",
                      f"Network utilisation: {demand_ratio*100:.1f}% of available capacity booked by CargoPilot. "
                      f"Combined (pre-booked + CargoPilot): {(total_pre+total_bk)/total_cap*100:.1f}%.",
                      demand_teu=round(total_bk), available_teu=round(avail))

    # =========================================================================
    # DEMAND FORECAST RULES
    # =========================================================================

    def _validate_demand(self, data):
        if not hasattr(data, "demand_forecast"):
            return

        horizon = data.horizon_days
        port_codes = set(data.ports.keys())

        # Check for negative demand
        for (port, ctype, t), val in data.demand_forecast.items():
            if val < 0:
                self._add("DF01", "ERROR", "DEMAND", f"DEMAND:{port}:{ctype.value}:t{t}",
                          f"Demand D[{port},{ctype.value},{t}] = {val:.3f} is negative. "
                          f"Demand must always be ≥ 0.",
                          port=port, ctype=ctype.value, day=t, value=val)

        # Aggregate by (port, ctype) across days for statistics
        series: Dict[Tuple[str, ContainerType], List[float]] = defaultdict(list)
        for (port, ctype, t), val in data.demand_forecast.items():
            if 0 <= t <= horizon:
                series[(port, ctype)].append(val)

        # DF02 — missing days in forecast
        for (port, ctype), vals in series.items():
            if len(vals) < horizon - 1:
                self._add("DF02", "WARNING", "DEMAND", f"DEMAND:{port}:{ctype.value}",
                          f"Demand forecast for [{port}, {ctype.value}] has only {len(vals)} entries "
                          f"for a {horizon}-day horizon. Missing {horizon - len(vals)} days.",
                          entries=len(vals), expected=horizon)

        # DF03 — statistical anomaly detection (z-score spike/drop)
        for (port, ctype), vals in series.items():
            if len(vals) < 5:
                continue
            mu  = statistics.mean(vals)
            if mu == 0:
                continue
            try:
                sd = statistics.stdev(vals)
            except statistics.StatisticsError:
                continue
            if sd == 0:
                continue

            for i, v in enumerate(vals):
                z = abs(v - mu) / sd
                if z >= Z_ERROR:
                    self._add("DF03", "WARNING", "DEMAND", f"DEMAND:{port}:{ctype.value}:t{i}",
                              f"Demand anomaly: D[{port},{ctype.value},day{i}] = {v:.2f} "
                              f"is {z:.1f}σ from series mean {mu:.2f}. "
                              f"Investigate: unexpected surge or data error.",
                              port=port, ctype=ctype.value, day=i, value=round(v, 3),
                              mean=round(mu, 3), std=round(sd, 3), z_score=round(z, 2))
                elif z >= Z_WARN:
                    self._add("DF03", "INFO", "DEMAND", f"DEMAND:{port}:{ctype.value}:t{i}",
                              f"Demand D[{port},{ctype.value},day{i}] = {v:.2f} "
                              f"is {z:.1f}σ from mean {mu:.2f} — notable deviation.",
                              port=port, ctype=ctype.value, day=i, value=round(v, 3),
                              mean=round(mu, 3), std=round(sd, 3), z_score=round(z, 2))

        # DF04 — demand exceeding port storage capacity (impossible steady state)
        if hasattr(data, "storage_capacity"):
            daily_totals: Dict[Tuple[str, ContainerType], float] = {}
            for (port, ctype), vals in series.items():
                if vals:
                    daily_totals[(port, ctype)] = max(vals)

            for (port, ctype), max_demand in daily_totals.items():
                cap = data.storage_capacity.get((port, ctype), 0)
                if cap > 0 and max_demand > cap:
                    self._add("DF04", "WARNING", "DEMAND", f"DEMAND:{port}:{ctype.value}",
                              f"Peak daily demand at [{port},{ctype.value}] is {max_demand:.1f} containers "
                              f"but storage capacity is only {cap}. "
                              f"Even one day of uncollected demand overflows the yard.",
                              peak_demand=round(max_demand, 1), capacity=cap)

        # DF05 — coefficient of variation sanity (CV > 1.0 is extreme volatility)
        extreme_cv_ports = []
        for (port, ctype), vals in series.items():
            if len(vals) < 5:
                continue
            mu  = statistics.mean(vals)
            if mu == 0:
                continue
            try:
                sd = statistics.stdev(vals)
            except statistics.StatisticsError:
                continue
            cv = sd / mu
            if cv > 1.0:
                extreme_cv_ports.append((port, ctype.value, round(cv, 2)))

        if len(extreme_cv_ports) > 10:
            self._add("DF05", "INFO", "DEMAND", "GLOBAL",
                      f"{len(extreme_cv_ports)} port/type pairs have coefficient of variation > 1.0. "
                      f"Demand is highly volatile — consider higher safety stock levels.",
                      count=len(extreme_cv_ports),
                      examples=[f"{p}:{c} (CV={v})" for p, c, v in extreme_cv_ports[:5]])

    # =========================================================================
    # HISTORICAL DEMAND RULES
    # =========================================================================

    def _validate_historical_demand(self, data):
        """
        Compare historical demand (negative day indices) vs. forecast.
        Flag when the forecast mean is drastically different from historical average.
        """
        if not hasattr(data, "historical_demand") or not hasattr(data, "demand_forecast"):
            return

        # Aggregate historical by (port, ctype)
        hist_series: Dict[Tuple[str, ContainerType], List[float]] = defaultdict(list)
        for (port, ctype, t), val in data.historical_demand.items():
            if t < 0 and val >= 0:
                hist_series[(port, ctype)].append(val)

        # Aggregate forecast by (port, ctype)
        fcast_series: Dict[Tuple[str, ContainerType], List[float]] = defaultdict(list)
        for (port, ctype, t), val in data.demand_forecast.items():
            if t >= 0 and val >= 0:
                fcast_series[(port, ctype)].append(val)

        for (port, ctype), hist_vals in hist_series.items():
            fcast_vals = fcast_series.get((port, ctype), [])
            if not hist_vals or not fcast_vals:
                continue

            hist_mu  = statistics.mean(hist_vals)
            fcast_mu = statistics.mean(fcast_vals)
            if hist_mu == 0:
                continue

            ratio = fcast_mu / hist_mu
            eid = f"HIST:{port}:{ctype.value}"

            # HD01 — forecast is a massive jump vs. historical (>3x)
            if ratio > 3.0:
                try:
                    hist_sd = statistics.stdev(hist_vals)
                    z = (fcast_mu - hist_mu) / (hist_sd + 0.001)
                except Exception:
                    z = None
                self._add("HD01", "WARNING", "DEMAND", eid,
                          f"Forecast demand for [{port},{ctype.value}] is {ratio:.1f}× the historical average. "
                          f"Historical avg: {hist_mu:.1f}, Forecast avg: {fcast_mu:.1f}. "
                          f"Anomaly requiring investigation — seasonal surge or data error?",
                          port=port, ctype=ctype.value,
                          hist_avg=round(hist_mu, 2), fcast_avg=round(fcast_mu, 2),
                          ratio=round(ratio, 2),
                          z_score=round(z, 2) if z is not None else None)

            # HD02 — forecast is a massive drop vs. historical (<0.2x)
            elif ratio < 0.20:
                self._add("HD02", "WARNING", "DEMAND", eid,
                          f"Forecast demand for [{port},{ctype.value}] has dropped to {ratio*100:.0f}% "
                          f"of historical average. Historical avg: {hist_mu:.1f}, Forecast avg: {fcast_mu:.1f}. "
                          f"Possible demand collapse — verify data.",
                          port=port, ctype=ctype.value,
                          hist_avg=round(hist_mu, 2), fcast_avg=round(fcast_mu, 2),
                          ratio=round(ratio, 2))

            # HD03 — check weekly seasonality consistency
            # Historical should show Mon-Wed peaks (day % 7 in {0,1,2})
            # Group by day-of-week
            dow_vals: Dict[int, List[float]] = defaultdict(list)
            all_days = list(data.historical_demand.keys())
            for (p, c, t), v in data.historical_demand.items():
                if p == port and c == ctype and t < 0:
                    dow = abs(t) % 7
                    dow_vals[dow].append(v)

            if len(dow_vals) >= 5:
                dow_means = {dow: statistics.mean(v) for dow, v in dow_vals.items() if v}
                if dow_means:
                    peak_dow = max(dow_means, key=dow_means.get)
                    trough_dow = min(dow_means, key=dow_means.get)
                    peak_ratio = dow_means[peak_dow] / (dow_means[trough_dow] + 0.001)
                    if peak_ratio > 2.5:
                        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
                        self._add("HD03", "INFO", "DEMAND", eid,
                                  f"Strong weekly seasonality at [{port},{ctype.value}]: "
                                  f"{day_names[peak_dow]} avg demand is {peak_ratio:.1f}× {day_names[trough_dow]}. "
                                  f"Ensure the forecast model captures this pattern.",
                                  peak_day=day_names[peak_dow], trough_day=day_names[trough_dow],
                                  ratio=round(peak_ratio, 2))
