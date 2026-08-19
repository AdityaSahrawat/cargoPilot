# CargoPilot

An event-driven decision support platform for container equipment planning, state reconstruction, demand forecasting, and cost-aware optimization.

---

## ⚓ Overview

Global container shipping suffers from severe equipment imbalance: certain ports accumulate thousands of idle containers while others face acute shortages. Equipment planners historically rely on spreadsheets and disconnected enterprise systems to answer critical questions:
- *Should empty containers be repositioned to deficit ports?*
- *Should containers be leased locally to meet surge demand?*
- *Which demand should be prioritized vs deferred?*
- *What is the most cost-effective operational plan over a multi-week horizon?*

**CargoPilot** bridges this gap by continuously ingesting logistics events, reconstructing container state, forecasting short-term regional demand, running mathematical optimization models, and delivering ranked recommendations to equipment planners.

---

## 🎯 Core Features & Business Workflow

1. **Logistics Event Ingestion & State Reconstruction**:
   - Ingests real-time operational events (`GATE_IN`, `GATE_OUT`, `LOADED`, `DISCHARGED`, `RETURNED`, `REPAIRED`, `RELEASED`, `DAMAGED`).
   - Automatically reconciles state transitions and updates container availability, status, and physical location.

2. **Demand Forecasting**:
   - Combines confirmed booking demand with probabilistic short-term demand projections per port, week, and container type with confidence scoring.

3. **Optimization Engine**:
   - Generates cost-optimal operational plans over a multi-week horizon.
   - Evaluates joint decision variables: container repositioning over voyage legs, local leasing agreements, target inventory levels, and demand fulfillment/backlog.

4. **Decision Workbench & Dashboard APIs**:
   - Provides equipment planners with high-level KPI overviews, shortage risk alerts, surplus/deficit location tracking, and actionable recommendation approval workflows.

---

## 🏗️ System Architecture

CargoPilot uses a decoupled, service-oriented architecture:

```text
Logistics Events / Bookings / Vessel Schedules
                    │
                    ▼
          FastAPI Controllers (/api/v1)
                    │
                    ▼
           OptimizationService
                    │
                    ▼
        OptimizationInputBuilder ───► Database Facts (DB Schema V1)
                    │
                    ▼
              Solver Engine
                    │
                    ▼
        OptimizationResult (Repositioning, Leasing, Inventory, Demand)
```

---

## 📂 Project Structure

