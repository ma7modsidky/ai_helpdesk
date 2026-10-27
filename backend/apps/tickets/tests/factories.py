"""Factories for ticket tests.

A ticket needs a workspace and a requester address; a message needs an author
account. Defaults are the least surprising values, so a test that cares about a
role, status, or visibility asks for it explicitly.
"""

from __future__ import annotations

import factory
from factory.declarations import Sequence, SubFactory

from apps.accounts.tests.factories import UserFactory
from apps.organizations.tests.factories import WorkspaceFactory
from apps.tickets.models import MessageVisibility, Ticket, TicketMessage, TicketStatus


class TicketFactory(factory.django.DjangoModelFactory[Ticket]):
    class Meta:
        model = Ticket

    workspace = SubFactory(WorkspaceFactory)  # type: ignore[no-untyped-call]
    subject = Sequence(lambda index: f"Ticket {index}")  # type: ignore[no-untyped-call]
    description = "The customer cannot sign in."
    requester_email = Sequence(  # type: ignore[no-untyped-call]
        lambda index: f"customer{index}@example.com"
    )
    status = TicketStatus.OPEN


class TicketMessageFactory(factory.django.DjangoModelFactory[TicketMessage]):
    class Meta:
        model = TicketMessage

    ticket = SubFactory(TicketFactory)  # type: ignore[no-untyped-call]
    author = SubFactory(UserFactory)  # type: ignore[no-untyped-call]
    body = "Thanks for reaching out."
    visibility = MessageVisibility.PUBLIC_REPLY
