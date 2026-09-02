import os
import sys
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from main import app
from app.db.database import Base, get_db, get_test_db
from tests.test_world.scenario_builder import ScenarioBuilder
from app.test_worlds.world_1.db_seeder import reseed_world_1_db


@pytest.fixture(scope="function")
def api_client():
    """Test client using an isolated in-memory SQLite database for full REST API & Scenario tests."""
    prod_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_engine_inst = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=prod_engine)
    Base.metadata.create_all(bind=test_engine_inst)

    ProdSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=prod_engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine_inst)

    def override_get_db():
        db = ProdSessionLocal()
        try:
            yield db
        finally:
            db.close()

    def override_get_test_db():
        db = TestSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_test_db] = override_get_test_db

    # Seed prod DB with base world
    prod_db = ProdSessionLocal()
    builder = ScenarioBuilder(prod_db)
    builder.setup_base_world()

    # Seed test DB with World 1 canonical dataset
    test_db = TestSessionLocal()
    reseed_world_1_db(test_db)

    client = TestClient(app)
    yield client, prod_db

    app.dependency_overrides.clear()
    prod_db.close()
    test_db.close()
