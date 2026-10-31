"""Dispatch, claims, and outcomes for background work (T5.2, ADR-033).

The convention in one paragraph: a dispatcher derives an idempotency key from the thing the
work is about — ``f"ticket:{ticket.id}:classify:v{ticket.version}"`` — and calls
:func:`dispatch_once`. The first call writes a ``TaskRecord`` and queues the task with that
record's id; every later call with the same key returns ``None`` and queues nothing. A worker
then calls :func:`begin`, which claims the row only from ``pending`` or ``failed``: a duplicate
delivery of a message that already succeeded is skipped, and a retry of a failed attempt is
allowed. So duplicate execution is safe without a second idempotency store (D-08).

Keys are the dispatcher's responsibility because only it knows what the work is about. The key
must change when the work must happen again: reclassifying a ticket after an edit uses the new
version, which is a new row.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.db.models import Count, F
from django.utils import timezone

from apps.common.logging import get_request_id
from apps.common.models import TaskRecord, TaskStatus
from apps.common.tasking import Runnable, enqueue

# Long enough to name any exception class, short enough to stay inside the column.
ERROR_CLASS_MAX = 100


class TaskRecordNotFound(LookupError):
    """A task ran with an id that no row holds.

    Raised rather than ignored: it means a message outlived its record or was tampered with,
    and a silent no-op would hide that from the operator.
    """


def register(
    *, task_name: str, idempotency_key: str, request_id: str = ""
) -> tuple[TaskRecord, bool]:
    """Return the record for this key, creating it on first call.

    ``get_or_create`` closes the race itself: if two callers insert at once the loser re-reads
    the winner's row, so the unique constraint decides who created it rather than who asked.
    """
    return TaskRecord.objects.get_or_create(
        task_name=task_name,
        idempotency_key=idempotency_key,
        defaults={"request_id": request_id[:64]},
    )


def start(record: TaskRecord) -> bool:
    """Claim the work, returning ``False`` when another attempt already owns it.

    The claim is a conditional ``UPDATE``, not a read followed by a save: two workers receiving
    the same message at the same moment cannot both see ``pending``. ``succeeded`` is final, so
    a redelivered message for finished work is skipped instead of running twice.
    """
    claimed = TaskRecord.objects.filter(
        pk=record.pk,
        status__in=(TaskStatus.PENDING, TaskStatus.FAILED),
    ).update(
        status=TaskStatus.RUNNING,
        started_at=timezone.now(),
        finished_at=None,
        last_error="",
        attempts=F("attempts") + 1,
    )
    if claimed:
        record.refresh_from_db()
    return bool(claimed)


def begin(record_id: str | UUID) -> TaskRecord | None:
    """Load and claim a record for execution, or ``None`` when it must not run."""
    record = TaskRecord.objects.filter(pk=record_id).first()
    if record is None:
        raise TaskRecordNotFound(f"No task record with id {record_id}.")
    return record if start(record) else None


def succeed(record: TaskRecord, result: dict[str, object] | None = None) -> None:
    """Mark the work finished, with any small result worth reading later."""
    TaskRecord.objects.filter(pk=record.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        result=result or {},
        last_error="",
    )
    record.refresh_from_db()


def fail(record: TaskRecord, error: BaseException) -> None:
    """Record the failed attempt by exception class only.

    The message is deliberately dropped: a provider error can quote a token or a customer's
    text, and this table is read by operators and, later, by an API. ``failed`` is not final —
    a retry claims the row again (see :func:`start`).
    """
    TaskRecord.objects.filter(pk=record.pk).update(
        status=TaskStatus.FAILED,
        finished_at=timezone.now(),
        last_error=type(error).__name__[:ERROR_CLASS_MAX],
    )
    record.refresh_from_db()


def dispatch_once(
    task: Runnable,
    *,
    idempotency_key: str,
    request_id: str | None = None,
    **kwargs: object,
) -> TaskRecord | None:
    """Queue ``task(record_id, **kwargs)`` once per key, after the transaction commits.

    Returns the record that owns the work, or ``None`` when this key was already dispatched.
    The task is always called with the record id as its first argument, which is what lets the
    worker claim the right row instead of inventing one.

    The request id is captured here rather than in the worker: it is the dispatch site that a
    reader already has, and copying it into the row is what joins an API log line to the task
    that it queued.
    """
    record, created = register(
        task_name=task.name,
        idempotency_key=idempotency_key,
        request_id=(get_request_id() or "") if request_id is None else request_id,
    )
    if not created:
        return None

    enqueue(task, str(record.pk), **kwargs)
    return record


@dataclass(frozen=True)
class TaskSummary:
    """What the ``task_status`` command reports: counts, backlog age, and stuck work."""

    counts: dict[str, int]
    oldest_pending_seconds: float | None
    stuck: list[TaskRecord]


def summary(*, stale_after: timedelta) -> TaskSummary:
    """Aggregate task state from the database, without attaching to the broker.

    Deliberately read-only and broker-free: an operator checking whether work is moving should
    not need a working worker or queue connection, and the API's readiness stays tied to
    PostgreSQL alone (D-14).
    """
    counts = {status.value: 0 for status in TaskStatus}
    for row in TaskRecord.objects.order_by().values("status").annotate(total=Count("id")):
        counts[str(row["status"])] = int(row["total"])

    now = timezone.now()
    oldest_pending: datetime | None = (
        TaskRecord.objects.filter(status=TaskStatus.PENDING)
        .order_by("created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    stuck = list(
        TaskRecord.objects.filter(
            status=TaskStatus.RUNNING, started_at__lt=now - stale_after
        ).order_by("started_at")[:20]
    )
    return TaskSummary(
        counts=counts,
        oldest_pending_seconds=(now - oldest_pending).total_seconds() if oldest_pending else None,
        stuck=stuck,
    )
