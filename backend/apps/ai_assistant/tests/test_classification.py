"""The classification job end to end: dispatch, claims, and recorded outcomes (T6.2).

Every test runs with ``CELERY_TASK_ALWAYS_EAGER`` on and a scripted fake provider, so the suite
proves the whole path — queue, claim, prompt, parse, persist — without a broker, a worker, or a
vendor key. The provider is the only thing replaced; nothing else is mocked.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from celery.exceptions import Retry

from apps.accounts.tests.factories import UserFactory
from apps.ai_assistant.models import Sentiment, TicketClassification
from apps.ai_assistant.prompts import CLASSIFICATION_PROMPT_VERSION
from apps.ai_assistant.providers import AIProviderTimeout, FakeAIProvider
from apps.ai_assistant.tasks import classify_ticket, request_classification
from apps.common.models import TaskStatus
from apps.organizations.models import MembershipRole
from apps.organizations.services import Capability, require_capability
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory
from apps.tickets.models import Ticket, TicketPriority
from apps.tickets.services import create_ticket
from apps.tickets.tests.factories import TicketFactory

pytestmark = pytest.mark.django_db


def _response(**overrides: Any) -> str:
    payload: dict[str, Any] = {
        "category": "billing",
        "sentiment": "negative",
        "suggested_priority": "high",
        "confidence": 0.82,
        "rationale": "Customer reports a duplicate charge and previous unanswered contacts.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def _use(monkeypatch: pytest.MonkeyPatch, provider: FakeAIProvider) -> FakeAIProvider:
    """Point the task at a scripted provider; everything else stays real."""
    monkeypatch.setattr("apps.ai_assistant.tasks.get_provider", lambda: provider)
    return provider


def _job(
    ticket: Ticket,
    *,
    workspace_id: Any = None,
    ticket_version: int | None = None,
) -> TicketClassification:
    return TicketClassification.objects.create(
        workspace_id=workspace_id or ticket.workspace_id,
        ticket=ticket,
        ticket_version=ticket_version if ticket_version is not None else ticket.version,
        prompt_version=CLASSIFICATION_PROMPT_VERSION,
    )


def test_a_queued_classification_stores_the_validated_answer(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create(requester_email="customer@example.com")
    _use(monkeypatch, FakeAIProvider(responses=(_response(),)))

    with django_capture_on_commit_callbacks(execute=True):
        job = request_classification(ticket)

    assert job is not None
    job.refresh_from_db()
    assert job.status == TaskStatus.SUCCEEDED
    assert job.attempts == 1
    assert job.category == "billing"
    assert job.sentiment == Sentiment.NEGATIVE
    assert job.suggested_priority == TicketPriority.HIGH.value
    assert job.confidence == 0.82
    assert job.rationale.startswith("Customer reports a duplicate charge")
    # Provenance, so a quality question is answered from data rather than from memory.
    assert job.provider == "fake"
    assert job.model == "fake-model-v1"
    assert job.latency_ms is not None
    assert job.prompt_version == CLASSIFICATION_PROMPT_VERSION
    # Tenant scope: copied from the ticket, never passed in by a caller.
    assert job.workspace_id == ticket.workspace_id
    assert job.ticket_version == ticket.version


def test_the_requester_identity_is_not_sent_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create(
        requester_email="customer@example.com",
        requester_name="Dana Customer",
    )
    provider = _use(monkeypatch, FakeAIProvider(responses=(_response(),)))

    with django_capture_on_commit_callbacks(execute=True):
        request_classification(ticket)

    prompt = provider.calls[0].prompt
    assert ticket.subject in prompt
    # Nothing about who asked: it changes no category and is the data most worth withholding.
    assert "customer@example.com" not in prompt
    assert "Dana Customer" not in prompt


def test_one_job_per_ticket_version(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create()
    provider = _use(monkeypatch, FakeAIProvider(responses=(_response(),)))

    with django_capture_on_commit_callbacks(execute=True):
        first = request_classification(ticket)
        second = request_classification(ticket)

    assert first is not None
    assert second is None
    assert TicketClassification.objects.filter(ticket=ticket).count() == 1
    assert len(provider.calls) == 1


def test_an_edited_ticket_gets_its_own_job(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create()
    _use(
        monkeypatch,
        FakeAIProvider(responses=(_response(category="billing"), _response(category="technical"))),
    )

    with django_capture_on_commit_callbacks(execute=True):
        first = request_classification(ticket)
    Ticket.objects.filter(pk=ticket.pk).update(version=ticket.version + 1)
    ticket.refresh_from_db()
    with django_capture_on_commit_callbacks(execute=True):
        second = request_classification(ticket)

    assert first is not None and second is not None
    assert second.pk != first.pk
    # The answer that described the old text is kept, not overwritten: a screen can always tell
    # whether a suggestion is current.
    first.refresh_from_db()
    second.refresh_from_db()
    assert first.category == "billing"
    assert second.category == "technical"


def test_a_duplicate_delivery_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create()
    provider = _use(monkeypatch, FakeAIProvider(responses=(_response(),)))

    with django_capture_on_commit_callbacks(execute=True):
        job = request_classification(ticket)
    assert job is not None

    assert classify_ticket.delay(str(job.pk)).get() == "skipped"

    job.refresh_from_db()
    assert job.attempts == 1
    assert len(provider.calls) == 1


def test_a_superseded_version_is_finished_without_asking_the_model(
    monkeypatch: pytest.MonkeyPatch,
    django_capture_on_commit_callbacks: Any,
) -> None:
    ticket = TicketFactory.create()
    provider = _use(monkeypatch, FakeAIProvider(responses=(_response(),)))

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        job = request_classification(ticket)
    assert job is not None
    Ticket.objects.filter(pk=ticket.pk).update(version=ticket.version + 1)
    for callback in callbacks:
        callback()

    job.refresh_from_db()
    # Terminal, not a retry loop: the newer version has its own job, and classifying text no
    # screen shows would spend quota to produce an answer nobody may read.
    assert job.status == TaskStatus.SUCCEEDED
    assert job.category == ""
    assert provider.calls == []


def test_invalid_output_is_recorded_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = TicketFactory.create()
    _use(monkeypatch, FakeAIProvider(responses=("I think this is about billing.",)))
    job = _job(ticket)

    assert classify_ticket.delay(str(job.pk)).get() == "invalid"

    job.refresh_from_db()
    assert job.status == TaskStatus.FAILED
    assert job.last_error == "AIResponseInvalid"
    # One attempt: the same prompt against the same model fails the same way.
    assert job.attempts == 1


def test_a_transient_failure_is_recorded_and_left_for_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = TicketFactory.create()
    _use(monkeypatch, FakeAIProvider(fail_with=AIProviderTimeout()))
    job = _job(ticket)

    with pytest.raises(Retry):
        classify_ticket.delay(str(job.pk))

    job.refresh_from_db()
    assert job.status == TaskStatus.FAILED
    assert job.last_error == "AIProviderTimeout"
    # `failed` is not final, which is what lets the retry claim the row again.
    assert job.attempts == 1


def test_a_job_is_not_run_against_another_tenants_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticket = TicketFactory.create()
    provider = _use(monkeypatch, FakeAIProvider(responses=(_response(),)))
    # A row whose workspace disagrees with its ticket's, which no code path can write; the
    # worker still refuses to classify across the boundary rather than trusting the message.
    job = _job(ticket, workspace_id=WorkspaceFactory.create().pk)

    assert classify_ticket.delay(str(job.pk)).get() == "superseded"
    assert provider.calls == []


def test_a_ticket_is_created_even_when_the_queue_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = WorkspaceFactory.create()
    user = UserFactory.create()
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.AGENT)
    access = require_capability(
        user=user,
        workspace_id=workspace.pk,
        capability=Capability.TICKETS_CREATE,
    )

    def _unavailable(ticket: Ticket) -> None:
        raise RuntimeError("broker is down")

    monkeypatch.setattr("apps.ai_assistant.tasks.request_classification", _unavailable)

    ticket = create_ticket(
        access=access,
        subject="Cannot sign in",
        description="I keep getting an error.",
        requester_email="customer@example.com",
    )

    # AI is assistive: an outage costs a suggestion, never the ticket.
    assert Ticket.objects.filter(pk=ticket.pk).exists()
    assert not TicketClassification.objects.filter(ticket=ticket).exists()


def test_the_ticket_creation_path_queues_one_classification(
    django_capture_on_commit_callbacks: Any,
) -> None:
    workspace = WorkspaceFactory.create()
    user = UserFactory.create()
    MembershipFactory.create(workspace=workspace, user=user, role=MembershipRole.AGENT)
    access = require_capability(
        user=user,
        workspace_id=workspace.pk,
        capability=Capability.TICKETS_CREATE,
    )

    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        ticket = create_ticket(
            access=access,
            subject="Cannot sign in",
            description="I keep getting an error.",
            requester_email="customer@example.com",
        )

    # One message, published only after commit.
    assert len(callbacks) == 1
    job = TicketClassification.objects.get(ticket=ticket)
    # Queued, not run: creation does not wait for a model.
    assert job.status == TaskStatus.PENDING
    assert job.ticket_version == ticket.version
    assert job.workspace_id == workspace.pk
