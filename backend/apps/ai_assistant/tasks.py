"""The classification task and its dispatcher (T6.2).

Ticket creation calls :func:`request_classification`, which writes one job row for the ticket's
current version and publishes the message after the surrounding transaction commits. Creation
never waits for a model: the row is a few milliseconds and the call happens in a worker.

Failure is handled by class, because that is what decides whether another attempt can help:

- a transient provider error (timeout, unavailable, rate limit) is recorded and re-raised, so
  Celery's bounded retry policy applies;
- invalid output is recorded and *not* re-raised: the same prompt against the same model fails
  the same way, so a retry burns quota and delays the operator (05 §6).

Whatever happens, the ticket keeps existing. AI is assistive in MVP and an outage degrades a
suggestion, not the product.
"""

from __future__ import annotations

import logging

from celery import shared_task

from apps.ai_assistant.prompts import (
    CLASSIFICATION_MAX_OUTPUT_TOKENS,
    CLASSIFICATION_PROMPT_VERSION,
    build_classification_prompt,
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
from apps.ai_assistant.schemas import parse_classification
from apps.common.tasking import enqueue
from apps.tickets.models import Ticket

from .models import TicketClassification

logger = logging.getLogger(__name__)

# Bounded like every other task (10_SECURITY): an outage becomes a failed job the operator can
# see and retry, not a message that spins forever.
MAX_CLASSIFICATION_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 30


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
    autoretry_for=(AIProviderTimeout, AIProviderUnavailable, AIProviderRateLimited),
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
