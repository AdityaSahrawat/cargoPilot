# Business workflow

## Purpose

This document describes the end‑to‑end business workflow around CargoPilot: from initial booking requests to CargoPilot's equipment planning, recommendation, and the planner's operational decision.

CargoPilot operates within a carrier's domain and focuses on managing that carrier's container equipment across ports and depots.

## Overall workflow (high level)

1. Shipper needs to move goods
2. Selects carrier and service
3. Booking request submitted
4. Carrier accepts / rejects / waitlists
5. Confirmed booking enters CargoPilot boundary
6. CargoPilot: reconstruct current state, forecast demand, plan & optimize
7. Recommended equipment plan produced
8. Planner reviews (approve / modify / reject)
9. Operational execution

Visual summary:

Shipper → Carrier → Booking → Carrier decision → Confirmed booking

CARGOPILOT BOUNDARY:

Current equipment state + Confirmed bookings + Known future movements + Forecasts + Operational constraints → Optimization → Recommended plan → Planner → Execution

---

## External booking workflow (steps 1–3)

1. Shipper identifies transportation need (origin, destination, required date, cargo characteristics, container type, quantity). This selection process is outside CargoPilot.

2. Booking request: shipper submits a request to a carrier including origin, destination, container type, quantity, pickup/shipping date and cargo details. At this point the request is not a confirmed commitment.

3. Carrier evaluates the booking considering vessel/voyage capacity, existing bookings, equipment requirements, service availability, customer contracts, and operational constraints. The carrier may accept, reject, or waitlist the request. This booking decision is handled by existing carrier processes and is outside CargoPilot's core scope.

---

## CargoPilot workflow (steps 4–10)

CargoPilot operates on confirmed bookings and operational data.

4. Reconstruct current equipment state

- Build a snapshot of all relevant equipment: individual containers, types, locations, availability, assignments, in‑transit assets, and assets under repair.

5. Incorporate known future movements

- Include vessel/voyage schedules, containers already assigned, expected arrivals and committed movements. These are deterministic inputs (not forecasts).

6. Estimate future demand (forecast)

- Use confirmed bookings, historical flows, and operational data to estimate additional equipment needs by location and time window. Forecasts are probabilistic and handled differently from confirmed bookings.

7. Equipment planning & optimization

- Combine current state, confirmed bookings, forecasts, known future movements, capacity, connectivity, leasing options, constraints, and cost models.
- The optimizer evaluates joint actions such as assigning equipment, repositioning, leasing, prioritizing demand, or accepting temporary shortages.

8. Produce recommendation

- Output a recommended equipment plan describing allocations, repositioning actions, leasing suggestions, prioritized demand, estimated costs and impacts, and key constraints/risks.

9. Planner review

- A human planner reviews the recommendation and may approve, modify, or reject it. CargoPilot is a decision‑support tool, not an automated decision authority.

10. Operational execution

- Approved actions are pushed to or entered into existing operational systems. Resulting operational events feed back into CargoPilot for continuous state reconstruction and iterative planning.

---

## Continuous planning cycle

Events → Current state → Future requirements → Optimization → Recommendation → Planner decision → Operational execution → New events → (repeat)

---

## Implementation notes / next steps

- Identify integration points with carrier booking and operational systems (bookings, vessel schedules, event streams).
- Design event schema for movement and execution events to feed state reconstruction.
- Define SLAs and human‑in‑the‑loop approval flows for planner interventions.



