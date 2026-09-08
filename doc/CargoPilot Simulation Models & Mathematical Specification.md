# CargoPilot Simulation Models & Mathematical Specification

> **Document:** Doc 2 — Simulation Models & Mathematical Specification  
> **Version:** V1.0 — Final for Implementation  
> **Status:** Implementation Baseline  
> **Depends On:** [Doc 1 — Simulation Engine Architecture & Behavioral Specification](file:///Users/adityasahrawat/dev/projects/cargoPilot/doc/CargoPilot-Simulation-Engine%E2%80%94Design-Specification.md)  

---

## Table of Contents

1. [Modeling Philosophy & Mathematical Framework](#1-modeling-philosophy--mathematical-framework)
2. [Simulation Time & Event-Time Calculations](#2-simulation-time--event-time-calculations)
3. [Randomness & Probability Framework](#3-randomness--probability-framework)
4. [Vessel & Voyage Model](#4-vessel--voyage-model)
5. [Port & Terminal Model](#5-port--terminal-model)
6. [Container & Equipment Model](#6-container--equipment-model)
7. [Demand Model](#7-demand-model)
8. [Booking Generation Model](#8-booking-generation-model)
9. [Allocation & 7-Day Lock Model](#9-allocation--7-day-lock-model)
10. [Import Return & Equipment Availability Model](#10-import-return--equipment-availability-model)
11. [Equipment Supply & Scarcity Model](#11-equipment-supply--scarcity-model)
12. [Leasing Model](#12-leasing-model)
13. [Repositioning Model](#13-repositioning-model)
14. [Disruption Models](#14-disruption-models)
15. [Causal & Cascading Effects](#15-causal--cascading-effects)
16. [Forecasting Model](#16-forecasting-model)
17. [Information / Visibility Model](#17-information--visibility-model)
18. [Operational Timeline Model](#18-operational-timeline-model)
19. [Failure & Exception Models](#19-failure--exception-models)
20. [Recovery Models](#20-recovery-models)
21. [Backlog Model](#21-backlog-model)
22. [Cost Models](#22-cost-models)
23. [Scenario Models](#23-scenario-models)
24. [Parameters & Configuration](#24-parameters--configuration)
25. [Shared State, PostgreSQL & Kafka Integration](#25-shared-state-postgresql--kafka-integration)
26. [Calibration & Realism](#26-calibration--realism)
27. [Validation](#27-validation)
28. [Mathematical Formula Registry](#28-mathematical-formula-registry)
29. [Model Dependency Map](#29-model-dependency-map)
30. [V1 vs Future Models](#30-v1-vs-future-models)
31. [Final Modeling Principle](#final-modeling-principle)

---

## 1. Modeling Philosophy & Mathematical Framework

### 1.1 Purpose
Doc 2 defines the mathematical, probabilistic, behavioral, and state-transition models used by the CargoPilot Simulation Engine.

**Doc 1 defines:**
- What exists
- System architecture
- Component responsibilities
- Simulation execution
- Event flow
- Interaction between Simulation Engine and CargoPilot

**Doc 2 defines:**
- How individual logistics behaviors are calculated
- How state changes
- How uncertainty is represented
- How operational consequences propagate
- Which parameters control each model

The separation between the two documents must be preserved.

### 1.2 Core Modeling Principle
The simulator models operational logistics realism, not detailed physical-world simulation.

#### V1 models:
- Vessels
- Voyages
- Vessel movement
- Ports and terminals
- Containers
- Equipment
- Demand
- Bookings
- Allocation observation
- Import returns
- Equipment availability
- Equipment scarcity
- Leasing execution
- Repositioning execution
- Disruptions
- Delays
- Failures
- Recovery
- Backlog
- Forecasts
- Information visibility
- Operational timelines
- Costs
- CargoPilot decisions
- Admin interventions

#### V1 does not model:
- Detailed ship hydrodynamics
- Engine thermodynamics
- Individual engine components
- Detailed ocean physics
- Exact weather forecasting
- Detailed crane mechanics
- Detailed worker behavior
- Complete terminal digital-twin physics

The objective is to create a sufficiently realistic operational environment in which CargoPilot's planning and optimization decisions can be tested.

### 1.3 World-State Representation
Let $S(t)$ represent the complete operational simulation state at simulation time $t$.

Conceptually:

$$S(t) = \{ P(t), V(t), Y(t), C(t), B(t), D(t), E(t), L(t), A(t), R(t) \}$$

where:
- $P(t)$: Port state
- $V(t)$: Vessel state
- $Y(t)$: Voyage state
- $C(t)$: Container state
- $B(t)$: Booking state
- $D(t)$: Demand state
- $E(t)$: Equipment availability state
- $L(t)$: Leasing state
- $A(t)$: Allocation state
- $R(t)$: Disruption/scenario state

The physical persistence of these entities is maintained in the shared CargoPilot PostgreSQL database.

### 1.4 State Transition
A simulation event or model execution transforms state:

$$S(t^+) = F(S(t^-), E, \theta, \omega)$$

where:
- $S(t^-)$: State immediately before the event
- $S(t^+)$: State immediately after the event
- $E$: Event
- $\theta$: Configured parameters
- $\omega$: Stochastic outcome
- $F$: Applicable model logic

The simulator must never regenerate the world from scratch when advancing time. Every advancement begins from the latest persisted valid state.

### 1.5 Configurable Model Parameters
Any behavior that may reasonably require:
- Operational tuning
- Scenario control
- Experimentation
- Calibration
- Business adjustment

must be represented through an explicitly named parameter rather than an unexplained hardcoded value.

**Examples:**
- `PORT_BERTH_COUNT[port_id]`
- `PORT_LOADING_RATE[port_id]`
- `BOOKING_RATE[origin][destination][equipment_type]`
- `VESSEL_BASE_SPEED_KNOTS[vessel_class]`
- `DEMAND_BASE_RATE[origin][destination][equipment_type]`
- `IMPORT_RETURN_MEAN_DAYS[equipment_type]`

Each model has:

$$\Theta_m = \{ \theta_1, \theta_2, \ldots, \theta_n \}$$

where $m$ is the model.

### 1.6 Parameter Classification

Parameters may be classified as:

| Type | Example |
| :--- | :--- |
| **Simulation** | `SIMULATION_START_TIME` |
| **Scenario** | `STORM_PROBABILITY` |
| **Operational** | `PORT_LOADING_RATE` |
| **Business** | `LEASE_COST_PER_DAY` |
| **Calibration** | `VESSEL_DELAY_FACTOR` |
| **Mathematical** | Unit conversion constant |
| **Runtime state** | `VESSEL_CURRENT_POSITION` |
| **Derived value** | `VESSEL_ETA` |

Parameters should contain:
- Name
- Model
- Description
- Value
- Unit
- Default
- Minimum
- Maximum
- Type
- Distribution if applicable
- Scope
- Admin-editable flag
- Runtime-editable flag
- Scenario override capability

### 1.7 General Model Structure
Every simulation model follows:

```text
Current State
      +
Configuration
      +
Event / External Condition
      +
Random Outcome
      ↓
Model Logic
      ↓
State Changes
      +
Generated Events
      +
Downstream Consequences
```

---

## 2. Simulation Time & Event-Time Calculations

### 2.1 Simulation Clock
The simulator maintains one authoritative virtual clock:

$$T_{\text{sim}}$$

Simulation time is independent of real-world execution time.

**Example:**
```text
Simulation:
Day 1 00:00
      ↓ NEXT DAY
Day 2 00:00
```
The real system may execute this transition in seconds.

### 2.2 Time Advancement
For an advancement:

$$T_{\text{target}} = T_{\text{current}} + \Delta t$$

V1 constraint:

$$0 < \Delta t \le 24\text{h}$$

**Supported controls:**
- `+1 HOUR`
- `+6 HOURS`
- `+12 HOURS`
- `+24 HOURS / NEXT DAY`

Longer periods are achieved through repeated advancement.

### 2.3 Event-Driven Execution
The simulator does not execute every model every simulated hour.

Instead:
```text
Current Time
    ↓
Find next relevant event
    ↓
Advance SimPy to event
    ↓
Execute event
    ↓
Update state
    ↓
Generate consequences/events
    ↓
Continue
```
This is necessary because the simulation may contain hundreds of ports and thousands of vessels.

### 2.4 Event-Time Rules
Events have:
- Event time
- Entity
- Event type
- Source
- Payload
- Causal relationship

Events occurring inside $[T_{\text{current}}, T_{\text{target}}]$ are processed chronologically. Events beyond $T_{\text{target}}$ remain scheduled.

### 2.5 Same-Time Events
When multiple events have the same simulation timestamp, execution uses a deterministic priority order.

**General priority:**
1. External/disruption activation
2. Vessel movement/arrival
3. Port/resource state changes
4. Cargo/container operational events
5. Demand generation
6. Booking generation
7. Information/forecast updates
8. CargoPilot decision events
9. Cost/accounting events
10. Persistence/event publication

The exact event registry may define more specific priorities. This ensures reproducibility.

---

## 3. Randomness & Probability Framework

### 3.1 Purpose
Randomness represents uncertainty in operational behavior.

**Examples:**
- Demand variation
- Booking arrival
- Cancellation
- Vessel delay
- Weather impact
- Mechanical failure
- Container damage
- Customer return time
- Disruption occurrence
- Recovery duration

Randomness must not replace causal relationships.

### 3.2 Reproducibility
For identical:
- Initial World
- Scenario
- Configuration
- Random Seed

the simulator must produce the same stochastic outcomes.

Formally:

$$\text{SimulationResult} = f(S_0, \Theta, \text{Scenario}, \text{Seed})$$

### 3.3 Random Number Management
The simulation maintains a controlled random-number system.

Random outcomes should be generated by model/process rather than by repeatedly checking every entity at every hour.

For example, instead of:
```python
# Every hour:
if random() < failure_probability:
    ...
```
use a time-to-event model:
```text
Schedule next failure
        ↓
Failure occurs at scheduled stochastic time
```

### 3.4 Supported Distributions
V1 may use:
- Bernoulli
- Binomial
- Poisson
- Normal
- Log-normal
- Exponential
- Gamma
- Uniform
- Empirical distributions

The distribution is selected according to the operational behavior being modeled.

### 3.5 Probability Rule
For an event with probability $p$:

$$X \sim \text{Bernoulli}(p)$$

where:

$$0 \le p \le 1$$

For event rates:

$$N_t \sim \text{Poisson}(\lambda_t)$$

where $\lambda_t$ represents expected event count in the relevant period.

### 3.6 Randomness Parameters
**Examples:**
- `MODEL_SEED`
- `MODEL_EVENT_PROBABILITY`
- `MODEL_RATE`
- `MODEL_MEAN`
- `MODEL_STANDARD_DEVIATION`
- `MODEL_MIN`
- `MODEL_MAX`
- `MODEL_DISTRIBUTION`

Model-specific names should be preferred over generic names when scope could become ambiguous.

---

## 4. Vessel & Voyage Model

### 4.1 Purpose
The vessel model represents operational vessel movement between ports. The model does not perform detailed physical maritime simulation.

### 4.2 Vessel State
A vessel contains:

```text
Vessel
├── ID
├── Vessel Class
├── Capacity
├── Current Location
├── Current Voyage
├── Status
├── Current Position
├── Current Speed
├── ETA
├── Schedule Variance
├── Current Load
└── Condition
```

**Possible statuses:**
- `AVAILABLE`
- `SCHEDULED`
- `IN_TRANSIT`
- `ARRIVED`
- `WAITING_FOR_BERTH`
- `IN_PORT`
- `DEPARTED`
- `DELAYED`
- `UNAVAILABLE`

### 4.3 Voyage State
A voyage contains:
- Vessel
- Origin
- Destination
- Scheduled departure
- Scheduled arrival
- Actual departure
- Estimated arrival
- Actual arrival
- Status
- Route distance

### 4.4 Vessel Movement
For remaining distance $D$ and effective speed $V_{\text{eff}}$:

$$T_{\text{travel}} = \frac{D}{V_{\text{eff}}}$$

Effective speed:

$$V_{\text{eff}} = V_{\text{base}} \times F_{\text{weather}} \times F_{\text{operational}}$$

where:
- $V_{\text{base}}$: Vessel base speed
- $F_{\text{weather}}$: Weather factor
- $F_{\text{operational}}$: Operational factor

### 4.5 Current Position
When an event changes vessel movement, calculation starts from the vessel's current position. It must not restart the voyage from the original departure port.

If:

$$D_{\text{remaining}} = D_{\text{route}} - D_{\text{travelled}}$$

then:

$$T_{\text{remaining}} = \frac{D_{\text{remaining}}}{V_{\text{eff}}}$$

### 4.6 Weather Impact
Weather may modify:
- Speed
- Delay probability
- Route conditions
- Port operations

**Example:**

$$V_{\text{weather}} = V_{\text{base}} \times F_{\text{weather}}$$

A storm can therefore cause:
```text
Storm
 ↓
Speed reduction
 ↓
Longer remaining travel time
 ↓
ETA change
```

### 4.7 Arrival
When a vessel reaches its destination:
```text
IN_TRANSIT
    ↓
ARRIVED
    ↓
PORT RESOURCE CHECK
```
The vessel does not independently determine whether the port has capacity. It asks the port model.

### 4.8 Berth Waiting
If no berth is available:
```text
ARRIVED
    ↓
WAITING_FOR_BERTH
```
The port estimates the next available opportunity. Waiting time contributes to:

$$\text{ScheduleVariance} = \text{ActualTime} - \text{ScheduledTime}$$

### 4.9 Port Interaction
The vessel-port interaction is:
```text
Vessel reaches port
        ↓
Port evaluates berth
        ↓
Berth available?
     /       \
   Yes        No
   ↓           ↓
Berthing     Queue
   ↓           ↓
Operations   Wait
```
This avoids checking every vessel against every port continuously.

### 4.10 Voyage Generation
Recurring service/rotation:
```text
Service / Rotation
        ↓
Schedule
        ↓
Individual Voyages
        ↓
Vessel Assignment
```
The simulator may maintain approximately 90 days of future operational entities. However, CargoPilot must only receive information available according to the information/visibility model.

### 4.11 Vessel Parameters
**Examples:**
- `VESSEL_BASE_SPEED_KNOTS`
- `VESSEL_SPEED_VARIATION`
- `VESSEL_CAPACITY_TEU`
- `VESSEL_TURNAROUND_TIME_HOURS`
- `VESSEL_DELAY_PROBABILITY`
- `VESSEL_MEAN_TIME_BETWEEN_FAILURES`
- `VESSEL_RECOVERY_TIME_HOURS`
- `WEATHER_SPEED_FACTOR`
- `WEATHER_DELAY_PROBABILITY`

---

## 5. Port & Terminal Model

### 5.1 Port Structure
```text
Port
├── Berths
├── Cranes
├── Yard
├── Vessel Queue
├── Container Inventory
├── Handling Capacity
└── Congestion State
```

### 5.2 Berth Capacity
Let $B_{\text{available}}(t)$ be available berth capacity. A vessel can begin berth-dependent operations only when sufficient berth capacity exists.

### 5.3 Yard Capacity
Mandatory consistency constraint:

$$\text{YardOccupancy}(t) \le \text{YardCapacity}$$

If capacity cannot accommodate additional containers, the operation must be delayed or queued rather than creating an impossible state.

### 5.4 Resource Utilization
For a resource:

$$U(t) = \frac{\text{ResourceUsage}(t)}{\text{ResourceCapacity}(t)}$$

where $U$ may represent:
- Berth utilization
- Crane utilization
- Yard utilization

### 5.5 Congestion
V1 uses a moderate nonlinear congestion model.

Let:

$$U = \frac{\text{Usage}}{\text{Capacity}}$$

Define threshold $U_c$.

For $U \le U_c$:

$$F_{\text{congestion}} = 1$$

For $U > U_c$:

$$F_{\text{congestion}} = 1 + \alpha \times \left( \frac{U - U_c}{1 - U_c} \right)^\beta$$

where:
- $\alpha$: Congestion severity
- $\beta$: Nonlinearity

Handling time becomes:

$$T_{\text{handling}} = T_{\text{base}} \times F_{\text{congestion}}$$

This allows congestion to increase rapidly as the resource approaches full utilization without requiring detailed terminal physics.

### 5.6 Port Operation
General flow:
```text
Vessel Arrival
      ↓
Berth Check
      ↓
Berthing
      ↓
Cargo Discharge / Loading
      ↓
Yard Update
      ↓
Vessel Departure
```

### 5.7 Port Parameters
**Examples:**
- `PORT_BERTH_COUNT[port]`
- `PORT_CRANE_COUNT[port]`
- `PORT_YARD_CAPACITY[port]`
- `PORT_LOADING_RATE[port]`
- `PORT_DISCHARGE_RATE[port]`
- `PORT_BASE_HANDLING_TIME[port]`
- `PORT_CONGESTION_THRESHOLD[port]`
- `PORT_CONGESTION_FACTOR[port]`
- `PORT_CONGESTION_EXPONENT[port]`

---

## 6. Container & Equipment Model

### 6.1 Container Attributes
Each container contains:
- Container ID
- Equipment type
- Current location
- Status
- Condition
- Booking
- Allocation
- Movement state
- Availability timestamp

### 6.2 Container Lifecycle
Primary lifecycle:
```text
EMPTY_AVAILABLE
      ↓
ALLOCATED
      ↓
GATE_OUT
      ↓
STUFFING
      ↓
LOADED
      ↓
IN_TRANSIT
      ↓
DISCHARGED
      ↓
CUSTOMER
      ↓
EMPTY
      ↓
EMPTY_AVAILABLE
```

### 6.3 Equipment Types
V1:
- `20DC`
- `40DC`
- `40HC`

Additional equipment types may be introduced through configuration.

### 6.4 Container Condition
Possible states:
- `GOOD`
- `DAMAGED`
- `MAINTENANCE`
- `UNAVAILABLE`

A condition transition must have a modeled cause.

### 6.5 Damage and Maintenance
For an operational event:

$$\text{Damage} \sim \text{Bernoulli}(p_{\text{damage}})$$

If damage occurs:
```text
GOOD
 ↓
DAMAGED
 ↓
REPAIR / MAINTENANCE
 ↓
GOOD
```
or:
```text
DAMAGED
 ↓
UNAVAILABLE
```
depending on severity.

**Parameters:**
- `CONTAINER_DAMAGE_PROBABILITY`
- `CONTAINER_DAMAGE_SEVERITY`
- `CONTAINER_REPAIR_TIME`
- `CONTAINER_MAINTENANCE_PROBABILITY`
- `CONTAINER_MAINTENANCE_TIME`

---

## 7. Demand Model

### 7.1 Purpose
Demand represents cargo requirements generated over simulation time.

Flow:
```text
Historical Demand
      ↓
Demand Model
      ↓
Future Demand
      ↓
Booking Generation
```

### 7.2 Demand Dimensions
Demand may vary by:
- Origin
- Destination
- Equipment type
- Time
- Quantity
- Direction
- Customer/segment where modeled

### 7.3 Base Demand
Define $D_{i,j,e,t}$ as demand for:
- Origin $i$
- Destination $j$
- Equipment type $e$
- Period $t$

### 7.4 Demand Generation
V1 uses:

$$\lambda_{i,j,e,t} = D_{\text{base}} \times F_{\text{trend}} \times F_{\text{seasonal}} \times F_{\text{scenario}}$$

Then generated demand can be sampled as:

$$D_{i,j,e,t} \sim \text{Poisson}(\lambda_{i,j,e,t})$$

For smaller or highly controlled test worlds, a configured deterministic demand value may also be used.

### 7.5 Historical Demand
The initial world may contain historical demand.

As simulation progresses:
```text
Historical Data
      ↓
Observed New Demand
      ↓
Historical Dataset Updated
      ↓
Forecast Model
```
This allows future forecasts to use an evolving simulated history.

### 7.6 Parameters
- `DEMAND_BASE_RATE[OD][equipment]`
- `DEMAND_GROWTH_RATE`
- `DEMAND_SEASONAL_FACTOR`
- `DEMAND_VARIANCE`
- `DEMAND_SPIKE_PROBABILITY`
- `DEMAND_SPIKE_FACTOR`
- `DEMAND_GENERATION_INTERVAL`

---

## 8. Booking Generation Model

### 8.1 Purpose
The Simulation Engine creates bookings representing simulated customer demand.

### 8.2 Booking Generation
Conceptually:
```text
Demand
  ↓
Booking Generation
  ↓
BOOKING_CREATED
  ↓
Kafka
  ↓
CargoPilot
```

### 8.3 Booking Rate
Booking behavior is configurable by:

$$\text{BOOKING\_RATE}[origin][destination][equipment][time]$$

A demand quantity may be converted into bookings according to configured booking-size behavior.

### 8.4 Booking Attributes
- Booking ID
- Origin
- Destination
- Equipment Type
- Quantity
- Cargo Ready Time
- Departure/Voyage
- Booking Time
- Status
- Allocation
- Lock Status

### 8.5 Cancellation
For a booking:

$$\text{Cancel} \sim \text{Bernoulli}(p_{\text{cancel}})$$

Cancellation must respect the booking's current operational state.

**Parameters:**
- `BOOKING_CANCELLATION_PROBABILITY`
- `BOOKING_MODIFICATION_PROBABILITY`
- `BOOKING_LEAD_TIME`
- `BOOKING_SIZE_DISTRIBUTION`

---

## 9. Allocation & 7-Day Lock Model

### 9.1 Responsibility
CargoPilot owns container allocation.

The simulator:
- Observes allocation
- Persists its consequences
- Executes resulting operational behavior
- Does not optimize allocation

### 9.2 Allocation Flow
```text
Booking Created
      ↓
CargoPilot
      ↓
Container Allocation
      ↓
PostgreSQL
      ↓
Allocation Event
      ↓
Simulation Engine observes
```

### 9.3 Allocation States
- `CREATED`
- `ALLOCATED`
- `MODIFIABLE`
- `LOCKED`
- `COMPLETED`

### 9.4 Seven-Day Lock
For vessel departure:

$$T_{\text{cutoff}} = T_{\text{departure}} - 7\text{ days}$$

Before cutoff:

$$T < T_{\text{cutoff}}$$

allocation may be modified.

At or after cutoff:

$$T \ge T_{\text{cutoff}}$$

the allocation is locked. Therefore equality belongs to the locked state.

### 9.5 Locked Allocation
Once locked:

$$\text{Allocation}_{t+1} = \text{Allocation}_t$$

under normal CargoPilot allocation operations. The simulator does not generate artificial allocation issues after locking.

---

## 10. Import Return & Equipment Availability Model

### 10.1 Purpose
This model handles the return of equipment after import cargo is delivered.

Flow:
```text
Loaded Import
      ↓
Vessel Arrival
      ↓
Discharge
      ↓
Customer
      ↓
Customer Use
      ↓
Empty Return
      ↓
Available Equipment
```

### 10.2 Return Time

$$T_{\text{return}} = T_{\text{delivery}} + T_{\text{customer\_use}}$$

Customer-use duration is stochastic/configurable. A suitable V1 distribution is a bounded distribution or empirical distribution.

### 10.3 Equipment Availability
When the customer returns the empty container:
```text
CUSTOMER
   ↓
EMPTY
   ↓
EMPTY_AVAILABLE
```
The equipment inventory at the return location increases.

### 10.4 Parameters
- `IMPORT_RETURN_MEAN_DAYS[equipment]`
- `IMPORT_RETURN_VARIANCE`
- `IMPORT_RETURN_MIN_DAYS`
- `IMPORT_RETURN_MAX_DAYS`
- `IMPORT_RETURN_DELAY_PROBABILITY`
- `IMPORT_RETURN_DELAY_DAYS`

---

## 11. Equipment Supply & Scarcity Model

### 11.1 Purpose
This model determines whether sufficient equipment exists at a location for operational demand.

### 11.2 Available Equipment
For location $l$ and equipment $e$:

$$\text{Available}_{l,e}(t)$$

represents usable equipment available at that location and time.

### 11.3 Requirement
For expected requirement:

$$\text{Required}_{l,e}(t)$$

### 11.4 Shortage

$$\text{Shortage}_{l,e}(t) = \max\bigl(0,\, \text{Required}_{l,e}(t) - \text{Available}_{l,e}(t)\bigr)$$

### 11.5 Surplus

$$\text{Surplus}_{l,e}(t) = \max\bigl(0,\, \text{Available}_{l,e}(t) - \text{Target}_{l,e}(t)\bigr)$$

### 11.6 Deficit

$$\text{Deficit}_{l,e}(t) = \max\bigl(0,\, \text{Target}_{l,e}(t) - \text{Available}_{l,e}(t)\bigr)$$

### 11.7 Scarcity Effects
Equipment shortage can cause:
```text
Shortage
   ↓
Booking fulfillment pressure
   ↓
CargoPilot decision
   ├── Reposition
   └── Lease
```
The simulator does not automatically optimize these decisions.

### 11.8 Parameters
- `EQUIPMENT_TARGET[location][equipment]`
- `EQUIPMENT_MINIMUM_STOCK[location][equipment]`
- `EQUIPMENT_SHORTAGE_THRESHOLD`
- `EQUIPMENT_AVAILABILITY_FACTOR`

---

## 12. Leasing Model

### 12.1 Responsibility
CargoPilot decides whether leasing is economically appropriate. The simulator represents the operational consequence of the lease decision. It does not automatically lease equipment merely because shortage exists.

### 12.2 Lease Requirement
Conceptually:

$$\text{LeaseRequirement} = \max(0,\, \text{RequiredEquipment} - \text{AvailableEquipment})$$

This is an input/indicator for CargoPilot rather than an automatic simulator decision.

### 12.3 Lease Execution
When CargoPilot decides to lease:
```text
CargoPilot Lease Decision
       ↓
Lease Order
       ↓
Lease Start Delay
       ↓
Equipment Added
       ↓
Available Equipment
```

### 12.4 Lease Cost
For quantity $Q$:

$$\text{LeaseCost} = Q \times \text{Rate} \times \text{Duration}$$

### 12.5 Parameters
- `LEASE_COST_PER_DAY`
- `LEASE_MIN_DURATION`
- `LEASE_MAX_DURATION`
- `LEASE_AVAILABLE_CAPACITY`
- `LEASE_START_DELAY`
- `LEASE_COST_VARIATION`

---

## 13. Repositioning Model

### 13.1 Purpose
Represents movement of empty containers between locations.
```text
Surplus Location
      ↓
Empty Repositioning
      ↓
Deficit Location
```

### 13.2 Decision Ownership
CargoPilot decides:
- Whether to reposition
- Source
- Destination
- Equipment type
- Quantity
- Timing

The simulator executes the movement.

### 13.3 Repositioning Execution
```text
CargoPilot Decision
      ↓
Source Inventory Decrease
      ↓
Repositioning In Transit
      ↓
Transit Time
      ↓
Destination Inventory Increase
```

### 13.4 Parameters
- `REPOSITIONING_TRANSIT_TIME`
- `REPOSITIONING_HANDLING_TIME`
- `REPOSITIONING_COST`
- `REPOSITIONING_CAPACITY`

---

## 14. Disruption Models

### 14.1 Purpose
Disruptions disturb normal operations.

V1 includes:
- Weather/storm
- Port congestion
- Port strike
- Vessel mechanical failure
- Equipment shortage
- Demand shock

### 14.2 Disruption Structure
```text
Disruption
├── ID
├── Type
├── Start Time
├── End Time
├── Duration
├── Severity
├── Affected Entities
├── Behavior
└── Random Outcome
```

### 14.3 Active Period vs Consequences
A disruption can end while its consequences remain.

**Example:**
```text
Storm
 ↓
Speed reduction
 ↓
Vessel delay
 ↓
Late arrival
 ↓
Port workload shift
 ↓
Container delay
```
When the storm ends, the storm is inactive, but the vessel may remain delayed.

### 14.4 Storm Model
For severity $s$, define:

$$F_{\text{weather}} = 1 - \alpha_s \times s$$

bounded to the configured minimum.

The effective speed becomes:

$$V_{\text{eff}} = V_{\text{base}} \times F_{\text{weather}} \times F_{\text{operational}}$$

Storm may additionally generate a delay event.

### 14.5 Parameters
- `STORM_OCCURRENCE_PROBABILITY`
- `STORM_DURATION_HOURS`
- `STORM_SEVERITY`
- `STORM_SPEED_FACTOR`
- `STORM_DELAY_FACTOR`
- `PORT_STRIKE_PROBABILITY`
- `PORT_STRIKE_DURATION`
- `PORT_STRIKE_CAPACITY_FACTOR`

---

## 15. Causal & Cascading Effects

### 15.1 Core Principle
The simulator prioritizes causal relationships over independent random changes.

### 15.2 Storm Chain
```text
Storm
  ↓
Weather Impact
  ↓
Vessel Delay
  ↓
Late Arrival
  ↓
Port Workload Change
  ↓
Discharge Delay
  ↓
Container Availability Decrease
  ↓
Equipment Shortage
  ↓
CargoPilot Replanning
```

### 15.3 Demand Chain
```text
Demand Increase
      ↓
More Bookings
      ↓
More Equipment Required
      ↓
Equipment Shortage
      ↓
CargoPilot Decision
      ↓
Repositioning / Leasing
      ↓
World State Change
```

### 15.4 Dependency Rule
A downstream model must consume the current result of its upstream dependency.

For example, if vessel ETA changes:
```text
Old ETA
   ↓
discard/recalculate dependent events
   ↓
New ETA
   ↓
new arrival event
```
The simulator must not continue using stale timing.

---

## 16. Forecasting Model

### 16.1 Purpose
Forecasting produces future estimates that CargoPilot can use for planning.

V1 forecast targets should focus on information that is operationally useful to CargoPilot:
- Demand
- Equipment requirement
- Equipment availability
- Equipment shortage
- Vessel arrival/ETA
- Port congestion where required

### 16.2 Forecast vs Actual
**Forecast:**

$$\text{Forecast}(t, t+k)$$

represents what is predicted at time $t$ for future time $t+k$.

**Actual:**

$$\text{Actual}(t+k)$$

represents the actual future state.

These must remain separate.

### 16.3 Forecast Generation
A basic demand forecast can use recent historical demand:

$$\hat{D}_{t+k} = \text{BaseForecast}_t + \text{Trend} + \text{Seasonality} + \text{ForecastError}$$

where forecast error is sampled from the configured error distribution.

### 16.4 Information Leakage
CargoPilot must not receive future actual information merely because the simulator internally knows it.

For example:
```text
Simulator knows:
Vessel will arrive Day 10 14:00

CargoPilot may know:
ETA Day 10 14:00

only if that information has been published
according to the visibility model.
```

### 16.5 Parameters
- `FORECAST_HORIZON`
- `FORECAST_UPDATE_INTERVAL`
- `FORECAST_NOISE`
- `FORECAST_ERROR_DISTRIBUTION`
- `FORECAST_HISTORY_WINDOW`

---

## 17. Information / Visibility Model

### 17.1 Purpose
The simulator distinguishes:
```text
REAL WORLD STATE
      ↓
WHAT HAS HAPPENED
      ↓
WHAT IS OBSERVABLE
      ↓
WHAT CARGOPILOT KNOWS
```

### 17.2 Three Timestamps
An operational fact can have:
- Occurrence Time
- Observation Time
- Ingestion Time

**Example:**
```text
Vessel delay occurs       10:00
Carrier observes          10:30
CargoPilot ingests        10:35
```

### 17.3 Event Information Delay

$$T_{\text{observation}} = T_{\text{occurrence}} + D_{\text{information}}$$

and:

$$T_{\text{ingestion}} = T_{\text{observation}} + D_{\text{ingestion}}$$

### 17.4 Parameters
- `EVENT_INFORMATION_DELAY`
- `EVENT_INGESTION_DELAY`
- `FORECAST_UPDATE_DELAY`
- `VESSEL_POSITION_UPDATE_INTERVAL`
- `PORT_STATUS_UPDATE_INTERVAL`

---

## 18. Operational Timeline Model

### 18.1 Purpose
The simulator must represent the operational lifecycle established for CargoPilot.

### 18.2 Booking-to-Vessel Timeline
```text
Booking Opens
      ↓
Booking Submitted
      ↓
Booking Confirmed
      ↓
Booking Cutoff
      ↓
Cargo Ready
      ↓
CargoPilot Planning Window
      ↓
Container Assignment Deadline
      ↓
Freeze / Commitment
      ↓
Empty Release
      ↓
Empty Pickup
      ↓
Stuffing / Loading
      ↓
Full Container Movement
      ↓
CY / Gate-in Cutoff
      ↓
SI Cutoff
      ↓
VGM Cutoff
      ↓
Load-list Closure
      ↓
Vessel Loading
      ↓
Vessel Departure
      ↓
Actual Event Feedback
```

### 18.3 Timeline Representation
Every milestone contains:
- Timestamp
- Dependency
- State transition
- Lead time/offset
- Configurable parameter

### 18.4 Example
For empty release:

$$T_{\text{emptyRelease}} = T_{\text{departure}} - X_{\text{release}}$$

where `EMPTY_RELEASE_LEAD_TIME` is configurable.

### 18.5 Timeline Rule
Timeline events must be derived from operational dependencies rather than independently generated.

For example:
```text
Vessel Departure
      ↓
Empty Release
      ↓
Empty Pickup
```
If vessel departure changes, dependent milestones must be recalculated where they have not already occurred or become locked.

---

## 19. Failure & Exception Models

### 19.1 Purpose
Failures represent abnormal operational outcomes.

**Examples:**
- Vessel mechanical failure
- Container damage
- Berth unavailable
- Port capacity exceeded
- Equipment unavailable
- Booking cancellation
- Delayed cargo
- Failed movement

### 19.2 Failure Principle
A failure must cause a state transition and, where appropriate, downstream consequences.

**Example:**
```text
Mechanical Failure
      ↓
Vessel Unavailable
      ↓
Voyage Delay
      ↓
Arrival Delay
      ↓
Container Delay
```

### 19.3 Failure Probability
For an event:

$$\text{Failure} \sim \text{Bernoulli}(p)$$

or, where appropriate, use a time-to-failure distribution.

### 19.4 Parameters
- `FAILURE_PROBABILITY`
- `FAILURE_FREQUENCY`
- `FAILURE_SEVERITY`
- `FAILURE_DELAY`
- `FAILURE_RECOVERY_TIME`

Model-specific parameters override these generic concepts where required.

---

## 20. Recovery Models

### 20.1 Purpose
Recovery represents operational recovery after a disruption or failure. It does not refer to simulator software recovery.

### 20.2 Recovery Flow
**Example:**
```text
Failure
  ↓
Entity Unavailable
  ↓
Recovery Process
  ↓
Repair / Reallocation / Resource Release
  ↓
Entity Available
```

### 20.3 Recovery Time
For a recovery process:

$$T_{\text{recovery}} = T_{\text{failure}} + \text{Duration}_{\text{recovery}}$$

Recovery duration may be deterministic or stochastic.

### 20.4 Parameters
- `RECOVERY_TIME`
- `RECOVERY_TIME_MEAN`
- `RECOVERY_TIME_VARIANCE`
- `RECOVERY_SUCCESS_PROBABILITY`
- `RECOVERY_CAPACITY`

---

## 21. Backlog Model

### 21.1 Purpose
Backlog represents operational work that should have been completed but remains outstanding.

**Examples:**
- Containers waiting for discharge
- Containers waiting for pickup
- Bookings awaiting equipment
- Vessels waiting for berth
- Unsatisfied equipment demand

### 21.2 Backlog Balance

$$\text{Backlog}_{t+1} = \text{Backlog}_t + \text{Arrivals} - \text{Completed}$$

with:

$$\text{Backlog}_t \ge 0$$

### 21.3 Processing Capacity
If:

$$\text{Arrivals} > \text{ProcessingCapacity}$$

then backlog increases.

Processing capacity can depend on:
- Cranes
- Berth availability
- Yard availability
- Equipment
- Congestion

### 21.4 Backlog Effects
Backlog can affect:
```text
Backlog
 ↓
Congestion
 ↓
Longer Handling
 ↓
Vessel Delay
```
and:
```text
Backlog
 ↓
Delayed Container Availability
 ↓
Equipment Shortage
 ↓
CargoPilot Replanning
```

### 21.5 Parameters
- `BACKLOG_CAPACITY`
- `BACKLOG_PROCESSING_RATE`
- `BACKLOG_DELAY_FACTOR`
- `BACKLOG_CONGESTION_FACTOR`

---

## 22. Cost Models

### 22.1 Purpose
Cost models represent operational/economic consequences for simulation and optimization testing.

V1 may represent:
- Vessel delay
- Port handling
- Container handling
- Repositioning
- Leasing
- Equipment shortage
- Storage
- Demurrage/detention where included
- Disruption
- Recovery

### 22.2 Total Cost

$$\text{TotalCost} = \sum \text{Cost}_i$$

### 22.3 Delay Cost

$$\text{DelayCost} = \text{DelayDuration} \times \text{CostPerHour}$$

### 22.4 Lease Cost

$$\text{LeaseCost} = \text{Quantity} \times \text{Rate} \times \text{Duration}$$

### 22.5 Repositioning Cost

$$\text{RepositioningCost} = \text{Quantity} \times \text{CostPerContainer}$$

### 22.6 Storage Cost

$$\text{StorageCost} = \text{ContainerCount} \times \text{Days} \times \text{CostPerDay}$$

### 22.7 Parameters
- `VESSEL_DELAY_COST_PER_HOUR`
- `PORT_HANDLING_COST`
- `CONTAINER_HANDLING_COST`
- `REPOSITIONING_COST_PER_CONTAINER`
- `LEASE_COST_PER_DAY`
- `STORAGE_COST_PER_DAY`
- `SHORTAGE_COST_PER_CONTAINER`
- `DISRUPTION_COST`
- `RECOVERY_COST`

Cost definitions must remain compatible with the CargoPilot optimization objective.

---

## 23. Scenario Models

### 23.1 Purpose
Scenarios allow controlled and repeatable experiments.

**V1 scenarios:**
- `NORMAL`
- `PORT_CONGESTION`
- `VESSEL_DELAY`
- `STORM`
- `EQUIPMENT_SHORTAGE`
- `DEMAND_SPIKE`
- `MULTIPLE_DISRUPTIONS`

### 23.2 Scenario Definition
```text
Scenario
├── ID
├── Start Time
├── Duration
├── Affected Entities
├── Severity
├── Behavior
├── Configuration
└── Random Seed
```

### 23.3 Scenario Principle
A scenario modifies normal model behavior. It does not replace the normal simulation engine.

**Example:**
```text
NORMAL MODEL
      +
STORM PARAMETERS
      ↓
STORM SCENARIO
```

---

## 24. Parameters & Configuration

### 24.1 Central Parameter Registry
Every model registers configurable parameters.

**Required fields:**

| Field | Meaning |
| :--- | :--- |
| **Parameter Name** | Unique identifier |
| **Model** | Owning model |
| **Description** | Meaning |
| **Value** | Current value |
| **Default** | Default value |
| **Unit** | Unit |
| **Min** | Minimum |
| **Max** | Maximum |
| **Type** | Number / Boolean / Enum / etc. |
| **Distribution** | If stochastic |
| **Scope** | Global / Port / Route / etc. |
| **Admin Editable** | Whether admin can modify |
| **Runtime Editable** | Whether value may change during simulation |
| **Scenario Override** | Whether scenario can override |

### 24.2 Parameter Scope
Supported scopes include:
- `GLOBAL`
- `WORLD`
- `SCENARIO`
- `PORT`
- `ROUTE`
- `OD_PAIR`
- `VESSEL_CLASS`
- `EQUIPMENT_TYPE`
- `PORT + EQUIPMENT`
- `ROUTE + EQUIPMENT`

The most specific applicable parameter overrides broader scope.

**Example:**
```text
Global:
PORT_LOADING_RATE = 100

Port Chennai:
PORT_LOADING_RATE[INMAA] = 70
Chennai uses 70.
```

### 24.3 Runtime Parameter Changes
If an admin changes a runtime-editable parameter:
```text
Admin Change
     ↓
Validation
     ↓
PostgreSQL
     ↓
Simulation Engine observes
     ↓
Affected future events/models recalculated
```
Already completed historical events are not rewritten. Only affected future behavior is changed.

---

## 25. Shared State, PostgreSQL & Kafka Integration

### 25.1 Database Architecture
The Simulation Engine and CargoPilot use a shared PostgreSQL database. PostgreSQL stores the current operational truth.

Conceptually:
```text
                PostgreSQL
          ┌─────────────────────┐
          │                     │
          │ Operational State   │
          │ Simulation State    │
          │ CargoPilot State    │
          │ Allocations         │
          │ Events / History    │
          │ Parameters          │
          │                     │
          └─────────┬───────────┘
                    │
          ┌─────────┴──────────┐
          │                    │
    Simulation Engine      CargoPilot
```
The two services must have clear ownership of individual entities/operations.

### 25.2 Kafka Responsibility
Kafka transports changes and notifications. It does not become the authoritative current-state database.

- **PostgreSQL** = What is the current state?
- **Kafka**      = What changed?

### 25.3 Simulation $\rightarrow$ CargoPilot
**Example:**
```text
Simulation
   ↓
State Change
   ↓
PostgreSQL
   ↓
Kafka Event
   ↓
CargoPilot Ingestion
   ↓
CargoPilot DB / State
   ↓
Optimization
```

### 25.4 CargoPilot $\rightarrow$ Simulation
**Example:**
```text
CargoPilot Decision
   ↓
PostgreSQL
   ↓
Kafka Event
   ↓
Simulation Engine
   ↓
Operational Consequence
```
Examples include:
- Container allocation
- Repositioning decision
- Lease decision
- Planning decision

### 25.5 Event Structure
Every event should contain:
- `event_id`
- `event_type`
- `entity_type`
- `entity_id`
- `simulation_time`
- `occurrence_time`
- `source`
- `world_id`
- `payload`
- `caused_by_event_id`

`caused_by_event_id` allows causal chains to be traced.

---

## 26. Calibration & Realism

### 26.1 Purpose
Calibration means adjusting simulation parameters so that simulated behavior falls within realistic operational ranges. It does not require machine learning.

### 26.2 Calibration Sources
Possible sources:
- Historical operational data
- Public maritime/logistics data
- Company data
- Empirical observations
- Domain assumptions

Synthetic assumptions must be explicitly identified.

### 26.3 Calibration Targets
**Examples:**
- Average vessel speed
- Port turnaround time
- Berth waiting time
- Demand distribution
- Container return time
- Equipment imbalance
- Leasing cost
- Disruption frequency
- Delay distribution

### 26.4 Calibration Process
```text
Initial Parameters
       ↓
Run Simulation
       ↓
Measure Outputs
       ↓
Compare with Target Range
       ↓
Adjust Parameters
       ↓
Run Again
```
The objective is sufficient realism for testing CargoPilot decisions, not perfect reproduction of the physical world.

---

## 27. Validation

### 27.1 Purpose
Validation prevents impossible operational states.

### 27.2 Entity Consistency
An entity must not simultaneously exist in incompatible states.

**Example:**
```text
A container cannot simultaneously be:
AVAILABLE_AT_SHANGHAI
and:
IN_TRANSIT_TO_DUBAI
```

### 27.3 Capacity Constraints
Mandatory:

$$\text{YardOccupancy} \le \text{YardCapacity}$$

and:

$$\text{VesselLoad} \le \text{VesselCapacity}$$

### 27.4 Allocation Validation
Every allocation must reference:
- Valid booking
- Valid container
- Valid equipment type
- Valid voyage

Locked allocations cannot be modified through normal allocation operations.

### 27.5 Equipment Conservation
Conceptually:

$$\text{TotalEquipment} = \text{Available} + \text{Allocated} + \text{InTransit} + \text{Unavailable} + \text{OtherValidStates}$$

Equipment cannot appear or disappear without a modeled event.

### 27.6 Event Validation
Every event must identify:
- What happened
- Affected entity
- Simulation timestamp
- Source
- World
- Event ID

### 27.7 Validation Timing
Two levels of validation are used.

**Local validation** (after a state-changing event):
```text
Event
 ↓
State Update
 ↓
Validate affected entities/resources
```

**Advancement validation** (after completing the requested time advancement):
```text
Advance
 ↓
Process Events
 ↓
Full World Validation
 ↓
Persist Final State
```

---

## 28. Mathematical Formula Registry

The central formula registry contains the formulas used throughout the simulator.

| Concept | Formulation |
| :--- | :--- |
| **Simulation Time** | $T_{\text{target}} = T_{\text{current}} + \Delta t$, where $0 < \Delta t \le 24\text{h}$ |
| **State Transition** | $S(t^+) = F(S(t^-), E, \theta, \omega)$ |
| **Travel Time** | $T_{\text{travel}} = \frac{D}{V_{\text{eff}}}$ |
| **Effective Speed** | $V_{\text{eff}} = V_{\text{base}} \times F_{\text{weather}} \times F_{\text{operational}}$ |
| **Remaining Travel Time** | $T_{\text{remaining}} = \frac{D_{\text{remaining}}}{V_{\text{eff}}}$ |
| **Port Utilization** | $U = \frac{\text{ResourceUsage}}{\text{ResourceCapacity}}$ |
| **Congestion Factor** | $F_{\text{congestion}} = 1$ for $U \le U_c$; $F_{\text{congestion}} = 1 + \alpha \times \left(\frac{U - U_c}{1 - U_c}\right)^\beta$ for $U > U_c$ |
| **Handling Time** | $T_{\text{handling}} = T_{\text{base}} \times F_{\text{congestion}}$ |
| **Equipment Shortage** | $\text{Shortage} = \max(0,\, \text{Required} - \text{Available})$ |
| **Surplus** | $\text{Surplus} = \max(0,\, \text{Available} - \text{Target})$ |
| **Deficit** | $\text{Deficit} = \max(0,\, \text{Target} - \text{Available})$ |
| **Lease Requirement** | $\text{LeaseRequirement} = \max(0,\, \text{Required} - \text{Available})$ |
| **Lease Cost** | $\text{LeaseCost} = \text{Quantity} \times \text{Rate} \times \text{Duration}$ |
| **Repositioning Cost** | $\text{RepositioningCost} = \text{Quantity} \times \text{CostPerContainer}$ |
| **Storage Cost** | $\text{StorageCost} = \text{ContainerCount} \times \text{Days} \times \text{CostPerDay}$ |
| **Delay Cost** | $\text{DelayCost} = \text{DelayDuration} \times \text{CostPerHour}$ |
| **Import Return** | $T_{\text{return}} = T_{\text{delivery}} + T_{\text{customer\_use}}$ |
| **Backlog Balance** | $\text{Backlog}_{t+1} = \text{Backlog}_t + \text{Arrivals} - \text{Completed}$ |
| **Allocation Lock** | $T_{\text{cutoff}} = T_{\text{departure}} - 7\text{ days}$ |
| **Locked Allocation** | $\text{Allocation}_{t+1} = \text{Allocation}_t$ |
| **Demand Generation** | $\lambda_{i,j,e,t} = D_{\text{base}} \times F_{\text{trend}} \times F_{\text{seasonal}} \times F_{\text{scenario}}$; $D_{i,j,e,t} \sim \text{Poisson}(\lambda_{i,j,e,t})$ |
| **Information Time** | $T_{\text{observation}} = T_{\text{occurrence}} + D_{\text{information}}$; $T_{\text{ingestion}} = T_{\text{observation}} + D_{\text{ingestion}}$ |

---

## 29. Model Dependency Map

The simulation uses dependencies rather than blindly executing every model.

### 29.1 Demand Chain
```text
Demand
   ↓
Booking
   ↓
CargoPilot
   ↓
Allocation
   ↓
Container State
   ↓
Equipment Availability
   ↓
Shortage / Surplus
   ↓
CargoPilot Decision
   ├──────────────┐
   ↓              ↓
Repositioning   Leasing
   ↓              ↓
World State ←─────┘
```

### 29.2 Vessel/Port Chain
```text
Weather / Disruption
        ↓
Vessel Movement
        ↓
Voyage ETA
        ↓
Port Arrival
        ↓
Berth Availability
       / \
     Yes  No
      ↓    ↓
Berthing Queue / Waiting
      ↓
Port Operations
      ↓
Container Movement
      ↓
Equipment Availability
```

### 29.3 Import Equipment Chain
```text
Import Voyage
     ↓
Discharge
     ↓
Customer
     ↓
Customer Use
     ↓
Empty Return
     ↓
Equipment Available
     ↓
Local Equipment Pool
```

### 29.4 Disruption Chain
```text
Disruption
     ↓
Affected Model
     ↓
State Change
     ↓
Generated Event
     ↓
Downstream Model
     ↓
Further State Changes
```

### 29.5 Execution Principle
For an advancement:
```text
Load Current State
        ↓
Identify Relevant Events
        ↓
Execute Chronological Event
        ↓
Update State
        ↓
Generate Consequences
        ↓
Schedule Dependent Events
        ↓
Process Next Event
        ↓
Continue Until Target Time
        ↓
Validate
        ↓
Persist
        ↓
Publish Required Events
```

The engine must not:
- Run every model
- every simulated hour

---

## 30. V1 vs Future Models

### 30.1 V1 Scope
V1 includes:
- Ports
- Terminals
- Vessels
- Voyages
- Containers
- Equipment
- Demand
- Bookings
- CargoPilot allocation
- Seven-day allocation lock
- Import returns
- Equipment availability
- Equipment scarcity
- Leasing
- Repositioning
- Disruptions
- Delays
- Failures
- Recovery
- Backlog
- Forecasting
- Information visibility
- Operational timelines
- Costs
- Scenarios
- Configurable parameters
- Admin interventions
- PostgreSQL state persistence
- Kafka event propagation
- Deterministic simulation
- SimPy event-driven execution

### 30.2 Explicitly Out of Scope
V1 does not include:
- Detailed ship hydrodynamics
- Engine thermodynamics
- Individual engine component simulation
- Detailed ocean physics
- Exact weather forecasting
- Detailed crane mechanics
- Detailed worker behavior
- Full terminal digital twin
- Detailed human/customer behavioral simulation

### 30.3 Future Extensions
Possible future extensions:
- Advanced terminal simulation
- Advanced weather systems
- Detailed vessel physics
- Detailed crane/resource modeling
- Richer customer behavior
- Advanced market models
- Street-turn / triangulation
- Sophisticated forecasting
- Real-world API integration
- Historical calibration
- Larger optimization horizons
- More detailed physical simulation

---

## Final Modeling Principle

The CargoPilot Simulation Engine follows:

$$\boxed{ \text{Current State} + \text{Events} + \text{Configuration} + \text{Random Outcomes} \longrightarrow \text{State Changes} + \text{New Events} }$$

The responsibilities are:

```text
┌─────────────────────────────────────────────┐
│ Simulation Engine                           │
│ Creates and evolves the operational world   │
└─────────────────────────────────────────────┘
                      │
                      ▼
              ┌──────────────┐
              │    SimPy     │
              │ Time + Events│
              └──────────────┘

              PostgreSQL
        Current Operational Truth
                  ↕
               Kafka
          Event Propagation
                  ↕
              CargoPilot
       Planning + Optimization

                 Admin
                   ↓
             Configuration
                   ↓
              Simulation
```

The simulator must preserve:
- Causality
- State continuity
- Reproducibility
- Configurability
- World consistency
- Operational realism
- Information visibility
- Separation of simulation behavior and CargoPilot decisions

The shared PostgreSQL database represents current operational truth, Kafka represents what changed, SimPy provides simulation execution and virtual time, the Simulation Engine creates and evolves operational reality, and CargoPilot makes planning and optimization decisions.

This document is now suitable as the implementation baseline for `services/simulation/`. The companion [Doc 1](file:///Users/adityasahrawat/dev/projects/cargoPilot/doc/CargoPilot-Simulation-Engine%E2%80%94Design-Specification.md) establishes the overall system architecture, component responsibilities, and event flow.
