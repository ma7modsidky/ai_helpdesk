"""Simulated and smoke tasks (T5.1, T5.4).

``ping`` is the connectivity check. ``simulate_work`` is the failing/slow task the observability
and retry conventions are exercised with: it is deliberately artificial, so a slowdown or a
failure can be produced on a real worker without a provider, a fixture, or a code change.
"""

from __future__ import annotations

import logging
import time

from celery import shared_task

from apps.common.task_records import begin, succeed
from apps.common.task_records import fail as record_failure

logger = logging.getLogger(__name__)

# Sleeping is capped so a mistyped argument cannot occupy a worker for the full time limit.
MAX_SIMULATED_SECONDS = 5.0


class SimulatedTaskFailure(RuntimeError):
    """Raised on request by ``simulate_work``; retryable, like a provider timeout."""


@shared_task(max_retries=3, retry_backoff=2, retry_jitter=True)
def ping(message: str = "pong") -> str:
    """Round-trip smoke task: proves the broker, a worker, and the log context.

    Queue it from a shell to confirm a deployment's queue before trusting it with real work:

        from apps.common.tasks import ping
        ping.delay("hello")

    The worker's log line carries a ``task_id`` and this message, which is the smallest
    end-to-end check of the asynchronous path. It touches no database and no external
    service, so it is also safe to run against a production worker.
    """
    logger.info("Task ping ran with message %r.", message)
    return message


@shared_task(
    autoretry_for=(SimulatedTaskFailure,),
    max_retries=3,
    retry_backoff=2,
    retry_jitter=False,
)
def simulate_work(record_id: str, *, seconds: float = 0.0, should_fail: bool = False) -> str:
    """Do nothing slowly, or fail on purpose, while recording what happened.

    The task-side half of the idempotency convention: ``begin`` claims the record, and returns
    ``None`` when the work already succeeded or another attempt holds it, in which case this
    message is a duplicate and is dropped. Anything that goes wrong is recorded against the
    record by class and then re-raised, so Celery's retry policy applies to it too.
    """
    record = begin(record_id)
    if record is None:
        logger.info("Task simulate_work skipped: work already done or in flight.")
        return "skipped"

    started = time.monotonic()
    try:
        if seconds > 0:
            time.sleep(min(seconds, MAX_SIMULATED_SECONDS))
        if should_fail:
            raise SimulatedTaskFailure("simulated failure")
    except Exception as exc:
        record_failure(record, exc)
        raise

    succeed(record, {"seconds": round(time.monotonic() - started, 3), "attempt": record.attempts})
    return "succeeded"
