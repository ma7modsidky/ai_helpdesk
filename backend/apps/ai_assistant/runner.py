"""Claims and outcomes for a classification job (T6.2).

The same convention as ``apps.common.task_records`` (ADR-033), applied to a row that also holds
a typed result: a worker calls :func:`claim`, which takes the job only from ``pending`` or
``failed``. ``succeeded`` is final, so a message Celery delivers twice is dropped instead of
classifying the same ticket twice, and a retry of a failed attempt is allowed.

The row is written here and nowhere else, so an outcome cannot be half-recorded: provenance and
fields land in one ``UPDATE``, and a failure never copies an exception message — a provider
error can quote the prompt, and the prompt contains customer text.
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import F
from django.utils import timezone

from apps.ai_assistant.models import (
    ERROR_CLASS_MAX,
    MODEL_MAX,
    PROVIDER_MAX,
    TicketClassification,
)
from apps.ai_assistant.providers import Completion
from apps.ai_assistant.schemas import Classification
from apps.common.models import TaskStatus


class ClassificationNotFound(LookupError):
    """A task ran with an id that no row holds.

    Raised rather than ignored: it means a message outlived its row or was tampered with, and a
    silent no-op would hide that from the operator.
    """


def claim(classification_id: str | UUID) -> TicketClassification | None:
    """Load and claim a job for execution, or ``None`` when it must not run.

    The claim is a conditional ``UPDATE``, not a read followed by a save: two workers receiving
    the same message at the same moment cannot both see ``pending``.
    """
    job = TicketClassification.objects.filter(pk=classification_id).first()
    if job is None:
        raise ClassificationNotFound(f"No AI classification with id {classification_id}.")

    claimed = TicketClassification.objects.filter(
        pk=job.pk,
        status__in=(TaskStatus.PENDING, TaskStatus.FAILED),
    ).update(
        status=TaskStatus.RUNNING,
        started_at=timezone.now(),
        finished_at=None,
        last_error="",
        attempts=F("attempts") + 1,
    )
    if not claimed:
        return None

    job.refresh_from_db()
    return job


def succeed(
    job: TicketClassification,
    *,
    completion: Completion,
    classification: Classification,
) -> None:
    """Record the validated answer and what produced it."""
    TicketClassification.objects.filter(pk=job.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        provider=completion.provider[:PROVIDER_MAX],
        model=completion.model[:MODEL_MAX],
        latency_ms=completion.latency_ms,
        category=classification.category,
        sentiment=classification.sentiment,
        suggested_priority=classification.suggested_priority,
        confidence=classification.confidence,
        rationale=classification.rationale,
        last_error="",
    )
    job.refresh_from_db()


def fail(job: TicketClassification, error: BaseException) -> None:
    """Record the failed attempt by exception class only.

    ``failed`` is not final: a retry claims the row again. The message is deliberately dropped,
    for the reason in the module docstring.
    """
    TicketClassification.objects.filter(pk=job.pk).update(
        status=TaskStatus.FAILED,
        finished_at=timezone.now(),
        last_error=type(error).__name__[:ERROR_CLASS_MAX],
    )
    job.refresh_from_db()


def supersede(job: TicketClassification) -> None:
    """Finish a job whose ticket changed before a worker reached it.

    The newer version has its own job, so this one is done rather than retried: classifying
    superseded text would only produce an answer no screen should show. ``succeeded`` is the
    honest terminal state for "nothing left to do", and ``attempts`` still records the claim.
    """
    TicketClassification.objects.filter(pk=job.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        last_error="",
    )
    job.refresh_from_db()
