from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from app.api import health
from app.api.v1 import api_v1_router
from app.db.database import Base, engine, test_engine, SessionLocal, TestSessionLocal
from app.db import models
from tests.test_world.scenario_builder import ScenarioBuilder


from app.db.enums import LocationType
from app.test_worlds.world_1.db_seeder import reseed_world_1_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure both Production DB and Isolated Test DB tables exist and are populated on startup."""
    Base.metadata.create_all(bind=engine)
    Base.metadata.create_all(bind=test_engine)

    # Seed production DB baseline if empty
    prod_db = SessionLocal()
    try:
        if not prod_db.query(models.Company).first():
            builder = ScenarioBuilder(prod_db)
            builder.setup_base_world()
    finally:
        prod_db.close()

    # Seed isolated test DB (cargo_pilot_test.db) with canonical World 1 dataset if empty
    test_db = TestSessionLocal()
    try:
        if not test_db.query(models.Location).filter(models.Location.location_type == LocationType.PORT).first():
            reseed_world_1_db(test_db)
    finally:
        test_db.close()

    yield


app = FastAPI(title="CargoPilot API", version="1.0.0", lifespan=lifespan)

# Enable CORS for frontend applications (e.g., localhost:3000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {"status": "ok", "service": "cargoPilot-api"}


app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(api_v1_router, prefix="/api/v1")


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
