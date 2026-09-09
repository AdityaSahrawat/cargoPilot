"""
CargoPilot Simulation Service — Entrypoint
===========================================
Allows running `uv run main.py` directly from `services/simulation`.
"""
import os
import uvicorn

from app.main import app

__all__ = ["app"]

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    host = os.environ.get("HOST", "127.0.0.1")
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
