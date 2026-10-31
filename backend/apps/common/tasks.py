"""Celery tasks that belong to no single domain app (T5.1).

Domain apps add their own ``tasks.py``; this module holds the ones that are about the
infrastructure itself.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


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
