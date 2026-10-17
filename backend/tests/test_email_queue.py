"""Email queue: jobs must fail loudly (so RQ retries), the worker check is cached,
and the embedded worker only starts when there is a queue to consume."""
import pytest


def test_credentials_job_raises_when_the_mail_was_not_sent(client, monkeypatch):
    import app.services.jobs as jobs

    monkeypatch.setattr(jobs, "send_officer_credentials", lambda **kw: False)
    with pytest.raises(jobs.MailSendError):
        jobs.send_officer_credentials_job(to="a@example.com", name="A", role="lmo", temp_password="x")

    monkeypatch.setattr(jobs, "send_officer_credentials", lambda **kw: True)
    jobs.send_officer_credentials_job(to="a@example.com", name="A", role="lmo", temp_password="x")


def test_password_reset_job_raises_when_the_mail_was_not_sent(client, monkeypatch):
    import app.services.jobs as jobs

    monkeypatch.setattr(jobs, "send_admin_password_reset", lambda **kw: False)
    with pytest.raises(jobs.MailSendError):
        jobs.send_admin_password_reset_job(to="a@example.com", name="A", temp_password="x")


def test_worker_check_is_cached_briefly(client, monkeypatch):
    import rq

    import app.services.jobs as jobs

    calls = []

    def fake_count(cls, *a, **k):
        calls.append(1)
        return 1

    monkeypatch.setattr(rq.Worker, "count", classmethod(fake_count))
    monkeypatch.setattr(jobs, "_worker_check", (float("-inf"), False))
    assert jobs._worker_available(object()) is True
    assert jobs._worker_available(object()) is True
    assert len(calls) == 1  # second call came from the cache


def test_enqueue_email_retries(client):
    import app.services.jobs as jobs

    seen = {}

    class FakeQueue:
        def enqueue_call(self, **kw):
            seen.update(kw)

    jobs.enqueue_email(FakeQueue(), jobs.send_admin_password_reset_job, to="a@example.com", name="A", temp_password="x")
    assert seen["kwargs"] == {"to": "a@example.com", "name": "A", "temp_password": "x"}
    assert seen["retry"].max == len(jobs.EMAIL_RETRY_INTERVALS)


def test_embedded_worker_needs_a_queue_and_can_be_switched_off(client, monkeypatch):
    import app.services.embedded_worker as ew

    monkeypatch.setattr(ew, "_threads", [])
    monkeypatch.setattr(ew, "REDIS_URL", "")
    assert ew.start_embedded_worker() is False  # no Redis -> nothing to consume

    monkeypatch.setattr(ew, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(ew, "EMBEDDED_WORKER_ENABLED", False)
    assert ew.start_embedded_worker() is False  # dedicated worker expected instead


def test_embedded_worker_starts_a_thread_when_enabled(client, monkeypatch):
    import threading

    import app.services.embedded_worker as ew

    started = threading.Event()
    monkeypatch.setattr(ew, "_threads", [])
    monkeypatch.setattr(ew, "REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setattr(ew, "EMBEDDED_WORKER_ENABLED", True)
    monkeypatch.setattr(ew, "EMBEDDED_WORKER_THREADS", 1)
    monkeypatch.setattr(ew, "_work_loop", lambda index: started.set())
    try:
        assert ew.start_embedded_worker() is True
        assert started.wait(2)
    finally:
        ew.stop_embedded_worker()
