CargoPilot Master MILP — V1
0. What the optimizer actually decides
For every planning run,4 CargoPilot answers:
1. Which voyage/path should serve each accepted booking?
2. Which equipment type/container quantity should be assigned?
3. Where should empty containers be repositioned?
4. Should we use existing equipment or lease?
5. When should empty containers be moved?
6. How much inventory should remain at every location?
7. How should current decisions affect future inventory?
8. What should happen when everything cannot be satisfied?
Booking acceptance itself is outside the optimizer.
So:
Commercial system
       ↓
Booking accepted
       ↓
CargoPilot MILP
       ↓
Voyage + equipment + repositioning + leasing

1. Planning dimensions
We use:
i, j ∈ P
locations/ports
k ∈ K
equipment types
t ∈ T
planning periods
v ∈ V
voyages
b ∈ B
accepted bookings
p ∈ Pb
feasible paths for booking b.
A path could be:
China → USA
or
China → USA → Africa → Middle East
depending on the actual network.
This path-based representation is supported by Hu et al., while the time-expanded flow concept comes from ECO/Neely.

2. Parameters
A. Initial inventory
I⁰i,k
Usable empty containers at location i.

B. Forecast demand
Di,k,t
Expected future empty-container requirement.

C. Forecast returns
Ri,k,t
Expected containers becoming empty/available.
These are inputs, not optimization decisions. Neely explicitly treats customer returns as exogenous.

D. Already-in-transit containers
Gi,k,t
Containers already scheduled to arrive at location i at time t.
ECO explicitly includes this type of flow.

3. Booking parameters
For every accepted booking b:
Qb
quantity.
ob
origin.
db
destination.
Kb
compatible equipment types.
ETb
earliest acceptable departure.
LTb
latest acceptable delivery/service time.
We also have:
prioritybpriority_b
and therefore a different penalty for delaying/unserving different bookings.

4. Voyage parameters
For every voyage v:
originv, destinationv, departurev, arrivalv, CapvTEU, Capvweight
and:
BookedvTEU
existing/committed laden cargo capacity.
Therefore:
AvailableCapvTEU = CapvTEU − BookedvTEU
This is consistent with Dong & Song's observation that laden containers have priority and empty repositioning uses remaining vessel capacity.

5. Cost parameters
We need:
ci,j,k,vempty
empty repositioning cost.
ci,k,tleaseShort
short-term lease cost.
ci,k,tleaseLong
long-term lease cost.
ci,k,thold
inventory holding cost.
ci,kload
loading cost.
ci,kunload
unloading cost.
cbdelay
booking delay penalty.
cbshort
unserved booking penalty.
These cost categories are supported across ECO, Neely, Dong & Song, and Hu.

6. Safety-stock parameters
SSi,k,t
required safety stock.
It can be derived from forecast uncertainty and service level.
ECO provides the basic safety-stock formulation using forecast-error statistics and a service-level factor, and extends it using vessel arrival uncertainty and unloading timing.

7. Core decision variable #1 — booking assignment
Define:
xb,p,k ∈ Z ≥ 0
Number of containers from booking b, using equipment type k, assigned to path p.
This is the key CargoPilot extension.
Example:
Booking B123
100 × 40HC
China → USA

Candidate:
P1 = Voyage V101 direct
P2 = Voyage V103 direct
P3 = V101 → V205
MILP may decide:
x[B123,P1,40HC] = 0
x[B123,P2,40HC] = 100
or split it if the business allows splitting.

8. Booking fulfillment constraint
For every accepted booking:
∑(p∈Pb) ∑(k∈Kb) xb,p,k + Ub = Qb
where:
Ub ≥ 0
is unserved quantity.
If accepted bookings must always be fulfilled, we can instead set:
Ub = 0
and make the model infeasible if there genuinely isn't enough capacity/equipment.
For V1, I recommend keeping U_b with a very large penalty, because it gives the optimizer a controlled failure mode rather than simply crashing.

