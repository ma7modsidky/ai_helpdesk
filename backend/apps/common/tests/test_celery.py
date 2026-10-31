"""Celery wiring: settings, retries, correlation IDs, and after-commit dispatch (T5.1).

Every test here runs with ``CELERY_TASK_ALWAYS_EAGER`` on, which is the point: the suite
proves the conventions without a broker or a worker, so CI needs neither.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from celery import shared_task
from celery.exceptions import Retry

from apps.common.logging import (
    TASK_ID_ABSENT,
    JsonFormatter,
    RequestIdFilter,
    get_task_id,
)
from apps.common.tasking import CorrelatedTask, enqueue
from apps.common.tasks import ping
from config.celery import app

ATTEMPTS: list[int] = []


class Transient(RuntimeError):
    """Stands in for a provider timeout: retryable, unlike a validation error."""


@shared_task(
    bind=True,
    autoretry_for=(Transient,),
    max_retries=2,
    retry_backoff=False,
    retry_jitter=False,
)
def always_transient(self: Any) -> int:
    ATTEMPTS.append(len(ATTEMPTS) + 1)
    raise Transient("try again")


@shared_task(bind=True)
def give_up(self: Any) -> None:
    """Retries with no budget left, which is how a worker reaches the bound."""
    raise self.retry(exc=Transient("exhausted"), max_retries=0)


@shared_task(bind=True)
def read_context(self: Any) -> tuple[str | None, str | None]:
    return get_task_id(), self.request.id


def _record() -> logging.LogRecord:
    return logging.LogRecord(
        name="apps.common.demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="tick",
        args=(),
        exc_info=None,
    )


class _RecordingTask:
    """A stand-in for a task object, so dispatch can be asserted without executing one."""

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args: object) -> None:
        self.calls.append(args)


def test_broker_comes_from_django_settings(settings: Any) -> None:
    assert app.conf.broker_url == settings.CELERY_BROKER_URL
    assert app.conf.broker_url.startswith("amqp://")


def test_every_task_inherits_the_correlated_base_class() -> None:
    # Assigned on the app, not declared per task: a task added later must get the
    # correlation context without remembering to opt in.
    assert issubclass(app.Task, CorrelatedTask)
    assert isinstance(ping, CorrelatedTask)


def test_retry_and_acknowledgement_defaults_are_bounded() -> None:
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.task_max_retries == 3
    assert app.conf.task_default_retry_delay == 30
    assert app.conf.task_soft_time_limit == 120
    assert app.conf.task_time_limit == 180
    assert app.conf.worker_prefetch_multiplier == 1


def test_no_result_backend_is_configured(settings: Any) -> None:
    # The database is the record of what a task did (T5.2), so a result backend would be a
    # second source of truth that a worker restart could empty.
    assert settings.CELERY_RESULT_BACKEND is None
    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert not app.conf.result_backend
    assert app.conf.task_serializer == "json"


# The eager settings are what make every test above run without a broker; `ping.delay()`
# returning proves it is in effect, so this only pins the configuration itself.
def test_the_suite_runs_tasks_without_a_broker(settings: Any) -> None:
    assert settings.CELERY_TASK_ALWAYS_EAGER
    assert settings.CELERY_TASK_EAGER_PROPAGATES


def test_tasks_are_discovered_from_installed_apps() -> None:
    # Discovery, not registration by hand: an app's `tasks.py` is found because the app is
    # installed, which is what keeps a new module from being silently unqueued.
    assert "apps.common.tasks.ping" in app.tasks


def test_a_queued_task_executes_and_returns_its_value() -> None:
    assert ping.delay("hello").get() == "hello"


def test_a_retryable_failure_is_queued_for_another_attempt() -> None:
    ATTEMPTS.clear()

    with pytest.raises(Retry) as caught:
        always_transient.delay()

    # The original exception is preserved, so the retry can report why it happened rather
    # than a generic "retried" message.
    assert isinstance(caught.value.exc, Transient)
    assert len(ATTEMPTS) == 1


def test_retries_stop_at_the_configured_bound() -> None:
    assert always_transient.max_retries == 2

    # Celery re-raises the cause once the budget is spent rather than retrying forever, so a
    # task that can never succeed ends as a failed task the operator can see.
    with pytest.raises(Transient, match="exhausted"):
        give_up.delay()


def test_a_task_binds_its_id_to_the_logging_context() -> None:
    task_id, request_id = read_context.delay().get()

    assert task_id is not None
    assert task_id == request_id
    # The context is reset afterwards, so the next task (or the calling thread) cannot
    # inherit this one's ID.
    assert get_task_id() is None


def test_task_id_reaches_the_log_record_and_the_json_line() -> None:
    record = _record()
    # Attached dynamically by the filter, exactly like request_id in test_logging.py.
    record.task_id = "task-42"

    RequestIdFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert record.task_id == "task-42"  # type: ignore[attr-defined]
    assert payload["task_id"] == "task-42"


def test_absent_task_id_is_logged_as_a_placeholder() -> None:
    record = _record()

    RequestIdFilter().filter(record)
    payload = json.loads(JsonFormatter().format(record))

    assert get_task_id() is None
    assert payload["task_id"] == TASK_ID_ABSENT
    assert record.task_id == TASK_ID_ABSENT  # type: ignore[attr-defined]


@pytest.mark.django_db
def test_enqueue_publishes_only_after_commit(django_capture_on_commit_callbacks: Any) -> None:
    task = _RecordingTask()

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        enqueue(task, "ticket-1")
        # Nothing is published while the transaction is open: a worker must not read a row
        # that a rollback could still remove.
        assert task.calls == []

    assert len(callbacks) == 1
    callbacks[0]()
    assert task.calls == [("ticket-1",)]


@pytest.mark.django_db(transaction=True)
def test_enqueue_publishes_immediately_outside_a_transaction() -> None:
    task = _RecordingTask()

    enqueue(task, "ticket-2")

    assert task.calls == [("ticket-2",)]
