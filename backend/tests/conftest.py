"""
Shared pytest fixtures for the backend test suite.

Uses mongomock instead of a real MongoDB so tests run anywhere (CI, a
laptop with no local Mongo) without needing Atlas credentials. Each test
gets a fresh in-memory database via the `client` fixture.
"""
import mongomock
import pytest
from fastapi.testclient import TestClient


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
    client.post(
        "/api/v1/auth/register",
        json={
            "name": "Test Owner",
            "email": "owner@example.com",
            "password": "correct-password",
            "role": "owner",
        },
    )
    return {"email": "owner@example.com", "password": "correct-password"}
