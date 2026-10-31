"""Background-task conventions shared by every Celery task (T5.1, ADR-032).

Three things belong here rather than in each task module:

- ``CorrelatedTask`` binds the task ID to the logging context for the duration of the run.
  It is the task-side counterpart of ``apps.common.middleware.RequestIdMiddleware``, so a
  worker line can be matched to the dispatch site that logged the same ID.
- ``enqueue`` publishes only after the surrounding transaction commits. Publishing inside a
  transaction lets a worker read a row that a later rollback deletes; ``transaction.on_commit``
  is the MVP-sized version of the outbox pattern the architecture recommends (02 §2).
- No result backend is configured. Durable task state belongs in the database (T5.2), so
  nothing depends on an in-memory result that a worker restart would lose.
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any, Protocol

from celery.app.task import Task
from celery.exceptions import Retry
from django.db import transaction

from apps.common.logging import TASK_ID_ABSENT, reset_task_id, set_task_id

logger = logging.getLogger(__name__)


class Runnable(Protocol):
    """Anything with Celery's name and ``delay`` signature, so tests can pass a stand-in."""

    name: str

    def delay(self, *args: Any, **kwargs: Any) -> Any: ...


# The stubs declare `Task` generic while the runtime class is not subscriptable, so the
# parameters are supplied for the checker and ignored at runtime.
class CorrelatedTask(Task):  # type: ignore[type-arg]
    """Attach the running task's ID to every log record the task emits.

    Installed through ``CELERY_TASK_CLS``, so this applies to tasks that never mention it.
    The reset happens in ``finally``: a worker process reuses the context for the next task,
    and a leaked ID would attribute one task's log lines to another.

    Each run also emits one structured outcome line — task name, outcome, duration — because
    "how long does this take and how often does it fail" is otherwise only answerable by
    reading every task's code. The fields are separate keys in the JSON line so a log-based
    metric can aggregate them without parsing prose.
    """

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        token = set_task_id(self.request.id or TASK_ID_ABSENT)
        started = time.monotonic()
        try:
            result = super().__call__(*args, **kwargs)
        except Retry:
            # Not a failure: the task asked to run again later.
            self._log_outcome(outcome="retried", started=started)
            raise
        except Exception as exc:
            self._log_outcome(outcome="failed", started=started, error=exc)
            raise
        else:
            self._log_outcome(outcome="succeeded", started=started)
            return result
        finally:
            reset_task_id(token)

    def _log_outcome(
        self, *, outcome: str, started: float, error: BaseException | None = None
    ) -> None:
        """One line per run, with the fields a metric or an alert would read."""
        duration_ms = round((time.monotonic() - started) * 1000, 1)
        suffix = f" ({type(error).__name__})" if error is not None else ""
        logger.info(
            "Task %s %s in %sms%s.",
            self.name,
            outcome,
            duration_ms,
            suffix,
            extra={
                "task_name": self.name,
                "task_outcome": outcome,
                "task_duration_ms": duration_ms,
            },
        )


def enqueue(task: Runnable, /, *args: object, **kwargs: object) -> None:
    """Queue ``task(*args, **kwargs)`` once the current transaction commits.

    Call this from inside the transaction that produced the data the task will read. Outside
    a transaction it runs immediately, which is Django's documented ``on_commit`` behaviour
    and is what tests exercise.
    """

    transaction.on_commit(functools.partial(task.delay, *args, **kwargs))
