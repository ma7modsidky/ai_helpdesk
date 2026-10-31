"""AI tasks and their dispatchers (T6.2, T6.3).

Two jobs share this module because Celery discovers tasks per app, from ``tasks.py``, and both
follow the same failure convention:

- a transient provider error (timeout, unavailable, rate limit) is recorded and re-raised, so
  Celery's bounded retry policy applies;
- invalid output is recorded and *not* re-raised: the same prompt against the same model fails
  the same way, so a retry burns quota and delays the operator (05 §6).

Classification is queued by ticket creation; a draft is queued by a person. Neither ever writes
a ticket field or a message: AI output is a suggestion a human acts on (ADR-002).
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.ai_assistant.drafts import (
    claim_draft,
    fail_draft,
    succeed_draft,
    supersede_draft,
)
from apps.ai_assistant.prompts import (
    CLASSIFICATION_MAX_OUTPUT_TOKENS,
    CLASSIFICATION_PROMPT_VERSION,
    DRAFT_MAX_OUTPUT_TOKENS,
    build_classification_prompt,
    build_draft_prompt,
)
from apps.ai_assistant.providers import (
    AIProviderRateLimited,
    AIProviderTimeout,
    AIProviderUnavailable,
    AIResponseInvalid,
    CompletionRequest,
    get_provider,
)
from apps.ai_assistant.runner import claim, succeed, supersede
from apps.ai_assistant.runner import fail as record_failure
from apps.ai_assistant.schemas import parse_classification, parse_draft
from apps.ai_assistant.sources import candidates_for
from apps.common.tasking import enqueue
from apps.tickets.models import MessageVisibility, Ticket, TicketMessage

from .models import TicketClassification

logger = logging.getLogger(__name__)

# Bounded like every other task (10_SECURITY): an outage becomes a failed job the operator can
# see and retry, not a message that spins forever.
MAX_CLASSIFICATION_ATTEMPTS = 3
MAX_DRAFT_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30

# Only the tail of a conversation is sent: enough to answer the latest turn, small enough that a
# long thread cannot spend the context window or the bill.
DRAFT_CONVERSATION_MESSAGES = 10

_RETRYABLE = (AIProviderTimeout, AIProviderUnavailable, AIProviderRateLimited)


def request_classification(ticket: Ticket) -> TicketClassification | None:
    """Queue one classification for the ticket's current version.

    Returns the job, or ``None`` when this version already has one. ``get_or_create`` closes
    the race itself: if two callers insert at once the loser re-reads the winner's row, so the
    unique constraint decides who queued the work rather than who asked first.

    The workspace is copied from the ticket rather than accepted as an argument — there is no
    way for a caller to file a tenant's job under another tenant.
    """
    job, created = TicketClassification.objects.get_or_create(
        ticket=ticket,
        ticket_version=ticket.version,
        defaults={
            "workspace_id": ticket.workspace_id,
            "prompt_version": CLASSIFICATION_PROMPT_VERSION,
        },
    )
    if not created:
        return None

    enqueue(classify_ticket, str(job.pk))
    return job


@shared_task(
    autoretry_for=_RETRYABLE,
    max_retries=MAX_CLASSIFICATION_ATTEMPTS,
    retry_backoff=RETRY_DELAY_SECONDS,
    retry_jitter=True,
)
def classify_ticket(classification_id: str) -> str:
    """Classify one ticket version, recording the outcome on its job row."""
    job = claim(classification_id)
    if job is None:
        # A redelivered message for work that already succeeded, or one another worker holds.
        logger.info("Task classify_ticket skipped: work already done or in flight.")
        return "skipped"

    # Reloaded with trusted ids and the job's own workspace: the worker authorizes nothing from
    # the message, and a ticket that moved tenant (impossible through the API) is not classified.
    ticket = Ticket.objects.filter(pk=job.ticket_id, workspace_id=job.workspace_id).first()
    if ticket is None or ticket.version != job.ticket_version:
        supersede(job)
        logger.info("Task classify_ticket superseded: ticket %s changed.", job.ticket_id)
        return "superseded"

    try:
        provider = get_provider()
        completion = provider.complete(
            CompletionRequest(
                prompt=build_classification_prompt(
                    subject=ticket.subject,
                    description=ticket.description,
                ),
                model=provider.model,
                max_output_tokens=CLASSIFICATION_MAX_OUTPUT_TOKENS,
            )
        )
        classification = parse_classification(completion.text)
    except AIResponseInvalid as exc:
        record_failure(job, exc)
        # Class only: the response may contain customer text.
        logger.info("Task classify_ticket rejected the model output.")
        return "invalid"
    except Exception as exc:
        # Includes every retryable provider error, which is re-raised so the retry policy
        # applies. Anything unexpected is recorded the same way and then surfaced.
        record_failure(job, exc)
        raise

    succeed(job, completion=completion, classification=classification)
    return "succeeded"


@shared_task(
    autoretry_for=_RETRYABLE,
    max_retries=MAX_DRAFT_ATTEMPTS,
    retry_backoff=RETRY_DELAY_SECONDS,
    retry_jitter=True,
)
def draft_reply(draft_id: str) -> str:
    """Draft a reply for one ticket version, recording the outcome and its citations."""
    job = claim_draft(draft_id)
    if job is None:
        logger.info("Task draft_reply skipped: work already done or in flight.")
        return "skipped"

    ticket = Ticket.objects.filter(pk=job.ticket_id, workspace_id=job.workspace_id).first()
    if ticket is None or ticket.version != job.ticket_version:
        supersede_draft(job)
        logger.info("Task draft_reply superseded: ticket %s changed.", job.ticket_id)
        return "superseded"

    # Retrieval happens before the prompt is built, and its result is both what the model is
    # offered and what the validator accepts: a citation cannot come from anywhere else.
    sources = candidates_for(ticket=ticket)

    try:
        provider = get_provider()
        completion = provider.complete(
            CompletionRequest(
                prompt=build_draft_prompt(
                    subject=ticket.subject,
                    description=ticket.description,
                    conversation=_conversation(ticket),
                    sources=sources,
                ),
                model=provider.model,
                max_output_tokens=DRAFT_MAX_OUTPUT_TOKENS,
            )
        )
        draft = parse_draft(
            completion.text,
            candidate_ids={source.id for source in sources},
        )
    except AIResponseInvalid as exc:
        fail_draft(job, exc)
        logger.info("Task draft_reply rejected the model output.")
        return "invalid"
    except Exception as exc:
        fail_draft(job, exc)
        raise

    succeed_draft(job, completion=completion, draft=draft, sources=sources)
    return "succeeded"


def _conversation(ticket: Ticket) -> list[tuple[str, str]]:
    """The last public replies on a ticket, oldest first.

    Internal notes are excluded on purpose: they are staff commentary written for colleagues,
    and a note that reaches a customer-facing draft would be a leak the reviewer may not catch.
    Public replies are what a customer has already seen (05 §3, 10_SECURITY).
    """
    messages = list(
        TicketMessage.objects.filter(
            ticket=ticket,
            visibility=MessageVisibility.PUBLIC_REPLY,
        ).order_by("-created_at", "-id")[:DRAFT_CONVERSATION_MESSAGES]
    )
    return [
        ("agent" if message.author_id else "customer", message.body)
        for message in reversed(messages)
    ]
