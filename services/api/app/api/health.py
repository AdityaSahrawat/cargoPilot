from fastapi import APIRouter
from os import getenv
from typing import Dict

router = APIRouter()


def _component_status(name: str, configured: bool) -> Dict:
    return {
        "name": name,
        "status": "ok" if configured else "unknown",
        "configured": configured,
    }


@router.get("/", summary="Aggregate health status")
async def health() -> Dict:
    """Return overall service health and component statuses."""
    # Simple checks based on environment configuration presence.
    db_configured = bool(getenv("DATABASE_URL"))
    kafka_configured = bool(getenv("KAFKA_BOOTSTRAP_SERVERS"))

    components = [
        _component_status("database", db_configured),
        _component_status("kafka", kafka_configured),
    ]

    overall = "ok" if all(c["status"] == "ok" for c in components) else "degraded"

    return {"status": overall, "components": components}


@router.get("/ready", summary="Readiness probe")
async def readiness() -> Dict:
    """Readiness: verifies required configuration is present."""
    # Treat database config as required for readiness
    db_configured = bool(getenv("DATABASE_URL"))
    ready = db_configured
    details = {"database_configured": db_configured}
    return {"ready": ready, "details": details}


@router.get("/live", summary="Liveness probe")
async def liveness() -> Dict:
    """Liveness: basic liveness check.

    This returns success as long as the process is running. Keep lightweight.
    """
    return {"live": True}