9. Voyage capacity constraint
For every voyage v:
∑(b,p,k) TEUk · Ab,p,v · xb,p,k + ∑(i,j,k) TEUk · Xi,j,k,v ≤ CapvTEU
where:
Ab,p,v = 1
if path p uses voyage v.
And:
Xi,j,k,v
is empty-container repositioning on voyage v.
This is the critical coupling:
               Voyage capacity
                      │
          ┌───────────┴───────────┐
          ↓                       ↓
     Accepted cargo          Empty containers
          │                       │
          └───────────┬───────────┘
                      ↓
                  ONE MILP
The capacity formulation is directly grounded in the research.

10. Vessel weight constraint
Similarly:
∑(b,p,k) Weightk · Ab,p,v · xb,p,k + ∑(i,j,k) Weightk · Xi,j,k,v ≤ Capvweight
Chang et al. explicitly use both TEU and deadweight constraints.

11. Empty repositioning variable
Xi,j,k,v ∈ Z ≥ 0
Meaning:
number of empty containers of type k moved from i to j using voyage v.
This is directly based on the ECO/Neely flow structure.
For general transport:
Xi,j,k,m,t
where m could be:
vessel
truck
rail
barge
chartered slot
Chang supports this multimode representation.

12. Empty inventory variable
Ii,k,t ≥ 0
Number of empty containers available at location i.

13. The most important constraint — inventory conservation
The basic equation is:
Ii,k,t+1 = Ii,k,t + Ri,k,t + Gi,k,t + INi,k,t − OUTi,k,t − EUsedi,k,t
where:
R = returns
G = already-in-transit arrivals
IN = repositioned containers arriving
OUT = repositioned containers leaving
EUsed = empty containers consumed by accepted bookings.
This is the CargoPilot version of Neely's inventory conservation equation.

14. Booking consumes empty inventory
Suppose booking b originates at location o_b.
Then:
EUsedob,k,t = ∑(b,p) xb,p,k,t
for the appropriate pickup/loading period.
Therefore:
100 containers available
       ↓
Booking needs 60
       ↓
inventory = 40
The optimizer cannot magically use those 60 containers again.

15. Booking creates future empty inventory
After the laden journey:
Origin
  ↓
empty
  ↓
booking loaded
  ↓
laden voyage
  ↓
destination
  ↓
cargo unloaded
  ↓
empty
  ↓
available again
Therefore the booking itself eventually produces:
ReturnFromBookingdb,k,t
after the appropriate turnaround/devanning time.
Hu explicitly models the transition from laden container to empty/reusable container through turnaround timing.
This is important because the booking decision has future consequences.

16. Safety-stock constraint
For every location/type/time:
Ii,k,t ≥ SSi,k,t
This means CargoPilot cannot use every available empty container today just because today's movement is cheap.
Example:
China inventory = 1,000

Today's cheap repositioning opportunity = 700

Safety stock = 500
Maximum it can safely reposition:
1,000 - 500 = 500
This is one of the main principles coming from ECO/Neely.

17. Your "5 weeks from now" scenario
This model naturally handles it.
Suppose:
Week 5:
China expected shortage = 500
The optimizer can compare:
Option A
Move 500 now
Option B
Move 300 now
Lease 200 later
Option C
Move 500 through a cheap intermediate voyage
Option D
Use containers returning from USA
Option E
Use spare capacity on another voyage
And it evaluates the whole planning horizon, not just Week 5.

18. Short-term leasing variable
Lb,k,tshort ∈ Z ≥ 0
Short-term leased containers used for a booking.
Hu explicitly models short-term leasing as an alternative to using owned containers.
Then booking fulfillment becomes:
OwnedUsed+ShortLease+Unserved=DemandOwnedUsed + ShortLease + Unserved = Demand
19. Long-term leasing variable
Li,k,tlong ∈ Z ≥ 0
Containers added through longer-term leasing.
They become part of the available fleet/inventory subject to the lease's timing.
Hu explicitly distinguishes short-term and long-term leasing.

