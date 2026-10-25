"""Factories for tenancy tests.

Membership is unique per (workspace, user), so every factory call supplies its own
workspace and user by default; a shared default tenant would make the second call
in a test fail with a constraint error instead of exercising the behavior under
test.
"""

from __future__ import annotations

import factory
from factory.declarations import Sequence, SubFactory

from apps.accounts.tests.factories import UserFactory
from apps.organizations.models import Membership, MembershipRole, Workspace


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
