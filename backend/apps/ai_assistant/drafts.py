"""Draft dispatch, claims, and outcomes (T6.3).

The lifecycle mirrors ``runner.py`` for classification, with two deliberate differences:

- **A draft is requested, not automatic.** A classification is queued by ticket creation; a
  draft is queued by a person who intends to answer, so it needs its own throttle and its own
  permission check.
- **There is no unique key.** Asking again after an edit, or after a failure, is legitimate, so
  the table allows several drafts per ticket. What it does *not* allow is a second job while one
  for the same version is still pending or running: :func:`request_draft` returns the in-flight
  one instead, which makes a double click cost nothing and keeps two workers from answering the
  same question twice.

Nothing here writes a message. A draft is a row a human can read; sending stays where it already
is, on ``POST .../messages/`` behind ``tickets.comment`` (ADR-002).
"""

from __future__ import annotations

from uuid import UUID

from django.db.models import F
from django.utils import timezone

from apps.ai_assistant.models import (
    ERROR_CLASS_MAX,
    MODEL_MAX,
    PROVIDER_MAX,
    ReplyDraft,
    TicketClassification,
)
from apps.ai_assistant.prompts import DRAFT_PROMPT_VERSION
from apps.ai_assistant.providers import Completion
from apps.ai_assistant.schemas import Draft
from apps.ai_assistant.sources import Source
from apps.common.models import TaskStatus
from apps.common.tasking import enqueue
from apps.organizations.services import WorkspaceAccess
from apps.tickets.models import Ticket
from apps.tickets.services import get_ticket

IN_FLIGHT = (TaskStatus.PENDING, TaskStatus.RUNNING)


class DraftNotFound(LookupError):
    """A task ran with an id that no row holds."""


def request_draft(*, access: WorkspaceAccess, ticket_id: UUID) -> ReplyDraft:
    """Queue a draft for the ticket's current version, or return the one already running.

    The ticket is resolved through the tenant-scoped ticket service first, so a foreign id is a
    404 before any row is written. The workspace is copied from that ticket, never accepted as
    an argument.
    """
    ticket = get_ticket(access=access, ticket_id=ticket_id)

    existing = (
        ReplyDraft.objects.filter(
            ticket=ticket,
            ticket_version=ticket.version,
            status__in=IN_FLIGHT,
        )
        .order_by("-created_at")
        .first()
    )
    if existing is not None:
        return existing

    job = ReplyDraft.objects.create(
        workspace_id=ticket.workspace_id,
        ticket=ticket,
        ticket_version=ticket.version,
        prompt_version=DRAFT_PROMPT_VERSION,
    )

    # Imported here because `tasks` imports this module for its claim helpers.
    from apps.ai_assistant.tasks import draft_reply

    enqueue(draft_reply, str(job.pk))
    return job


def claim_draft(draft_id: str | UUID) -> ReplyDraft | None:
    """Load and claim a draft for execution, or ``None`` when it must not run."""
    job = ReplyDraft.objects.filter(pk=draft_id).first()
    if job is None:
        raise DraftNotFound(f"No AI draft with id {draft_id}.")

    claimed = ReplyDraft.objects.filter(
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


def succeed_draft(
    job: ReplyDraft,
    *,
    completion: Completion,
    draft: Draft,
    sources: list[Source],
) -> None:
    """Store the validated text and the sources it may cite, resolved to titles.

    Only identifiers and titles are kept: a citation the reader cannot open is not a citation,
    and copying article bodies into the draft row would duplicate the knowledge base.
    """
    by_id = {source.id: source for source in sources}
    cited = [
        {"article_id": by_id[source_id].id, "title": by_id[source_id].title}
        for source_id in draft.source_ids
    ]
    ReplyDraft.objects.filter(pk=job.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        provider=completion.provider[:PROVIDER_MAX],
        model=completion.model[:MODEL_MAX],
        latency_ms=completion.latency_ms,
        draft_text=draft.text,
        source_articles=cited,
        last_error="",
    )
    job.refresh_from_db()


def fail_draft(job: ReplyDraft, error: BaseException) -> None:
    """Record the failed attempt by exception class only."""
    ReplyDraft.objects.filter(pk=job.pk).update(
        status=TaskStatus.FAILED,
        finished_at=timezone.now(),
        last_error=type(error).__name__[:ERROR_CLASS_MAX],
    )
    job.refresh_from_db()


def supersede_draft(job: ReplyDraft) -> None:
    """Finish a draft whose ticket changed before a worker reached it."""
    ReplyDraft.objects.filter(pk=job.pk).update(
        status=TaskStatus.SUCCEEDED,
        finished_at=timezone.now(),
        last_error="",
    )
    job.refresh_from_db()


def latest_draft(ticket: Ticket) -> ReplyDraft | None:
    """The newest draft for a ticket, whatever its state."""
    return ReplyDraft.objects.filter(ticket=ticket).order_by("-created_at", "id").first()


def latest_classification(ticket: Ticket) -> TicketClassification | None:
    """The newest classification for a ticket, whatever its state."""
    return TicketClassification.objects.filter(ticket=ticket).order_by("-created_at", "id").first()
