"""Durable state for one AI classification job (T6.2, ADR-035).

A background task has no result backend (ADR-033), so this row is where the job lives: its
status, how many workers claimed it, what the provider reported, and the validated fields. It is
also the idempotency guard — ``(ticket, ticket_version)`` is unique — so a retried request, a
redelivered message, and two workers racing converge on one row and one classification.

Two decisions are deliberate:

- **The row is per ticket version, not per ticket.** A classification describes the text it was
  given. Editing a ticket therefore creates a new job instead of overwriting the answer that
  referred to the old text, so the UI can never show a stale suggestion as current.
- **The workspace is copied from the ticket.** Every read can then be tenant-scoped with one
  filter, and the row is only ever written by ``apps.ai_assistant.runner``, which copies the
  value from the ticket rather than accepting it from a caller.

Nothing here is applied to a ticket automatically: the record only *suggests* a category and
priority, and a human decides (05 §2).
"""

from __future__ import annotations

import uuid

from django.db import models

from apps.common.models import TaskStatus

# Column bounds, named here because the task and the schema both trim to them.
PROVIDER_MAX = 64
MODEL_MAX = 128
PROMPT_VERSION_MAX = 32
ERROR_CLASS_MAX = 100


class Sentiment(models.TextChoices):
    """The allowlisted sentiments a classification may report (05 §2)."""

    POSITIVE = "positive", "Positive"
    NEUTRAL = "neutral", "Neutral"
    NEGATIVE = "negative", "Negative"


class TicketClassification(models.Model):
    """One job: classify a specific version of a ticket's text."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    workspace = models.ForeignKey(
        "organizations.Workspace",
        on_delete=models.CASCADE,
        related_name="ai_classifications",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.CASCADE,
        related_name="classifications",
    )
    ticket_version = models.PositiveIntegerField(
        help_text="The ticket version this job read; a later edit is a different job.",
    )
    prompt_version = models.CharField(
        max_length=PROMPT_VERSION_MAX,
        help_text="Which prompt produced the result, so a quality change is attributable.",
    )
    status = models.CharField(
        max_length=16,
        choices=TaskStatus.choices,
        default=TaskStatus.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    # Provenance, filled in on success: a later quality question is answered from data rather
    # than from whatever the deployment happened to run at the time (05 §6).
    provider = models.CharField(max_length=PROVIDER_MAX, blank=True, default="")
    model = models.CharField(max_length=MODEL_MAX, blank=True, default="")
    latency_ms = models.FloatField(null=True, blank=True)
    category = models.CharField(max_length=100, blank=True, default="")
    sentiment = models.CharField(max_length=16, blank=True, default="")
    suggested_priority = models.CharField(max_length=16, blank=True, default="")
    confidence = models.FloatField(null=True, blank=True)
    rationale = models.CharField(
        max_length=280,
        blank=True,
        default="",
        help_text="One short sentence of evidence; never an authoritative statement.",
    )
    last_error = models.CharField(
        max_length=ERROR_CLASS_MAX,
        blank=True,
        default="",
        help_text="Exception class of the last failed attempt; never its message.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            # The idempotency guarantee: one job per ticket version, forever.
            models.UniqueConstraint(
                fields=("ticket", "ticket_version"),
                name="unique_classification_per_version",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=TaskStatus.values),
                name="classification_status_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(sentiment__in=["", *Sentiment.values]),
                name="classification_sentiment_is_known",
            ),
            models.CheckConstraint(
                condition=models.Q(ticket_version__gte=1),
                name="classification_version_is_positive",
            ),
            # A score outside [0, 1] is not a confidence; the schema rejects it too, so this
            # only guards a bug or a hand-written row.
            models.CheckConstraint(
                condition=models.Q(confidence__isnull=True)
                | models.Q(confidence__gte=0, confidence__lte=1),
                name="classification_confidence_is_a_probability",
            ),
        ]
        indexes = [
            # The operator view: what is queued, running, or stuck in this workspace.
            models.Index(fields=("workspace", "status", "created_at"), name="class_ws_status_idx"),
        ]

    def __str__(self) -> str:
        return f"classification {self.ticket_id} v{self.ticket_version} ({self.status})"
