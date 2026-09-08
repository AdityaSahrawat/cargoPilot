#!/usr/bin/env python3
"""
Database Initialization Script for CargoPilot
=============================================
Creates all database tables in PostgreSQL:
1. CargoPilot-owned & shared tables (services/api)
2. Simulator-owned tables (services/simulation)
3. Summarizes all created tables and columns.

Uses standard library only (os, subprocess); executes database operations
inside service venvs via `uv`.
"""
import os
import subprocess

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
API_DIR = os.path.join(ROOT_DIR, "services", "api")
SIM_DIR = os.path.join(ROOT_DIR, "services", "simulation")


def init_api_tables() -> None:
    print("\n--- 1. Creating CargoPilot Tables (services/api) ---")
    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        "from app.db.database import Base, engine; import app.db.models; Base.metadata.create_all(bind=engine); print('CargoPilot tables created successfully.')",
    ]
    subprocess.run(cmd, cwd=API_DIR, check=True)


def init_sim_tables() -> None:
    print("\n--- 2. Creating Simulator-Owned Tables (services/simulation) ---")
    cmd = [
        "uv",
        "run",
        "python",
        "-c",
        "import asyncio; from app.db.database import create_sim_tables; asyncio.run(create_sim_tables()); print('Simulator tables created successfully.')",
    ]
    subprocess.run(cmd, cwd=SIM_DIR, check=True)


def verify_tables() -> None:
    print("\n--- 3. Database Schema Summary ---")
    verify_script = (
        "import os\n"
        "from sqlalchemy import create_engine, inspect\n"
        "url = os.getenv('DATABASE_URL', 'postgresql+psycopg2://postgres:postgres@localhost:5432/cargo_pilot')\n"
        "engine = create_engine(url)\n"
        "inspector = inspect(engine)\n"
        "tables = sorted(inspector.get_table_names())\n"
        "print(f'Total Tables in PostgreSQL: {len(tables)}\\n')\n"
        "for t in tables:\n"
        "    cols = inspector.get_columns(t)\n"
        "    print(f'  - {t:35s} ({len(cols)} columns)')\n"
    )
    cmd = ["uv", "run", "python", "-c", verify_script]
    subprocess.run(cmd, cwd=API_DIR, check=True)
    print("\nDatabase initialization complete! Both services are connected.")


if __name__ == "__main__":
    init_api_tables()
    init_sim_tables()
    verify_tables()
