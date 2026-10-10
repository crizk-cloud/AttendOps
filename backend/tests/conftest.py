"""Test setup: a real PostgreSQL test database (TEST_DATABASE_URL), migrated with Alembic.

Tables are truncated between tests. Settings come from fixed test values, never from .env.
"""

import os

from cryptography.fernet import Fernet

TEST_DB = os.environ.get("TEST_DATABASE_URL",
                         "postgresql+psycopg://attendops:attendops@localhost:5432/attendops_test")
os.environ.update({
    "DATABASE_URL": TEST_DB,
    "JWT_SECRET": "test-secret-" + "x" * 40,
    "DEVICE_CREDENTIALS_KEY": Fernet.generate_key().decode(),
    "ENVIRONMENT": "test",
})

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.auth.passwords import hash_password  # noqa: E402
from app.db import Base, get_engine, get_sessionmaker  # noqa: E402
from app.models import AppUser, Role  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest.fixture(scope="session", autouse=True)
def _migrated_db():
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DB)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def _clean_tables():
    yield
    names = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db():
    with get_sessionmaker()() as session:
        yield session


@pytest.fixture
def client():
    from app.main import create_app
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def make_user(db):
    def _make(email: str, role: Role = Role.viewer, active: bool = True) -> AppUser:
        user = AppUser(email=email, role=role, is_active=active, password_hash=hash_password(PASSWORD))
        db.add(user)
        db.commit()
        return user
    return _make


@pytest.fixture
def login(client):
    def _login(email: str, password: str = PASSWORD) -> dict:
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _login
