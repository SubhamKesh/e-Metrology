"""
Runs the background job worker that processes certificate generation
(see app/services/jobs.py). Start this as its own long-running process,
alongside uvicorn -- same idea as running a second uvicorn instance for
the WebSocket fan-out test, just a different kind of process this time.

Uses rq.SimpleWorker rather than plain rq.Worker: the default Worker forks
a child process per job (via os.fork) to enforce a hard timeout on each
job. os.fork() doesn't exist on Windows, so the default Worker crashes
immediately there. SimpleWorker runs each job in the same process instead
-- no per-job timeout enforcement, but it actually runs on Windows, which
matters more for this project's dev environment than the timeout
guarantee does. (On a Linux production host, switching to the default
Worker for real timeout enforcement is a reasonable upgrade -- not
necessary to get this working today.)

Usage (from backend/, same venv as uvicorn):
    python run_worker.py

Leave it running in its own terminal. It logs each job it picks up and
each one's result; Ctrl+C to stop it, same as uvicorn.
"""
from redis import Redis
from rq import SimpleWorker

from app.config.settings import REDIS_URL
from app.services.jobs import QUEUE_NAME

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
    worker = SimpleWorker([QUEUE_NAME], connection=conn)
    print(f"Worker started, listening on queue '{QUEUE_NAME}'. Ctrl+C to stop.")
    worker.work()