20. Leasing constraint
For example:
Li,k,tshort ≤ LeaseAvailabilityi,k,tshort
and:
Li,k,tlong ≤ LeaseAvailabilityi,k,tlong
plus lease-duration/return constraints.
The exact contract structure will be configurable.

21. The critical economic trade-off
CargoPilot should not explicitly say:
"If lease price < repositioning price, lease."
Instead, the MILP should naturally discover it.
Because:
Repositioning today
        ↓
uses a container
        ↓
changes inventory at origin
        ↓
may cause future shortage
        ↓
may affect future booking
        ↓
may require another repositioning
while:
Lease today
    ↓
costs money
    ↓
but preserves owned inventory
    ↓
may avoid future repositioning
Hu's guide leasing price research supports exactly this economic relationship, but the master MILP should evaluate the network-wide consequences, rather than use a standalone threshold.

22. Multi-leg repositioning
This is where the time-expanded network becomes powerful.
We do not need a special variable:
China → USA → Africa → Middle East → China
Instead:
X(China,USA,V1)
          ↓
X(USA,Africa,V2)
          ↓
X(Africa,MiddleEast,V3)
          ↓
X(MiddleEast,China,V4)
The inventory balance connects them.
Example:
Week 1
China → USA
        ↓
Week 3
USA → Africa
        ↓
Week 5
Africa → Middle East
        ↓
Week 7
Middle East → China
The solver can discover this if the corresponding arcs/voyages exist.

23. Flow feasibility
For every movement:
Xi,j,k,v ≤ AvailableEmptyi,k,t
You cannot move more containers than actually exist.
And:
Xi,j,k,v ≤ CapacityAvailablev
24. Transportation-mode selection
If we allow multiple modes:
zi,j,m,t ∈ {0, 1}
and:
Xi,j,k,m,t ≤ M · zi,j,m,t
with:
∑(m) zi,j,m,t ≤ 1
where business rules require a single mode.
Chang explicitly provides the foundation for this mode-selection structure.
For V1, however, I would keep mode selection simple rather than immediately making it extremely granular.

25. Booking timing constraint
For each assigned path:
Departureb,p ≥ ETb
and:
Arrivalb,p ≤ LTb + Delayb
where:
Delayb ≥ 0
26. Path feasibility
We only generate valid paths.
So the MILP doesn't have to discover:
Is China → Antarctica → USA possible?
The network-generation layer should already eliminate impossible paths.
MILP chooses among:
valid path 1
valid path 2
valid path 3
...
This keeps the model computationally manageable.

27. Equipment compatibility
For every booking:
xb,p,k = 0
if equipment type k is incompatible with booking b.
This handles:
20DV
40DV
40HC
45HC
reefer
special equipment
...

28. Inventory capacity
If a depot has physical storage limits:
Ii,k,t ≤ StorageCapi,k
This should be optional because not every location has the same practical constraint.

29. Loading/unloading constraints
The Neely model gives the binary logic:
ui,k,t + vi,k,t ≤ 1
to prevent incompatible simultaneous operations.
And corresponding big-M constraints connect the operational binaries to the flow.
For CargoPilot, we can initially simplify these unless loading/unloading capacity is a real bottleneck.

30. Objective function
This is the heart of the optimizer.
For CargoPilot V1:
min Z = Creposition + Clease + Cholding + Chandling + Cdelay + Cunserved + Cother
Expanded:
min Z = ∑ c_empty · X + ∑ c_shortLease · L_short + ∑ c_longLease · L_long + ∑ c_hold · I + ∑ c_load · UP + ∑ c_unload · DOWN + ∑ c_delay · Delay + ∑ c_short · U
The research supports these cost categories, although the actual CargoPilot coefficients are not supplied by the papers and must come from operational/business data.

