"""Task records: idempotent dispatch, claims, and safe failure reporting (T5.2)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone

from apps.common.logging import reset_request_id, set_request_id
from apps.common.models import TaskRecord, TaskStatus
from apps.common.task_records import (
    TaskRecordNotFound,
    begin,
    dispatch_once,
    fail,
    register,
    start,
    succeed,
    summary,
)

pytestmark = pytest.mark.django_db

TASK_NAME = "apps.common.tasks.simulate_work"


def _register(key: str = "ticket:1:classify:v1", *, request_id: str = "") -> TaskRecord:
    record, _ = register(task_name=TASK_NAME, idempotency_key=key, request_id=request_id)
    return record


class _FakeTask:
    """A task stand-in: dispatch is asserted without queueing or executing anything."""

    name = TASK_NAME

    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def delay(self, *args: object) -> None:
        self.calls.append(args)


def test_registering_the_same_key_twice_returns_the_first_record() -> None:
    first, created_first = register(task_name=TASK_NAME, idempotency_key="ticket:1")
    second, created_second = register(task_name=TASK_NAME, idempotency_key="ticket:1")

    assert created_first is True
    assert created_second is False
    assert second.pk == first.pk


def test_the_same_key_under_two_task_names_is_two_pieces_of_work() -> None:
    first, _ = register(task_name="apps.common.tasks.ping", idempotency_key="ticket:1")
    second, _ = register(task_name=TASK_NAME, idempotency_key="ticket:1")

    assert first.pk != second.pk


def test_register_records_the_request_that_queued_the_work() -> None:
    assert _register(request_id="req-123").request_id == "req-123"


def test_a_claim_moves_pending_to_running_and_counts_the_attempt() -> None:
    record = _register()

    assert start(record) is True
    assert record.status == TaskStatus.RUNNING
    assert record.attempts == 1
    assert record.started_at is not None


def test_a_second_claim_while_running_is_refused() -> None:
    record = _register()
    start(record)

    assert start(record) is False
    # The duplicate delivery did not consume a retry.
    assert record.attempts == 1


def test_a_retry_may_claim_a_failed_record_again() -> None:
    record = _register()
    start(record)
    fail(record, RuntimeError("boom"))

    assert record.status == TaskStatus.FAILED
    assert start(record) is True
    assert record.attempts == 2


def test_finished_work_is_never_claimed_again() -> None:
    record = _register()
    start(record)
    succeed(record)

    assert start(record) is False
    assert record.status == TaskStatus.SUCCEEDED


def test_failure_records_the_exception_class_and_not_its_message() -> None:
    record = _register()
    start(record)

    fail(record, RuntimeError("provider said token=secret-value"))

    # A message can quote a credential or a customer's text, and this table is read by
    # operators and later by an API; only the class is stored.
    assert record.last_error == "RuntimeError"
    assert record.status == TaskStatus.FAILED
    assert "secret-value" not in record.last_error


def test_success_records_the_result_and_the_finish_time() -> None:
    record = _register()
    start(record)

    succeed(record, {"seconds": 0.25})

    assert record.status == TaskStatus.SUCCEEDED
    assert record.result == {"seconds": 0.25}
    assert record.finished_at is not None


def test_begin_raises_for_an_unknown_record() -> None:
    with pytest.raises(TaskRecordNotFound):
        begin("00000000-0000-0000-0000-000000000000")


def test_begin_returns_none_for_finished_work() -> None:
    record = _register()
    start(record)
    succeed(record)

    assert begin(record.pk) is None


def test_dispatch_once_queues_one_message_per_key(
    django_capture_on_commit_callbacks: Any,
) -> None:
    task = _FakeTask()

    with django_capture_on_commit_callbacks(execute=True):
        first = dispatch_once(task, idempotency_key="ticket:1")
        second = dispatch_once(task, idempotency_key="ticket:1")

    assert first is not None
    assert second is None
    assert len(task.calls) == 1
    # The task always receives the record id, so the worker claims the row instead of
    # inventing a second one.
    assert task.calls[0] == (str(first.pk),)


def test_dispatch_once_copies_the_request_id_from_the_caller(
    django_capture_on_commit_callbacks: Any,
) -> None:
    task = _FakeTask()
    token = set_request_id("req-9")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            record = dispatch_once(task, idempotency_key="ticket:2")
    finally:
        reset_request_id(token)

    assert record is not None
    assert record.request_id == "req-9"


def test_summary_counts_by_status_and_flags_stuck_work() -> None:
    _register("k-pending")
    running = _register("k-running")
    start(running)
    TaskRecord.objects.filter(pk=running.pk).update(started_at=timezone.now() - timedelta(hours=1))
    succeeded = _register("k-succeeded")
    start(succeeded)
    succeed(succeeded)

    report = summary(stale_after=timedelta(minutes=15))

    assert report.counts[TaskStatus.PENDING.value] == 1
    assert report.counts[TaskStatus.RUNNING.value] == 1
    assert report.counts[TaskStatus.SUCCEEDED.value] == 1
    assert [row.pk for row in report.stuck] == [running.pk]
    assert report.oldest_pending_seconds is not None


def test_summary_has_no_backlog_when_nothing_is_pending() -> None:
    record = _register()
    start(record)
    succeed(record)

    report = summary(stale_after=timedelta(minutes=15))

    assert report.oldest_pending_seconds is None
    assert report.stuck == []
