## Optimization model (V1)

### 1. Purpose

Defines the V1 deterministic optimization problem for CargoPilot: decide how a single carrier should use, reposition, lease, and retain container equipment over a multi‑period planning horizon to satisfy demand at minimum operational cost.

### 2. Optimization goal

Find the lowest‑cost feasible equipment plan across the planning horizon by jointly optimizing assignment, repositioning, leasing, inventory retention, backlog and shortage decisions.

Example (week summary):

- Use existing equipment: 60
- Reposition: 20
- Lease: 10
- Forecast backlog: 5
- Confirmed shortage: 0

### 3. Scope (V1)

Includes:

- Single carrier
- Multiple locations
- Weekly periods (aggregate quantities)
- Confirmed + forecast demand
- Empty returns, repositioning, leasing
- Inventory holding, backlog, shortage penalties

Excludes (for now): individual container IDs, vessel scheduling, carrier booking acceptance, stochastic optimization, emissions, street‑turn matching, and advanced stowage planning.

### 4. Planning horizon

- Time unit: one week
- Horizon: 10 weeks (T = {1..10})

Weekly periods are used because repositioning opportunities are tied to scheduled vessel/service movements.

### 5. Locations and types

- L: set of locations (ports, depots). Example: {Mumbai, Dubai, Chennai}
- K: set of container types (start with a single type, e.g. 40ft dry; treat types as separate pools)

### 6. Movement network

- A ⊆ L × L: feasible movement arcs where repositioning is operationally possible. Not all pairs are connected; arcs reflect vessel/service opportunities and permitted transport options.

### 7. Input parameters

- Initial inventory I_{l,k,0}: usable empty containers of type k at location l at t=0
- Confirmed demand D^C_{l,k,t}
- Forecast demand D^F_{l,k,t}
- Empty returns R_{l,k,t}
- Repositioning capacity Cap_{i,j,k,t}
- Repositioning lead time LT_{i,j}
- Leasing capacity LeaseCap_{l,k,t}

For deterministic V1: D_{l,k,t} = D^C_{l,k,t} + D^F_{l,k,t} (streams are tracked separately)

### 8. Cost parameters

- Repositioning cost c^R_{i,j,k,t}
- Leasing cost c^L_{l,k,t}
- Holding cost c^H_{l,k,t}
- Forecast backlog cost c^B_{l,k,t}
- Confirmed shortage penalty c^S_{l,k,t}

Confirmed shortage penalty should be significantly higher than forecast backlog cost.

### 9. Decision variables

- I_{l,k,t}: ending inventory at location l, type k, period t
- y_{i,j,k,t}: repositioned units from i→j in period t
- z_{l,k,t}: leased units obtained at l in period t
- x^C_{l,k,t}, x^F_{l,k,t}: demand served for confirmed and forecast streams
- B^F_{l,k,t}, B^C_{l,k,t}: forecast & confirmed backlog carried forward
- s^C_{l,k,t}: confirmed shortage after allowed window
- w_{l,k,t}: leased units returned/off‑hired in t

### 10. Core constraints

Inventory balance (for each l,k,t):

I_{l,k,t} = I_{l,k,t-1} + R_{l,k,t} + z_{l,k,t} + RepositionIn_{l,k,t} - x^C_{l,k,t} - x^F_{l,k,t} - RepositionOut_{l,k,t} - w_{l,k,t}

Demand balance:

- Confirmed demand either served, backlogged (limited age), or becomes confirmed shortage.
- Forecast demand can be served or backlogged across periods.

Shared equipment pool:

x^C_{l,k,t} + x^F_{l,k,t} ≤ AvailableInventory_{l,k,t}

Repositioning capacity:

∑_k y_{i,j,k,t} ≤ Cap_{i,j,t}

Lead time:

y_{i,j,k,t} arrives at destination after LT_{i,j} periods (inventory becomes available at t + LT_{i,j}).

Leasing limits:

z_{l,k,t} ≤ LeaseCap_{l,k,t}

Non‑negativity / integrality:

All quantities ≥ 0. For V1 prototype, variables may be continuous; enforce integer variables for MILP as needed.

### 11. Objective

Minimize total operational cost over the horizon:

min CH + CR + CL + CB + CS

where

CH = ∑_{l,k,t} c^H_{l,k,t} I_{l,k,t}
CR = ∑_{i,j,k,t} c^R_{i,j,k,t} y_{i,j,k,t}
CL = ∑_{l,k,t} c^L_{l,k,t} z_{l,k,t}
CB = ∑_{l,k,t} c^B_{l,k,t} B^F_{l,k,t}
CS = ∑_{l,k,t} c^S_{l,k,t} s^C_{l,k,t}

The optimizer searches for the lowest‑cost feasible plan across the complete 10‑week horizon.

### 12. Joint optimization rationale

Decisions (allocation, repositioning, leasing, prioritization, and delays) are solved jointly so the optimizer can compare mixed strategies rather than sequentially picking a single action type.

### 13. Model class & implementation notes

- V1: deterministic multi‑period, multi‑location inventory flow model with repositioning, leasing, backlog, and shortage.
- Practical formulation: MILP (integer variables). Prototype can start with continuous LP to validate behavior, then enforce integrality.

### 14. Example output

A recommended plan (per week) listing repositioning orders, leases, and expected returns; summary totals (total repositioned, leased, backlog, shortage) and estimated cost.

### 15. Extensions (V2+)

Potential future additions:

- Multiple container types (expanded)
- Stochastic / robust demand modeling
- Energy / CO₂ and emissions constraints
- Street‑turn and more detailed transport modeling
- More complex leasing contracts and pricing
- Integration with vessel scheduling and stowage

---

Next steps: convert the model into a small prototype solver (LP/MIP) with synthetic test cases and verification harness.

