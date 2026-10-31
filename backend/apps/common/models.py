"""The durable record of background work (T5.2, ADR-033).

A task has no result backend (T5.1), so this table is the only place that says whether
something ran. It is also the idempotency guard: ``(task_name, idempotency_key)`` is unique, so
a retried HTTP request, a Celery redelivery, and two workers racing all converge on one row and
one execution rather than one row per attempt.

The row describes the *work*, not the attempt: ``status`` is where the work stands,
``attempts`` counts how many times a worker has claimed it, and ``last_error`` holds the class
of the exception that ended the last attempt — never its message, which can echo a provider
response or a customer's text.
"""

from __future__ import annotations

import uuid

from django.db import models


class TaskStatus(models.TextChoices):
    """Where a piece of background work stands.

    ``failed`` is not terminal: Celery retries the same message, and the record accepts the
    claim again so the retry has somewhere to report. A permanent failure is only visible as
    ``failed`` with no further attempts, which is what the ``task_status`` command looks for.
    """

    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class TaskRecord(models.Model):
    """One unit of background work, keyed so a duplicate dispatch cannot start it twice."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    task_name = models.CharField(max_length=200)
    idempotency_key = models.CharField(
        max_length=200,
        help_text="Derived from the work itself, for example 'ticket:<id>:classify:v<version>'.",
    )
    status = models.CharField(
        max_length=16,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    request_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Request that dispatched the work, for joining logs across API and worker.",
    )
    result = models.JSONField(
        default=dict,
        blank=True,
        help_text="Small, schema-validated outcome data; not a free-form payload dump.",
    )
    last_error = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Exception class of the last failed attempt; never its message.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        # Newest first; the id tie-break keeps pagination deterministic.
        ordering = ("-created_at", "id")
        constraints = [
            # The idempotency guarantee itself. Not partial: a key identifies one piece of
            # work forever, including after it succeeded.
            models.UniqueConstraint(
                fields=("task_name", "idempotency_key"),
                name="unique_task_record_key",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TaskStatus.values),
                name="task_record_status_is_known",
            ),
            # An empty key or name would collapse unrelated work onto one row.
            models.CheckConstraint(
                condition=~models.Q(task_name=""),
                name="task_record_task_name_is_set",
            ),
            models.CheckConstraint(
                condition=~models.Q(idempotency_key=""),
                name="task_record_key_is_set",
            ),
        ]
        indexes = [
            # The status report: counts by status and the oldest pending row.
            models.Index(fields=("status", "created_at"), name="task_record_status_idx"),
            models.Index(fields=("task_name", "-created_at"), name="task_record_name_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.task_name}:{self.idempotency_key} ({self.status})"
