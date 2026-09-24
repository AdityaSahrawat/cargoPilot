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
from typing import AsyncGenerator, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.control import router as control_router
from app.api.state import router as state_router
from app.api.config import router as config_router
from app.kafka.consumer import SimulationKafkaConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("cargopilot.simulation")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    logger.info("CargoPilot Simulation Engine starting up...")

    # ── Database tables ───────────────────────────────────────────────────────
    from app.db.database import create_sim_tables
    try:
        await create_sim_tables()
        logger.info("Simulator-owned database tables verified/created.")
    except Exception as ex:
        logger.warning("Could not auto-create sim tables on startup: %s", ex)

    # ── Kafka consumer (inbound decisions from CargoPilot API) ────────────────
    # Imported here to avoid a circular import at module level.
    # The consumer is a no-op when KAFKA_ENABLED=false.
    from app.api.control import get_controller
    kafka_consumer: Optional[SimulationKafkaConsumer] = None
    try:
        controller = get_controller()
        kafka_consumer = SimulationKafkaConsumer(controller)
        await kafka_consumer.start()
        if kafka_consumer._enabled:
            logger.info("Kafka consumer started — listening for CargoPilot decisions.")
        else:
            logger.info("Kafka consumer in mock mode (KAFKA_ENABLED not set).")
    except Exception as ex:
        logger.warning("Kafka consumer could not start: %s", ex)

    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    if kafka_consumer is not None:
        await kafka_consumer.stop()
    logger.info("CargoPilot Simulation Engine shutting down.")


app = FastAPI(
    title="CargoPilot Simulation Engine",
    description="Discrete-event logistics simulation service using SimPy and PostgreSQL",
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

