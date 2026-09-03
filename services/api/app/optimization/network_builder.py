"""
CargoPilot Network Builder — Generic (World 1 + World 2)
=========================================================
Builds a time-expanded space-time network and discovers all feasible
candidate paths for every accepted booking. Supports:

  - Direct single-leg paths
  - Multi-leg paths on the SAME continuous voyage rotation
  - 2-hop transshipment  (two different voyages, one hub)
  - 3-hop transshipment  (three voyages, two intermediate hubs)

Works with any data object that exposes:
  .bookings, .voyage_legs, .ports, .horizon_days
(Duck-typed — compatible with World1Data and World2Data.)
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

from app.db.enums import ContainerType


@dataclass
class CandidatePath:
    path_id: str
    booking_id: str
    legs: List[Any]          # List[VoyageLegFixture] (World 1 or 2, same structure)
    origin_unlocode: str
    destination_unlocode: str
    departure_day: int
    arrival_day: int
    transit_days: int
    container_type: ContainerType


@dataclass
class NetworkGraph:
    ports: Dict[str, Any]              # Dict[str, PortFixture]
    voyage_legs: List[Any]             # List[VoyageLegFixture]
    booking_candidate_paths: Dict[str, List[CandidatePath]]
    horizon_days: int


class NetworkBuilder:
    """
    Generic time-expanded network builder.
    Accepts any data object with .bookings, .voyage_legs, .ports, .horizon_days.
    """

    # Maximum transshipment wait at an intermediate hub (days)
    MAX_TRANSSHIP_WAIT: int = 10
    # Maximum number of intermediate hubs (2 = 3-hop)
    MAX_HUBS: int = 2

    def __init__(self, data: Any):
        self.data = data
        # Index legs by departure port for fast lookup
        self._legs_from: Dict[str, List[Any]] = {}
        for leg in data.voyage_legs:
            self._legs_from.setdefault(leg.from_port_unlocode, []).append(leg)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_network(self) -> NetworkGraph:
        booking_paths: Dict[str, List[CandidatePath]] = {}
        for b in self.data.bookings:
            paths = self._find_paths(b)
            booking_paths[b.booking_id] = paths
        return NetworkGraph(
            ports=self.data.ports,
            voyage_legs=self.data.voyage_legs,
            booking_candidate_paths=booking_paths,
            horizon_days=self.data.horizon_days,
        )

    # ------------------------------------------------------------------
    # Internal path discovery
    # ------------------------------------------------------------------

    def _find_paths(self, booking: Any) -> List[CandidatePath]:
        paths: List[CandidatePath] = []
        seen: set = set()

        origin = booking.origin_unlocode
        dest   = booking.destination_unlocode
        earliest_dep = booking.cargo_ready_day
        deadline     = booking.delivery_deadline_day

        # ── 1. Direct paths (single leg OR consecutive legs on same voyage) ──
        paths += self._direct_paths(booking, origin, dest, earliest_dep, deadline, seen)

        # ── 2. Transshipment paths (up to MAX_HUBS intermediate hubs) ────────
        for leg1 in self._legs_from.get(origin, []):
            if leg1.departure_day < earliest_dep:
                continue
            if leg1.departure_day > deadline:
                break

            hub1 = leg1.to_port_unlocode
            # 2-hop: origin → hub1 → dest
            paths += self._transship_paths(
                booking, [leg1], hub1, dest,
                min_dep_at_hub=leg1.arrival_day,
                deadline=deadline,
                seen=seen,
                depth=0,
            )

        return paths

    def _direct_paths(
        self,
        booking: Any,
        origin: str,
        dest: str,
        earliest_dep: int,
        deadline: int,
        seen: set,
    ) -> List[CandidatePath]:
        """Direct single-leg AND same-voyage multi-leg paths."""
        paths: List[CandidatePath] = []

        # Group legs by voyage number for contiguous-leg search
        voyage_groups: Dict[str, List[Any]] = {}
        for leg in self.data.voyage_legs:
            voyage_groups.setdefault(leg.voyage_number, []).append(leg)

        for voy_num, v_legs in voyage_groups.items():
            sorted_legs = sorted(v_legs, key=lambda l: l.departure_day)
            n = len(sorted_legs)
            for i in range(n):
                if sorted_legs[i].from_port_unlocode != origin:
                    continue
                if sorted_legs[i].departure_day < earliest_dep:
                    continue
                for j in range(i, n):
                    if sorted_legs[j].to_port_unlocode != dest:
                        continue
                    leg_seq = sorted_legs[i : j + 1]
                    if not _is_contiguous(leg_seq):
                        continue
                    first, last = leg_seq[0], leg_seq[-1]
                    if last.arrival_day > deadline + 6:  # allow slight overshoot
                        continue
                    pid = f"PATH_CONT_{booking.booking_id}_{voy_num}_{first.leg_id}_to_{last.leg_id}"
                    if pid in seen:
                        continue
                    seen.add(pid)
                    paths.append(CandidatePath(
                        path_id=pid,
                        booking_id=booking.booking_id,
                        legs=leg_seq,
                        origin_unlocode=origin,
                        destination_unlocode=dest,
                        departure_day=first.departure_day,
                        arrival_day=last.arrival_day,
                        transit_days=last.arrival_day - first.departure_day,
                        container_type=booking.container_type,
                    ))
        return paths

    def _transship_paths(
        self,
        booking: Any,
        prefix_legs: List[Any],
        hub: str,
        dest: str,
        min_dep_at_hub: int,
        deadline: int,
        seen: set,
        depth: int,
    ) -> List[CandidatePath]:
        """
        Recursive transshipment path builder.
        depth=0 → looking for 1st hub connection (2-hop total)
        depth=1 → looking for 2nd hub connection (3-hop total)
        """
        paths: List[CandidatePath] = []
        origin = booking.origin_unlocode

        for leg2 in self._legs_from.get(hub, []):
            # Must depart after connection vessel arrives (+ 0 tolerance, same-day ok)
            if leg2.departure_day < min_dep_at_hub:
                continue
            # Transshipment wait must be reasonable
            if leg2.departure_day - min_dep_at_hub > self.MAX_TRANSSHIP_WAIT:
                continue
            # Don't reuse the same voyage as any prefix leg
            prefix_voyages = {l.voyage_number for l in prefix_legs}
            if leg2.voyage_number in prefix_voyages:
                continue
            if leg2.arrival_day > deadline + 6:
                continue

            # ── Destination reached ──────────────────────────────────────
            if leg2.to_port_unlocode == dest:
                leg_seq = prefix_legs + [leg2]
                pid = f"PATH_XSHIP_{booking.booking_id}_" + "_".join(l.leg_id for l in leg_seq)
                if pid not in seen:
                    seen.add(pid)
                    first, last = leg_seq[0], leg_seq[-1]
                    paths.append(CandidatePath(
                        path_id=pid,
                        booking_id=booking.booking_id,
                        legs=leg_seq,
                        origin_unlocode=origin,
                        destination_unlocode=dest,
                        departure_day=first.departure_day,
                        arrival_day=last.arrival_day,
                        transit_days=last.arrival_day - first.departure_day,
                        container_type=booking.container_type,
                    ))

            # ── Recurse for another hub (if depth allows) ─────────────────
            elif depth < self.MAX_HUBS - 1:
                paths += self._transship_paths(
                    booking,
                    prefix_legs + [leg2],
                    hub=leg2.to_port_unlocode,
                    dest=dest,
                    min_dep_at_hub=leg2.arrival_day,
                    deadline=deadline,
                    seen=seen,
                    depth=depth + 1,
                )

        return paths


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_contiguous(legs: List[Any]) -> bool:
    """Check that consecutive legs connect port-to-port without gaps."""
    for i in range(len(legs) - 1):
        if legs[i].to_port_unlocode != legs[i + 1].from_port_unlocode:
            return False
    return True