```text
cargoPilot/
├── README.md                      # Primary project documentation
├── docker-compose.yml             # Local infrastructure orchestration
│
├── apps/                          # Frontend Applications
│   ├── admin/                     # Admin control interface
│   └── web/                       # Main Equipment Planner Workbench Web App
│
├── services/                      # Backend Microservices & APIs
│   └── api/                       # Core CargoPilot FastAPI Service
│       ├── main.py                # FastAPI app entry point & router mounting
│       ├── pyproject.toml         # Python project configuration & dependencies
│       │
│       ├── app/
│       │   ├── api/               # API Controllers (Group 1 - Group 9)
│       │   │   ├── health.py      # Health check endpoints
│       │   │   └── v1/            # API V1 Endpoints
│       │   │       ├── router.py         # Main V1 router
│       │   │       ├── company.py        # Group 1: Company & Locations
│       │   │       ├── containers.py     # Group 2: Containers & Inventory
│       │   │       ├── vessels.py        # Group 3: Vessels, Services & Voyages
│       │   │       ├── bookings.py       # Group 4: Bookings & Assignments
│       │   │       ├── events.py         # Group 5: Container Events
│       │   │       ├── leases.py         # Group 6: Leasing
│       │   │       ├── forecast.py       # Group 7: Demand & Forecast
│       │   │       ├── optimization.py   # Group 8: Optimization Runs & Plan
│       │   │       └── dashboard.py      # Group 9: Dashboard & Alerts
│       │   │
│       │   ├── db/                # Database Layer (SQLAlchemy 2.0 + Alembic + Pydantic V2)
│       │   │   ├── database.py    # DB connection engine, session & get_db dependency
│       │   │   ├── enums.py       # CargoPilot domain enums (CompanyType, ContainerType, etc.)
│       │   │   ├── alembic.ini    # Alembic migration configuration
│       │   │   ├── alembic/       # Migration environment & revision scripts
│       │   │   ├── models/        # SQLAlchemy 2.0 ORM Declarative Models (16+ entities)
│       │   │   └── schemas/       # Pydantic V2 camelCase DTOs & Validation schemas
│       │   │
│       │   ├── optimization/      # Optimization Service Layer
│       │   │   ├── input_builder.py  # DB facts aggregator
│       │   │   ├── models.py         # Solver DTOs
│       │   │   ├── solver.py         # Optimization solver engine
│       │   │   └── service.py        # Optimization service coordinator
│       │   │
│       │   ├── domain/            # Domain logic modules
│       │   ├── forecasting/       # Demand forecasting models
│       │   └── services/          # Shared business logic services
│       │
│       └── tests/                 # Integration & Unit Test Suite
│           ├── test_api_v1.py     # API Endpoints (Groups 1-9) tests
│           ├── test_db_schema.py  # ORM Schema & Relationship tests
│           ├── test_health.py     # Health check endpoint tests
│           └── test_main.py       # Root API route tests
│
├── doc/                           # Architecture & Business Specs
│   ├── business-workflow.md       # End-to-end business process specification
│   ├── decision-model.md          # Decision workbench & action specs
│   ├── input-entity.md            # Data entities & input model breakdown
│   ├── optimization-model.md      # Optimization mathematical model definition
│   └── project-definition.md      # Product vision, scope, and technical objectives
│
├── data/                          # Seed datasets, sample event streams & mock data
└── infra/                         # Deployment scripts & cloud infrastructure configurations
```

---

## 🛠️ API V1 Reference

CargoPilot exposes 9 organized API groups under `/api/v1`:

| Group | Category | Key Endpoints | Description |
| :--- | :--- | :--- | :--- |
| **Group 1** | Company & Locations | `GET /company`, `GET /locations`, `GET /locations/:id` | Authenticated company & port/depot directory |
| **Group 2** | Containers & Inventory | `GET /containers`, `GET /containers/:id`, `GET /inventory` | Physical equipment directory & aggregated stock summary |
| **Group 3** | Vessels, Services & Voyages | `GET /vessels`, `GET /services`, `GET /voyages`, `GET /voyages/:id/legs` | Fleet schedule & leg capacity tracking |
| **Group 4** | Bookings & Assignments | `GET /bookings`, `POST /assignments`, `POST /assignments/:id/release` | Confirmed bookings & physical container allocation |
| **Group 5** | Container Events | `POST /container-events`, `GET /containers/:id/events` | Operational event log & automatic container state reconstruction |
| **Group 6** | Leasing | `GET /leases`, `GET /leases/:id` | Lessor container leasing contracts |
| **Group 7** | Demand & Forecast | `GET /demand/forecast`, `POST /demand/forecast`, `PATCH /demand/forecast/:id` | Confirmed demand vs expected demand forecasting |
| **Group 8** | Optimization | `POST /optimization/runs`, `GET /optimization/runs/:id/plan`, `POST /approve` | Optimization execution & recommended plan output |
| **Group 9** | Dashboard | `GET /dashboard/overview`, `GET /dashboard/alerts` | High-level decision metrics & shortage alerts |

---

## 🚀 Quickstart & Local Setup

### Prerequisites
- Python 3.13+
- `uv` package manager (recommended) or standard `pip`

### 1. Install Dependencies & Run Database Migrations

```bash
cd services/api

# Sync dependencies using uv
uv sync

# Run database migrations
uv run alembic -c app/db/alembic.ini upgrade head
```

### 2. Run Test Suite

```bash
uv run pytest
```

### 3. Start API Server

```bash
uv run uvicorn main:app --reload --port 8000
```
- API Base URL: `http://127.0.0.1:8000`
- Interactive OpenAPI Docs: `http://127.0.0.1:8000/docs`