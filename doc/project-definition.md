
# Project Definition — CargoPilot

## Project name

CargoPilot (working title)

### Alternative names

- HarborIQ
- PortFlow Planner
- ContainerOps
- EquipFlow
- Container Decision Hub
- EmptyOps
- FleetIQ Containers

My favorite is CargoPilot because it sounds like software that assists human operators rather than attempting to automate an entire shipping company.

## One-line pitch

An event-driven decision support platform that helps container equipment planners anticipate equipment shortages and evaluate the most cost‑effective operational response using real‑time logistics events, forecasting, and optimization.

## The problem

Global container shipping suffers from severe equipment imbalance: some ports accumulate thousands of idle containers while others face shortages. Planners often rely on spreadsheets, disconnected systems, and manual experience to make decisions such as:

- Should containers be repositioned?
- Should new containers be leased?
- Should demand be deferred?
- Which regions need immediate attention?

These decisions directly affect operational cost, customer service, and asset utilization. This project focuses on improving a single operational workflow through data engineering and decision support rather than replacing enterprise logistics platforms.

## Target user

**Primary user:** Equipment Planner (Container Equipment Control)

Responsible for ensuring the right container types and quantities are available at the right ports.

### User's daily workflow

Each morning the planner wants concise answers to:

- Which ports are expected to face shortages?
- Which ports have excess idle containers?
- Which recommendations require my approval?
- What is the cheapest response?
- What risks should I know before making decisions today?

The product is designed to answer these questions with actionable recommendations.

## Product goal

Provide planners with actionable, ranked recommendations (not raw operational data). The system continuously evaluates logistics events and proposes operational actions with cost and impact estimates.

## Core recommendation

Given current inventory, historical demand, forecasts, vessel schedules, and operational constraints, produce the lowest‑cost feasible plan over the planning horizon. Candidate actions include:

- Reposition containers
- Lease containers locally
- Delay repositioning
- Accept a temporary shortage
- Prioritize high‑value demand

## Out of scope

The product is explicitly not:

- A container tracking application
- A general logistics dashboard or TMS
- A digital twin of global trade
- Software intended to replace major carriers or logistics providers

It is a focused decision‑support tool for the equipment planning role.

## Core product workflow

1. Ingest streaming logistics events
2. Validate and reconcile events
3. Reconstruct current container state
4. Forecast short‑term demand by location
5. Run optimization to generate candidate plans
6. Present ranked recommendations in the Decision Workbench
7. Planner reviews and approves actions

## Key inputs

- Container events: loaded, discharged, returned, repaired, damaged, released
- Operational data: port & depot inventory, vessel schedules, historical movements, booking demand, repair backlog
- External data: weather, public schedules, trade imbalance datasets, port metadata

## Core outputs

The system should answer:

- Which ports require attention today?
- Which shortages are expected and why?
- What response options are available?
- Estimated cost and impact for each option
- A ranked recommended action for planner approval

## Product modules

1. Event Processing — ingest and reconcile logistics events (handle delays, duplicates, out‑of‑order data)
2. State Engine — maintain and reconstruct the current operational state of every container
3. Forecasting — estimate short‑term demand per port using historical patterns
4. Optimization Engine — generate feasible, cost‑aware operational plans (primary algorithmic component)
5. Decision Workbench — present ranked recommendations and support planner approvals

## Success metrics

Measure business outcomes (primarily via simulation) rather than only technical metrics:

- Predicted shortages identified (recall / precision)
- Idle container reduction (simulation)
- Planning cost reduction (simulation)
- Planner decision time
- Recommendation acceptance rate (simulation)

## Technical objectives

The project should demonstrate:

- Event‑driven architecture and streaming ingestion
- Event sourcing and state reconstruction
- Data warehousing and observability
- Forecasting and operations research / optimization
- Backend API design and geospatial visualization

## Resume blurb

Designed and built an event‑driven decision support platform for container equipment planning. The system ingests logistics events, reconstructs asset state, forecasts regional equipment demand, and generates cost‑aware operational recommendations through optimization, demonstrating large‑scale data engineering, warehousing, and event‑processing concepts.

---

For implementation details, design notes, and diagrams, see the project documentation in the repository.

