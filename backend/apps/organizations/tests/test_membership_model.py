from __future__ import annotations

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import UserFactory
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
)
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
)

pytestmark = pytest.mark.django_db


def test_roles_are_the_documented_four() -> None:
    assert set(MembershipRole.values) == {"owner", "admin", "manager", "agent"}


def test_a_new_membership_is_an_active_agent() -> None:
    membership = MembershipFactory.create()

    assert membership.role == MembershipRole.AGENT
    assert membership.status == MembershipStatus.ACTIVE
    assert membership.created_at is not None


def test_a_user_cannot_hold_two_memberships_in_one_workspace() -> None:
    workspace = WorkspaceFactory.create()
    user = UserFactory.create()
    MembershipFactory.create(workspace=workspace, user=user)

    with pytest.raises(IntegrityError), transaction.atomic():
        MembershipFactory.create(workspace=workspace, user=user)


def test_a_user_can_hold_memberships_in_several_workspaces() -> None:
    user = UserFactory.create()

    first = MembershipFactory.create(user=user)
    second = MembershipFactory.create(user=user)

    assert first.workspace_id != second.workspace_id
    assert Membership.objects.filter(user=user).count() == 2


def test_a_workspace_can_hold_several_users() -> None:
    workspace = WorkspaceFactory.create()

    MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    MembershipFactory.create(workspace=workspace, role=MembershipRole.MANAGER)

    assert workspace.memberships.count() == 2


def test_str_identifies_user_workspace_and_role() -> None:
    membership = MembershipFactory.create(role=MembershipRole.OWNER)

    assert str(membership) == f"{membership.user_id} in {membership.workspace_id} as owner"


def test_a_removed_membership_keeps_its_row() -> None:
    membership = MembershipFactory.create(status=MembershipStatus.REMOVED)

    assert Membership.objects.get(pk=membership.pk).status == "removed"


def test_a_role_must_be_supplied() -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.create(workspace=WorkspaceFactory.create(), user=UserFactory.create())


def test_database_rejects_an_unknown_role() -> None:
    membership = MembershipFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.filter(pk=membership.pk).update(role="superuser")


def test_database_rejects_an_unknown_status() -> None:
    membership = MembershipFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Membership.objects.filter(pk=membership.pk).update(status="pending")


def test_deleting_a_workspace_removes_its_memberships() -> None:
    membership = MembershipFactory.create()

    membership.workspace.delete()

    assert not Membership.objects.filter(pk=membership.pk).exists()


def test_deleting_a_user_removes_their_memberships() -> None:
    membership = MembershipFactory.create()

    membership.user.delete()

    assert not Membership.objects.filter(pk=membership.pk).exists()
