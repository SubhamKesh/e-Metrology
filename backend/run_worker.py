"""
Runs the background job worker that processes certificate generation
and owner email notifications (see app/services/jobs.py). Start this as
its own long-running process, alongside uvicorn.

Uses rq.SimpleWorker (no os.fork, which Windows lacks) with a custom
death penalty class (no signal.SIGALRM, which Windows also lacks).
Trade-off: per-job timeouts are NOT enforced here. On a Linux production
host, switch back to the default rq.Worker to get real timeout enforcement.

Usage (from backend/, same venv as uvicorn):
    python run_worker.py

Leave it running in its own terminal. Ctrl+C to stop it.
"""
from redis import Redis
from rq import SimpleWorker
from rq.timeouts import BaseDeathPenalty

from app.config.settings import REDIS_URL
from app.services.jobs import QUEUE_NAME

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)



class NoSignalDeathPenalty(BaseDeathPenalty):
    """Windows has no SIGALRM, so skip signal-based job timeouts."""

    def setup_death_penalty(self):
        pass

    def cancel_death_penalty(self):
        pass


class WindowsWorker(SimpleWorker):
    death_penalty_class = NoSignalDeathPenalty


if __name__ == "__main__":
    if not REDIS_URL:
        raise SystemExit(
            "REDIS_URL is not set -- there's no queue to work from. "
            "Without Redis, certificate generation runs inline in the "
            "request instead (see app/routers/inspections.py), so this "
            "worker process has nothing to do. Set REDIS_URL in .env "
            "first if you want to actually use the background queue."
        )
    conn = Redis.from_url(REDIS_URL)
    worker = WindowsWorker([QUEUE_NAME], connection=conn)
    print(f"Worker started, listening on queue '{QUEUE_NAME}'. Ctrl+C to stop.")
    worker.work()