"""
Database Configuration
=======================
Async PostgreSQL session using SQLAlchemy + asyncpg.

The simulation engine connects to the SHARED CargoPilot PostgreSQL database.
PostgreSQL is the single authoritative persistent state (Doc 2 §25.1).

Ownership:
    - Simulation writes to simulator-owned tables (sim_models.py).
    - CargoPilot writes to its own tables.
    - Both read shared tables (vessels, locations, voyages, containers, bookings).
    - The simulation engine does NOT write to CargoPilot-owned tables.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


# ---------------------------------------------------------------------------
# Database URL
# ---------------------------------------------------------------------------

DATABASE_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/cargo_pilot",
)

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

engine: AsyncEngine = create_async_engine(
    DATABASE_URL,
    echo=os.environ.get("SQL_ECHO", "false").lower() in ("true", "1"),
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)

# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Declarative base (for simulator-owned models only)
# ---------------------------------------------------------------------------

class SimBase(DeclarativeBase):
    """
    Base class for simulator-owned ORM models.

    Services/api tables use their own Base. This base is strictly for
    tables the simulation engine owns (sim_models.py).
    """
    pass


# ---------------------------------------------------------------------------
# Session dependency
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency. Provides an async session per request.

    Usage::

        @router.get("/state")
        async def get_state(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

async def create_sim_tables() -> None:
    """
    Create all simulator-owned tables (sim_models.py) if they do not exist.
    Called at application startup.

    Note: Services/api tables are managed by services/api migrations.
    This only creates simulation-specific tables.
    """
    # Import here to avoid circular imports at module load
    import app.db.sim_models  # noqa: F401  — registers models on SimBase.metadata
    async with engine.begin() as conn:
        await conn.run_sync(SimBase.metadata.create_all)
