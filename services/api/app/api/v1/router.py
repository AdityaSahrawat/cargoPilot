from fastapi import APIRouter

from app.api.v1 import (
    company,
    containers,
    vessels,
    bookings,
    events,
    leases,
    forecast,
    optimization,
    dashboard,
)

api_v1_router = APIRouter()

api_v1_router.include_router(company.router, tags=["Group 1 — Company & Locations"])
api_v1_router.include_router(containers.router, tags=["Group 2 — Container & Inventory"])
api_v1_router.include_router(vessels.router, tags=["Group 3 — Vessels, Services & Voyages"])
api_v1_router.include_router(bookings.router, tags=["Group 4 — Bookings & Equipment Assignment"])
api_v1_router.include_router(events.router, tags=["Group 5 — Container Events"])
api_v1_router.include_router(leases.router, tags=["Group 6 — Leasing"])
api_v1_router.include_router(forecast.router, tags=["Group 7 — Demand & Forecast"])
api_v1_router.include_router(optimization.router, tags=["Group 8 — Optimization"])
api_v1_router.include_router(dashboard.router, tags=["Group 9 — Dashboard"])
