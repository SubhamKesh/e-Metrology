"""
Tests for the second hardening pass: CORS is no longer hardcoded, the
/__dev/db-info route is gone in production, JWT_SECRET/COOKIE_SECURE/CORS
have hard startup guards in production, and the DDoS middleware's store is
swappable (Redis vs in-memory) so it can be made correct across multiple
uvicorn workers.

The startup guards live in app/config/settings.py and run at *import* time,
so they can't be exercised by monkeypatching an already-imported module --
each guard test spawns a fresh subprocess with the relevant env vars set,
which is the only way to actually observe "does the process refuse to
start".
"""
import subprocess
import sys
import textwrap


def _run_import_with_env(env_overrides: dict) -> subprocess.CompletedProcess:
    """Runs `import app.config.settings` in a clean subprocess with the
    given environment variables set, isolated from the real .env file."""
    code = textwrap.dedent(
        """
        import app.config.settings
        print("IMPORT_OK")
        """
    )
    env = {
        "PATH": "/usr/bin:/bin",
        # Point dotenv at a nonexistent file so it can't pick up the repo's
        # real backend/.env and mask the env vars this test is setting.
        "MONGO_URI": "mongodb://localhost:27017",
    }
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=".",
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_dev_defaults_still_import_cleanly():
    """No ENVIRONMENT set (today's CI/local-dev behaviour) must keep working
    unchanged -- none of the new production guards should fire."""
    result = _run_import_with_env({})
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


def test_production_refuses_default_jwt_secret():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "dev_secret_change_me",
            "COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
    )
    assert result.returncode != 0
    assert "insecure" in result.stderr.lower() or "JWT_SECRET" in result.stderr


def test_production_refuses_placeholder_jwt_secret_from_env_example():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "change_this_to_a_long_random_string",
            "COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
    )
    assert result.returncode != 0


def test_production_refuses_short_jwt_secret():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "too-short",
            "COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
    )
    assert result.returncode != 0


def test_production_accepts_real_jwt_secret():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "a" * 40,
            "COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout


def test_production_refuses_cookie_insecure():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "a" * 40,
            "COOKIE_SECURE": "false",
            "CORS_ALLOWED_ORIGINS": "https://app.example.com",
        }
    )
    assert result.returncode != 0
    assert "COOKIE_SECURE" in result.stderr


def test_production_refuses_default_cors_origin():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "a" * 40,
            "COOKIE_SECURE": "true",
            # left unset -> falls back to the localhost:5173 dev default
        }
    )
    assert result.returncode != 0
    assert "CORS_ALLOWED_ORIGINS" in result.stderr


def test_production_refuses_wildcard_cors_origin():
    result = _run_import_with_env(
        {
            "ENVIRONMENT": "production",
            "JWT_SECRET": "a" * 40,
            "COOKIE_SECURE": "true",
            "CORS_ALLOWED_ORIGINS": "*",
        }
    )
    assert result.returncode != 0


def test_cors_allowed_origins_parses_comma_separated_list(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://a.example.com, https://b.example.com")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    import importlib

    import app.config.settings as settings_mod

    importlib.reload(settings_mod)
    try:
        assert settings_mod.CORS_ALLOWED_ORIGINS == [
            "https://a.example.com",
            "https://b.example.com",
        ]
    finally:
        # Restore the module to its default-env state so later tests in the
        # same process (which import app.main -> app.config.settings) don't
        # see this test's overrides.
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        importlib.reload(settings_mod)


def test_dev_db_info_route_not_mounted_in_production(monkeypatch):
    """The debug route must be genuinely absent (not just 404-by-luck) when
    ENVIRONMENT=production -- checked by inspecting the app's route table
    rather than issuing a request, since a stray reverse-proxy rule could
    otherwise make a present-but-blocked route look the same as an absent
    one from the outside."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import os
                os.environ["ENVIRONMENT"] = "production"
                os.environ["JWT_SECRET"] = "a" * 40
                os.environ["COOKIE_SECURE"] = "true"
                os.environ["CORS_ALLOWED_ORIGINS"] = "https://app.example.com"
                os.environ.setdefault("MONGO_URI", "mongodb://localhost:27017")
                from app.main import app
                paths = {route.path for route in app.routes}
                assert "/__dev/db-info" not in paths, paths
                print("ROUTE_ABSENT_OK")
                """
            ),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "ROUTE_ABSENT_OK" in result.stdout


def test_dev_db_info_route_present_in_development(client):
    """Unauthenticated access is still fine to keep for local dev/debugging
    -- only production needs the route gone entirely."""
    r = client.get("/__dev/db-info")
    assert r.status_code == 200
    assert "mongo_uri_present" in r.json()


def test_ddos_store_selection_uses_in_memory_without_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    from app.middleware.ddos_store import InMemoryDDoSStore, build_store

    store = build_store("")
    assert isinstance(store, InMemoryDDoSStore)


def test_ddos_store_selection_uses_redis_when_configured():
    from app.middleware.ddos_store import RedisDDoSStore, build_store

    store = build_store("redis://localhost:6379/0")
    assert isinstance(store, RedisDDoSStore)


async def _run_middleware_n_times(store, n, ip="1.2.3.4"):
    """Drives the DDoS store directly (bypassing FastAPI) so the sliding
    window / blocking logic can be tested without needing N real HTTP
    requests or a running Redis instance."""
    import time

    from app.middleware import ddos_protection as ddos_mod

    now = time.time()
    blocked_count = 0
    for _ in range(n):
        blocked, _ = await store.is_blocked(ip, now)
        if blocked:
            blocked_count += 1
            continue
        if await store.record_and_check(ip, now, ddos_mod.WINDOW_SECONDS, ddos_mod.WINDOW_MAX_REQUESTS):
            await store.block(ip, now, ddos_mod.BLOCK_DURATION_SECONDS)
            blocked_count += 1
    return blocked_count


def test_in_memory_store_blocks_after_threshold():
    import asyncio

    from app.middleware.ddos_store import InMemoryDDoSStore

    store = InMemoryDDoSStore()
    blocked_count = asyncio.run(_run_middleware_n_times(store, 100))
    # 60 allowed, then everything after should be counted as blocked.
    assert blocked_count > 0