31. Why this objective solves your original problem
Suppose:
China shortage in 5 weeks
The model sees:
Reposition now
+ reposition cost
+ possible inventory impact
+ possible future shortage
Lease
+ lease cost
- preserves existing inventory
Wait
+ risk of future shortage
+ shortage penalty
Use another voyage
+ maybe additional transit time
- potentially cheaper transportation
Multi-leg reposition
+ several movements
- potentially much lower cost
- keeps containers productive
All of those appear inside the same objective and constraints.
That's the key.

32. Priority handling
We should not create arbitrary separate objective functions for:
priority
cost
service
inventory
Instead, priority modifies the penalty.
For example:
cbshort = BaseShortagePenalty × PriorityMultiplierb
and similarly for delay.
This follows the design principle we already established.

33. Hard vs soft constraints
This is extremely important.
Hard constraints
These should never be violated:
✓ Vessel physical capacity
✓ Vessel weight
✓ Container availability
✓ Equipment compatibility
✓ Voyage schedule
✓ Physical movement feasibility
✓ Lease availability
✓ Non-negative inventory
Soft constraints
These may be violated at a cost:
⚠ Safety stock
⚠ Booking delay
⚠ Forecast demand fulfillment
⚠ Target inventory
For example, safety stock could initially be hard:
I ≥ SS
but later become soft if real operations need more flexibility.

34. Complete high-level MILP
So the final mathematical structure is:
min Creposition + Clease + Cinventory + Chandling + Cdelay + Cshortage subject to: Booking fulfillment, Booking-path feasibility, Voyage TEU capacity, Voyage weight capacity, Laden + empty shared capacity, Empty inventory conservation, Booking equipment consumption, Booking-generated future returns, Empty repositioning availability, Safety stock, Leasing availability, Lease duration, Equipment compatibility, Storage capacity, Timing constraints, Path constraints, Operational constraints. x, X, L, I, U, Delay ≥ 0; z, u, v ∈ {0, 1}
35. The architecture I would lock
The important thing is not that we blindly implement every variable above on day one.
I would structure CargoPilot as:
                    CARGOPILOT
                         │
              ┌──────────┴──────────┐
              │                     │
          DATA LAYER           FORECAST LAYER
              │                     │
              └──────────┬──────────┘
                         ↓
                 NETWORK BUILDER
                         ↓
              feasible voyages/paths
                         ↓
                  MASTER MILP
                         │
       ┌─────────────────┼─────────────────┐
       ↓                 ↓                 ↓
   BOOKINGS          EQUIPMENT          INVENTORY
       │                 │                 │
       ↓                 ↓                 ↓
   voyage/path      owned/lease       reposition
       │                 │                 │
       └─────────────────┼─────────────────┘
                         ↓
                  GLOBAL OPTIMUM
                         ↓
                 Execution Plan

36. What comes directly from research vs our synthesis
Component
Basis
Inventory balance
Neely / ECO
Empty repositioning
ECO / Neely
Safety stock
ECO / Neely
Vessel capacity
ECO / Chang / Dong
Loaded allocation
Chang
Laden + empty interaction
Chang / Dong
Multi-mode ECR
Chang / Neely
Fleet/inventory effects
Dong
Short-term leasing
Hu
Long-term leasing
Hu
Leasing vs repositioning economics
Hu
Path-based routing
Hu
Demand uncertainty
ECO / Dong / Xiang
Robust optimization
Xiang — deferred
Single integrated master formulation
Our synthesis
Booking → voyage allocation
Our CargoPilot scope adaptation
Booking → equipment allocation
Our CargoPilot scope adaptation
Multi-leg future positioning
Our synthesis of time/path-flow concepts

This distinction matters: the papers do not give us this exact CargoPilot MILP as a ready-made equation set. They give us validated building blocks that we are integrating.

37. One thing I would NOT add yet
I would not put stochastic/robust optimization into V1.
Xiang's two-stage robust formulation and column-and-constraint generation are valuable later, but they add substantial complexity.
So:
CargoPilot V1
        ↓
Deterministic Master MILP
        ↓
Scenario testing
        ↓
V1.1
        ↓
Stochastic / robust layer
This keeps the first implementation solvable and debuggable.

