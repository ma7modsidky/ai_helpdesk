from __future__ import annotations

import pytest

from apps.organizations.exceptions import InsufficientRole, WorkspaceNotFound
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.services import (
    change_membership,
    resolve_workspace_access,
)
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_a_member_without_manage_capability_cannot_change_roles() -> None:
    agent = MembershipFactory.create(role=MembershipRole.AGENT)
    target = MembershipFactory.create(workspace=agent.workspace)
    access = resolve_workspace_access(user=agent.user, workspace_id=agent.workspace_id)

    with pytest.raises(InsufficientRole):
        change_membership(
            access=access,
            membership_id=target.id,
            role=MembershipRole.MANAGER,
        )


def test_a_stale_owner_session_cannot_act_after_being_demoted() -> None:
    workspace = WorkspaceFactory.create()
    demoted = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    other_owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)

    # Resolved while ``demoted`` was still an owner; the service must not trust it.
    stale_access = resolve_workspace_access(user=demoted.user, workspace_id=workspace.id)
    change_membership(
        access=resolve_workspace_access(user=other_owner.user, workspace_id=workspace.id),
        membership_id=demoted.id,
        role=MembershipRole.AGENT,
    )

    with pytest.raises(InsufficientRole):
        change_membership(
            access=stale_access,
            membership_id=target.id,
            role=MembershipRole.MANAGER,
        )


def test_a_workspace_archived_mid_request_is_rechecked() -> None:
    workspace = WorkspaceFactory.create()
    owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)
    stale_access = resolve_workspace_access(user=owner.user, workspace_id=workspace.id)

    Workspace.objects.filter(pk=workspace.pk).update(status=WorkspaceStatus.ARCHIVED)

    with pytest.raises(WorkspaceNotFound):
        change_membership(
            access=stale_access,
            membership_id=target.id,
            role=MembershipRole.MANAGER,
        )


def test_an_actor_removed_mid_request_is_rechecked() -> None:
    workspace = WorkspaceFactory.create()
    owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=workspace)
    stale_access = resolve_workspace_access(user=owner.user, workspace_id=workspace.id)

    Membership.objects.filter(pk=owner.pk).update(status=MembershipStatus.REMOVED)

    with pytest.raises(WorkspaceNotFound):
        change_membership(
            access=stale_access,
            membership_id=target.id,
            role=MembershipRole.MANAGER,
        )


def test_an_unchanged_update_is_a_no_op() -> None:
    owner = MembershipFactory.create(role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=owner.workspace, role=MembershipRole.AGENT)
    access = resolve_workspace_access(user=owner.user, workspace_id=owner.workspace_id)

    result = change_membership(
        access=access,
        membership_id=target.id,
        role=MembershipRole.AGENT,
    )

    assert result == target
    assert result.role == MembershipRole.AGENT
