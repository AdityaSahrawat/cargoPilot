
# Decision model

## 1. Purpose

This document defines the decisions CargoPilot supports and the information required to make them. CargoPilot optimizes the use and positioning of a carrier's container equipment across its network. The core question is:

> How should the carrier allocate available container equipment to satisfy confirmed and expected demand at minimum feasible cost?

## 2. Decision boundary

The carrier's booking process (before confirmation) is outside CargoPilot. CargoPilot consumes confirmed bookings and operational data and performs equipment planning that feeds a planner decision.

Shipper → Booking request → Carrier booking process → Confirmed booking

========================
     CargoPilot
========================

Confirmed booking → Equipment planning → Planner decision

---

## Decision 0 — Shipper selects carrier

Status: outside CargoPilot

Information involved:

- Cargo requirements (origin, destination, required date)
- Container type and quantity
- Carrier/service options

Output: a booking request submitted to a carrier.

---

## Decision 1 — Carrier accepts booking

Trigger: carrier receives a booking request

Question: can the carrier accept this booking?

Information required:

- Origin, destination, required date
- Container type and quantity
- Relevant vessel/voyage and existing confirmed bookings
- Available capacity, customer/contract conditions, operational constraints

Possible outcomes: accepted / rejected / waitlisted

Output: a confirmed booking when accepted. CargoPilot begins at this point.

---

## Decision 2 — Allocate existing equipment

Trigger: a confirmed booking or expected requirement needs equipment

Question: can available carrier equipment satisfy this requirement?

Information required:

- Booking/demand (type, quantity, origin, destination, required date, priority)
- Container inventory (type, current location, status, availability date, ownership/control, existing assignments)
- Operational info (existing commitments, relevant voyage/service, timing constraints)

Constraints:

- Container must be controlled by the carrier, be the correct type, be available, be able to reach the location in time, and not already be committed.

Output: an equipment allocation plan. If sufficient equipment exists, no additional supply action is required.

---

## Decision 3 — Lease additional equipment

Trigger: existing equipment is insufficient or leasing is more cost‑effective

Question: should the carrier obtain additional equipment through leasing?

Information required:

- Required type, quantity, location, availability date
- Lease availability, price, duration/terms, pickup/drop constraints

Constraints: leasing is only possible where leasing options exist.

Output: proposed lease quantity and associated cost. Leasing is treated as a supply action, not a core entity.

---

## Decision 4 — Reposition equipment

Trigger: a location projects a shortage while another has surplus

Question: should equipment be moved from another location?

Information required:

- Current equipment by location/type, projected surplus/shortage
- Origin/destination, transport routes, vessel/voyage schedules
- Movement capacity, lead time, repositioning cost, required arrival date

Constraints:

- Source cannot send more than it can spare; equipment must be the correct type; a feasible route and transport capacity must exist; lead time must suffice; repositioning must respect existing commitments.

Output: a repositioning order with origin, destination, container type, quantity, transport/voyage, expected arrival, and estimated cost.

---

## Decision 5 — Prioritize demand / accept shortage

Trigger: available and obtainable equipment cannot economically satisfy all requirements

Question: which requirements receive equipment and which shortages are accepted?

Information required:

- Confirmed bookings, forecasted demand, booking priority, required dates
- Available equipment, expected supply, cost/penalty of not satisfying demand

Constraints: higher‑priority or operationally critical requirements should be preferred.

Output: a prioritized allocation plan and any expected shortage.

---

## Decision 6 — Delay an action

Delaying an action is a possible outcome of the joint planning process rather than a separate optimization problem. For example, the optimizer may defer repositioning if forecast uncertainty makes immediate action unjustified. Firm, near‑term requirements are treated differently from uncertain forecast‑driven needs.

---

## Joint optimization (decisions 2–6)

Decisions about allocation, leasing, repositioning, prioritization, and delays must be solved jointly. The optimizer should evaluate combinations (e.g., mix of local allocation, repositioning, leasing, and accepted shortage) to find the lowest‑cost feasible plan.

Example solution mix:

- 60 containers → existing local equipment
- 20 containers → reposition from another location
- 10 containers → lease locally
- 10 containers → shortage accepted

---

## Optimization inputs

The joint planning problem uses:

- Equipment: container availability, type, location, status, existing assignments
- Demand: confirmed bookings, forecasted demand, required location/time, priority
- Network: ports, depots, vessel/voyage schedules, feasible routes, transport capacity
- Supply options: existing equipment, repositioning options, leasing options
- Costs: repositioning, leasing, holding/idle, shortage/priority penalties, other operational costs

---

## Optimization objective

Initial objective: minimize total operational cost of satisfying container requirements while respecting equipment, network, timing, and capacity constraints. The exact cost function and mathematical formulation will be defined after the business decisions and required data are finalized.

---

## Decision output

CargoPilot produces a recommended equipment plan containing:

- Equipment allocations
- Repositioning actions
- Leasing actions
- Prioritized demand
- Expected shortages
- Estimated total cost
- Alternative feasible plans
- Relevant constraints and risks

The equipment planner reviews and approves or modifies the final plan.

---

## Implementation notes / next steps

- Formalize the optimization objective and constraints as a mathematical model (LP/MIP or heuristic approach).
- Define data schemas and interfaces for required inputs (bookings, inventory, schedules, lease offers).
- Design evaluation harness for comparing plan alternatives and computing expected costs under uncertainty.


