import os

# Must be set BEFORE app.main is imported: the lifespan reads it to skip
# spawning the background sweep loops that deadlock full-suite teardown.
# Production/dev never set this; only tests do.
os.environ.setdefault("DISABLE_BACKGROUND_SWEEPS", "1")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base
from app.dependencies import get_db
from app import models  # noqa: F401 - ensure all model metadata is registered for test DB setup
from app.models.user import User
from app.utils.password import hash_password

TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "postgresql://postgres:postgres@db/mickeymouse_test")


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(TEST_DB_URL)
    with engine.connect() as conn:
        conn.execute(text("COMMIT"))
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db(test_engine):
    TestingSession = sessionmaker(bind=test_engine)
    session = TestingSession()
    yield session
    session.rollback()
    session.close()


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def admin_user(db):
    user = db.query(User).filter(User.email == "admin@test.com").first()
    if not user:
        user = User(
            email="admin@test.com",
            name="Test Admin",
            password_hash=hash_password("password123"),
            role="admin",
            is_active=True,
        )
        db.add(user)
    else:
        user.name = "Test Admin"
        user.password_hash = hash_password("password123")
        user.role = "admin"
        user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def admin_token(client, admin_user):
    response = client.post("/api/auth/login", json={"email": "admin@test.com", "password": "password123"})
    return response.json()["access_token"]


@pytest.fixture
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}
