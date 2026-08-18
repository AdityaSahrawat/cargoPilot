# CargoPilot Database System (`services/api/app/db`)

This package houses the operational, planning, and optimization database schema for CargoPilot V1, built with **SQLAlchemy 2.0**, **Alembic**, and **Pydantic V2**.

---

## Directory Structure

```
services/api/app/db/
├── README.md                          # Schema documentation
├── __init__.py                        # Core exports
├── database.py                        # DB Engine, SessionLocal, get_db() dependency
├── enums.py                           # CargoPilot domain enums (CompanyType, ContainerType, etc.)
├── alembic.ini                        # Alembic configuration
├── alembic/
│   ├── env.py                         # Alembic migration runner
│   └── versions/
│       └── 0001_initial_v1_schema.py # V1 database migration script
├── models/                            # SQLAlchemy 2.0 ORM Models
│   ├── base.py                        # UUID & Timestamp mixins
│   ├── company.py                     # Company, CompanyLocation
│   ├── location.py                    # Location (Port & Depot)
│   ├── container.py                   # Container, ContainerEvent
│   ├── vessel.py                      # Vessel
│   ├── service.py                     # Service
│   ├── voyage.py                      # Voyage, VoyagePortCall, VoyageLeg
│   ├── booking.py                     # Booking, EquipmentAssignment
│   ├── lease.py                       # Lease
│   ├── forecast.py                    # DemandForecast
│   └── optimization.py                # OptimizationRun, Reposition, Lease, Inventory, Demand
└── schemas/                           # Pydantic V2 Schemas (DTOs & Validation)
    ├── company.py
    ├── location.py
    ├── container.py
    ├── vessel.py
    ├── service.py
    ├── voyage.py
    ├── booking.py
    ├── lease.py
    ├── forecast.py
    └── optimization.py
```

---

## V1 Schema Entity Summary

### Operational Entities
1. **Company**: Organizations (Carrier, Lessor, Customer, Alliance Partner). `is_self=True` identifies the primary CargoPilot customer.
2. **Location**: Physical ports and depots with capacity, repair capabilities, and UN/LOCODE.
3. **CompanyLocation**: Association tracking home ports and carrier presence.
4. **Vessel**: Physical ships with IMO number, container capacity, owner, and operator.
5. **Service**: Recurring trade routes operated by a company (e.g. Asia → Middle East).
6. **Voyage**: Scheduled execution of a service by a vessel.
7. **VoyagePortCall**: Individual port stops in sequence with arrival/departure timestamps.
8. **VoyageLeg**: Movement between consecutive port calls. Exposes `@hybrid_property` `available_capacity = total_capacity - booked_capacity`.
9. **Container**: Physical container records with owner, status, condition, and current location/voyage tracking.
10. **ContainerEvent**: Operational audit trail (GATE_IN, LOADED, DISCHARGED, DAMAGED, etc.).
11. **Booking**: Confirmed transport requirements linking customer, carrier, origin, destination, container type, and voyage.
12. **EquipmentAssignment**: Specific physical container allocation to a booking.
13. **Lease**: Carrier container usage agreements with lessors (rates, pickup/return ports, durations).

### Planning & Optimization Entities
14. **DemandForecast**: Expected future demand aggregated by location, week, and container type with confidence scoring.
15. **OptimizationRun**: Execution record for the mathematical solver (start week, horizon, status, objective value).
16. **Optimization Results**:
    - `OptimizationReposition`: Solver recommended empty container movements over voyage legs.
    - `OptimizationLease`: Solver recommended container leasing actions.
    - `OptimizationInventory`: Target empty container stock per location and week.
    - `OptimizationDemand`: Served demand, backlog, and shortage projections.

---

## Running Database Migrations

From `services/api`:

```bash
# Run migrations up to latest revision
alembic -c app/db/alembic.ini upgrade head

# Generate a new auto-migration
alembic -c app/db/alembic.ini revision --autogenerate -m "description_of_change"

# Rollback last migration
alembic -c app/db/alembic.ini downgrade -1
```

---

## Code Example: Using Models & Schemas

```python
from app.db.database import get_db
from app.db import models, schemas, enums

# Using FastAPI dependency
def create_new_company(company_in: schemas.CompanyCreate, db=Depends(get_db)):
    db_company = models.Company(**company_in.model_dump())
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return schemas.CompanyResponse.model_validate(db_company)
```
