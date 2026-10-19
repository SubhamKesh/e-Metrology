"""
Shared pytest fixtures for the backend test suite.

Uses mongomock instead of a real MongoDB so tests run anywhere (CI, a
laptop with no local Mongo) without needing Atlas credentials. Each test
gets a fresh in-memory database via the `client` fixture.
"""
import os

# Tests run on mongomock with no Redis. Setting this to "" before the app is
# imported stops a real REDIS_URL in .env from leaking into the test run
# (python-dotenv does not override variables that are already set).
os.environ["REDIS_URL"] = ""
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

    # Audit trail (app/services/audit.py) writes to its own collection,
    # imported by name — point it at the in-memory DB too, otherwise every
    # audit write would try to reach a real MongoDB.
    import app.services.audit as audit_mod

    monkeypatch.setattr(audit_mod, "audit_logs_col", fake_db["audit_logs"])

    # Certificate validity rules (app/services/validity.py, routers/admin_validity.py), same reason.
    import app.routers.admin_validity as validity_router
    import app.services.validity as validity_service

    monkeypatch.setattr(dbmod, "validity_rules_col", fake_db["validity_rules"])
    monkeypatch.setattr(validity_service, "validity_rules_col", fake_db["validity_rules"])
    monkeypatch.setattr(validity_router, "validity_rules_col", fake_db["validity_rules"])

    # Supporting documents (routers/instrument_documents.py), same reason.
    import app.routers.instrument_documents as documents_router

    monkeypatch.setattr(dbmod, "instrument_documents_col", fake_db["instrument_documents"])
    monkeypatch.setattr(documents_router, "instrument_documents_col", fake_db["instrument_documents"])
    monkeypatch.setattr(documents_router, "instruments_col", fake_db["instruments"])
    monkeypatch.setattr(documents_router, "applications_col", fake_db["applications"])
    monkeypatch.setattr(documents_router, "certificates_col", fake_db["certificates"])
    import app.services.documents as documents_service

    monkeypatch.setattr(documents_service, "instrument_documents_col", fake_db["instrument_documents"])
    import app.routers.instruments as instruments_router

    monkeypatch.setattr(instruments_router, "instruments_col", fake_db["instruments"])
    monkeypatch.setattr(instruments_router, "applications_col", fake_db["applications"])

    # The DDoS middleware counts requests per IP in a process-wide store. Every
    # TestClient request comes from the same IP, so without a fresh store per
    # test the counts pile up across the whole suite and eventually trip the
    # block — which says nothing about the code under test.
    from app.middleware import ddos_protection as ddos_mod
    from app.middleware.ddos_store import InMemoryDDoSStore

    monkeypatch.setattr(ddos_mod, "_store", InMemoryDDoSStore())

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


@pytest.fixture(autouse=True)
def documents_not_required(monkeypatch):
    """Submitting an application needs its required documents (services/documents.py). The older tests
    are about scheduling, inspections and so on, not documents, so they skip that check; the tests in
    test_profile_and_documents.py switch it back on."""
    import app.routers.applications as applications_router

    monkeypatch.setattr(applications_router, "missing_required_documents", lambda *a, **k: [])
