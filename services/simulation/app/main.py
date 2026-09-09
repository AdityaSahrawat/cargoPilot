"""
CargoPilot Simulation Engine — Main Service
============================================
FastAPI application for discrete-event logistics simulation engine microservice.

Doc 1 §5 — System Architecture & Component Responsibilities
Doc 2 §1 — Modeling Philosophy & Mathematical Framework
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.control import router as control_router
from app.api.state import router as state_router
from app.api.config import router as config_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cargopilot.simulation")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    logger.info("CargoPilot Simulation Engine starting up...")
    from app.db.database import create_sim_tables
    try:
        await create_sim_tables()
        logger.info("Simulator-owned database tables verified/created.")
    except Exception as ex:
        logger.warning("Could not auto-create sim tables on startup: %s", ex)
    yield
    logger.info("CargoPilot Simulation Engine shutting down...")


app = FastAPI(
    title="CargoPilot Simulation Engine",
    description="Discrete-event logistics simulation service using SimPy, PostgreSQL, and Kafka",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(control_router)
app.include_router(state_router)
app.include_router(config_router)


@app.get("/health", tags=["system"])
async def health_check() -> Dict[str, str]:
    """Health check probe."""
    return {
        "status": "healthy",
        "service": "cargopilot-simulation",
        "version": "1.0.0",
    }


if __name__ == "__main__":
    import os
    import uvicorn

    port = int(os.environ.get("PORT", 8001))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

