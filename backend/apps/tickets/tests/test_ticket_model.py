from __future__ import annotations

import uuid

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.tests.factories import WorkspaceFactory
from apps.tickets.models import (
    MessageVisibility,
    Ticket,
    TicketEvent,
    TicketEventType,
    TicketMessage,
    TicketPriority,
    TicketStatus,
)
from apps.tickets.tests.factories import TicketFactory, TicketMessageFactory

pytestmark = pytest.mark.django_db


def test_a_new_ticket_is_open_normal_and_unassigned() -> None:
    ticket = TicketFactory.create()

    assert ticket.status == TicketStatus.OPEN
    assert ticket.priority == TicketPriority.NORMAL
    assert ticket.version == 1
    assert ticket.assignee_id is None
    assert ticket.requester_user_id is None
    assert ticket.category == ""
    assert ticket.requester_name == ""


def test_the_requester_email_is_stored_trimmed_and_lowercased() -> None:
    ticket = TicketFactory.create(requester_email="  Customer@Example.COM ")

    ticket.refresh_from_db()
    assert ticket.requester_email == "customer@example.com"


def test_a_ticket_has_no_team_column() -> None:
    field_names = {field.name for field in Ticket._meta.get_fields()}

    assert "team" not in field_names
    assert "team_id" not in field_names


def test_an_unknown_status_cannot_be_written() -> None:
    ticket = TicketFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Ticket.objects.filter(pk=ticket.pk).update(status="archived")


def test_an_unknown_priority_cannot_be_written() -> None:
    ticket = TicketFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Ticket.objects.filter(pk=ticket.pk).update(priority="critical")


def test_a_non_positive_version_cannot_be_written() -> None:
    ticket = TicketFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Ticket.objects.filter(pk=ticket.pk).update(version=0)


def test_an_empty_message_body_cannot_be_written() -> None:
    message = TicketMessageFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        TicketMessage.objects.filter(pk=message.pk).update(body="")


def test_an_unknown_message_visibility_cannot_be_written() -> None:
    message = TicketMessageFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        TicketMessage.objects.filter(pk=message.pk).update(visibility="whisper")


def test_a_public_reply_and_an_internal_note_are_distinct_rows() -> None:
    ticket = TicketFactory.create()

    TicketMessageFactory.create(ticket=ticket, visibility=MessageVisibility.PUBLIC_REPLY)
    TicketMessageFactory.create(ticket=ticket, visibility=MessageVisibility.INTERNAL_NOTE)

    visibilities = list(
        TicketMessage.objects.filter(ticket=ticket)
        .order_by("created_at", "id")
        .values_list("visibility", flat=True)
    )
    assert visibilities == [
        MessageVisibility.PUBLIC_REPLY.value,
        MessageVisibility.INTERNAL_NOTE.value,
    ]


def test_an_unknown_event_type_cannot_be_written() -> None:
    event = TicketEvent.objects.create(
        workspace=WorkspaceFactory.create(),
        object_id=uuid.uuid4(),
        event_type=TicketEventType.CREATED,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        TicketEvent.objects.filter(pk=event.pk).update(event_type="ticket.exploded")


def test_tickets_are_ordered_by_latest_activity() -> None:
    workspace = WorkspaceFactory.create()
    older = TicketFactory.create(workspace=workspace)
    newer = TicketFactory.create(workspace=workspace)

    Ticket.objects.filter(pk=newer.pk).update(updated_at=timezone.now())

    assert list(Ticket.objects.filter(workspace=workspace)) == [newer, older]
