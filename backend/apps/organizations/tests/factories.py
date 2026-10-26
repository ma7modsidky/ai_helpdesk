"""Factories for tenancy tests.

Membership is unique per (workspace, user), so every factory call supplies its own
workspace and user by default; a shared default tenant would make the second call
in a test fail with a constraint error instead of exercising the behavior under
test.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from typing import Any

import factory
from django.utils import timezone
from factory.declarations import LazyFunction, Sequence, SubFactory

from apps.accounts.tests.factories import UserFactory
from apps.organizations.invitations import hash_token
from apps.organizations.models import Invitation, Membership, MembershipRole, Workspace


class WorkspaceFactory(factory.django.DjangoModelFactory[Workspace]):
    class Meta:
        model = Workspace

    # factory_boy declares attributes through untyped descriptors.
    name = Sequence(lambda index: f"Workspace {index}")  # type: ignore[no-untyped-call]
    slug = Sequence(lambda index: f"workspace-{index}")  # type: ignore[no-untyped-call]


class MembershipFactory(factory.django.DjangoModelFactory[Membership]):
    class Meta:
        model = Membership

    workspace = SubFactory(WorkspaceFactory)  # type: ignore[no-untyped-call]
    user = SubFactory(UserFactory)  # type: ignore[no-untyped-call]
    # The least-privileged role: a test that needs more must ask for it.
    role = MembershipRole.AGENT


class InvitationFactory(factory.django.DjangoModelFactory[Invitation]):
    class Meta:
        model = Invitation

    workspace = SubFactory(WorkspaceFactory)  # type: ignore[no-untyped-call]
    email = Sequence(lambda index: f"invitee{index}@example.com")  # type: ignore[no-untyped-call]
    role = MembershipRole.AGENT
    # 64 hex characters, as the real hash is; the raw token is never stored.
    token_hash = Sequence(  # type: ignore[no-untyped-call]
        lambda index: hashlib.sha256(f"factory-token-{index}".encode()).hexdigest()
    )
    expires_at = LazyFunction(lambda: timezone.now() + timedelta(days=7))  # type: ignore[no-untyped-call]


def issued_invitation(
    *,
    workspace: Workspace,
    email: str = "invitee@example.com",
    role: str | MembershipRole = MembershipRole.AGENT,
    **kwargs: Any,
) -> tuple[Invitation, str]:
    """Create an invitation and return the raw token the caller would have sent."""
    token = secrets.token_urlsafe(32)
    invitation = InvitationFactory.create(
        workspace=workspace,
        email=email,
        role=role,
        token_hash=hash_token(token),
        **kwargs,
    )
    return invitation, token
