import os
from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Main / Production Database
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cargo_pilot.db")

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=os.getenv("SQL_ECHO", "False").lower() in ("true", "1"),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Isolated Test Environment Database
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./cargo_pilot_test.db")
test_connect_args = {}
if TEST_DATABASE_URL.startswith("sqlite"):
    test_connect_args["check_same_thread"] = False

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args=test_connect_args,
    echo=False,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide a transactional production database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_test_db() -> Generator[Session, None, None]:
    """FastAPI dependency to provide an isolated test database session for Scenario Lab."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()
