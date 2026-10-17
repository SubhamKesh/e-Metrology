"""An RQ worker that runs inside the web process.

Why this exists: the job queue (certificate PDFs, officer/owner emails) needs
a process running RQ's worker. On Render's free plan there is no Background
Worker service, so with REDIS_URL set and nothing consuming the queue, jobs sat
in Redis forever. This module starts the worker as a daemon thread of the
FastAPI process, so the queue always has a consumer with no extra service.

How it fits with load balancing:
  * Every web instance (and every uvicorn --workers process) starts one worker
    thread against the SAME Redis queue. RQ hands each job to exactly one
    worker, so work is spread across all instances and nothing runs twice.
  * Workers register themselves in Redis, which is what jobs.py checks
    (_worker_available) before it queues anything. If Redis is down or no
    worker is alive, callers fall back to sending inline / in a thread.
  * EMBEDDED_WORKER=false switches this off when a dedicated worker service
    (`python run_worker.py`) is deployed instead - recommended on a paid plan,
    because it keeps heavy PDF work away from the API's CPU.

Threads cannot install signal handlers or use SIGALRM, so this uses
SimpleWorker (no fork) with a no-signal death penalty. Per-job timeouts are not
enforced; every job here already uses its own network timeouts.
"""
import logging
import os
import socket
import threading
import time

from app.config.settings import REDIS_URL

logger = logging.getLogger("maapsetu")

EMBEDDED_WORKER_ENABLED = os.getenv("EMBEDDED_WORKER", "true").strip().lower() != "false"
EMBEDDED_WORKER_THREADS = max(1, int(os.getenv("EMBEDDED_WORKER_THREADS", "1") or "1"))

_stop = threading.Event()
_threads: list[threading.Thread] = []


def _build_worker(index: int):
    from redis import Redis
    from rq import SimpleWorker
    from rq.timeouts import BaseDeathPenalty

    from app.services.jobs import QUEUE_NAME

    class NoSignalDeathPenalty(BaseDeathPenalty):
        def setup_death_penalty(self):
            pass

        def cancel_death_penalty(self):
            pass

    class ThreadWorker(SimpleWorker):
        death_penalty_class = NoSignalDeathPenalty

        # signal.signal() only works in the main thread; the web server owns
        # signals, so the worker must not try to install its own.
        def _install_signal_handlers(self):
            pass

        def install_signal_handlers(self):
            pass

    name = f"embedded-{socket.gethostname()}-{os.getpid()}-{index}"
    return ThreadWorker([QUEUE_NAME], connection=Redis.from_url(REDIS_URL), name=name)


def _work_loop(index: int) -> None:
    """Run a worker; if Redis drops or the worker dies, wait and start a fresh one."""
    delay = 2
    while not _stop.is_set():
        try:
            worker = _build_worker(index)
            logger.info("Embedded RQ worker %s listening.", worker.name)
            delay = 2
            worker.work(with_scheduler=False)
        except Exception:
            logger.exception("Embedded RQ worker crashed; restarting in %ss.", delay)
        if _stop.wait(delay):
            break
        delay = min(delay * 2, 60)


def start_embedded_worker() -> bool:
    """Start the worker thread(s). True if started; False when not applicable."""
    if not REDIS_URL:
        return False  # no queue at all: callers already run work inline
    if not EMBEDDED_WORKER_ENABLED:
        logger.info("EMBEDDED_WORKER=false: expecting a dedicated worker process (run_worker.py).")
        return False
    if _threads:
        return True
    _stop.clear()
    for i in range(EMBEDDED_WORKER_THREADS):
        t = threading.Thread(target=_work_loop, args=(i,), name=f"rq-embedded-{i}", daemon=True)
        t.start()
        _threads.append(t)
    return True


def stop_embedded_worker() -> None:
    _stop.set()
    _threads.clear()
