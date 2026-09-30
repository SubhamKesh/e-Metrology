"""
Shared pytest fixtures for the backend test suite.

Uses mongomock instead of a real MongoDB so tests run anywhere (CI, a
laptop with no local Mongo) without needing Atlas credentials. Each test
gets a fresh in-memory database via the `client` fixture.
"""
import mongomock
import pytest
from fastapi.testclient import TestClient
from passlib.context import CryptContext  # Added to hash our dummy password


@pytest.fixture
def client(monkeypatch):
    fake_client = mongomock.MongoClient()
    fake_db = fake_client["maapsetu_test"]

    import app.config.db as dbmod

    monkeypatch.setattr(dbmod, "client", fake_client)
    monkeypatch.setattr(dbmod, "db", fake_db)
    monkeypatch.setattr(dbmod, "users_col", fake_db["users"])
    monkeypatch.setattr(dbmod, "refresh_tokens_col", fake_db["refresh_tokens"])
    monkeypatch.setattr(dbmod, "instruments_col", fake_db["instruments"])
    monkeypatch.setattr(dbmod, "applications_col", fake_db["applications"])
    monkeypatch.setattr(dbmod, "inspections_col", fake_db["inspections"])
    monkeypatch.setattr(dbmod, "certificates_col", fake_db["certificates"])
    monkeypatch.setattr(dbmod, "alerts_col", fake_db["alerts"])

    # Routers/middleware imported the collection objects directly at
    # import time, so they need patching too, not just app.config.db.
    import app.routers.auth as auth_mod
    import app.middleware.auth as auth_mid

    monkeypatch.setattr(auth_mod, "users_col", fake_db["users"])
    monkeypatch.setattr(auth_mod, "refresh_tokens_col", fake_db["refresh_tokens"])
    monkeypatch.setattr(auth_mid, "users_col", fake_db["users"])

    from app.main import app

    try:
        from app.rate_limit import limiter

        limiter.reset()
    except ImportError:
        pass

    return TestClient(app)


@pytest.fixture
def registered_owner(client):
    """
    Bypasses the /register API entirely to avoid OTP verification.
    Directly seeds the test database with a verified user.
    """
    import app.config.db as dbmod
    
    # Hash the password exactly how the app expects it
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed_password = pwd_context.hash("correct-password")
    
    # Create the user document with all required fields
    user_doc = {
        "name": "Test Owner",
        "email": "owner@example.com",
        "password": hashed_password,
        "role": "owner",
        "org_name": "Test Org",      # Added missing required field
        "contact": "9876543210",     # Added missing required field
        "is_verified": True,         # Mark as verified (adjust field name if your app uses something else)
        "is_active": True
    }
    
    # Insert directly into mongomock
    dbmod.users_col.insert_one(user_doc)
    
    return {"email": "owner@example.com", "password": "correct-password"}