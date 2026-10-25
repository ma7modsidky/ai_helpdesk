from __future__ import annotations

import uuid

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.organizations.exceptions import InsufficientRole, WorkspaceNotFound
from apps.organizations.models import (
    MembershipRole,
    MembershipStatus,
    WorkspaceStatus,
)
from apps.organizations.services import (
    accessible_workspaces,
    has_role_at_least,
    require_role,
    resolve_workspace_access,
)
from apps.organizations.tests.factories import (
    MembershipFactory,
    WorkspaceFactory,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("role", MembershipRole.values)
def test_a_member_resolves_their_own_workspace(role: str) -> None:
    membership = MembershipFactory.create(role=role)

    access = resolve_workspace_access(user=membership.user, workspace_id=membership.workspace_id)

    assert access.workspace == membership.workspace
    assert access.membership == membership


def test_an_unknown_workspace_is_not_found() -> None:
    user = UserFactory.create()

    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_access(user=user, workspace_id=uuid.uuid4())


def test_a_non_member_cannot_resolve_another_workspace() -> None:
    insider = UserFactory.create()
    own = MembershipFactory.create(user=insider)
    outsider = MembershipFactory.create()

    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_access(user=insider, workspace_id=outsider.workspace_id)

    # The same user still reaches the workspace they do belong to.
    assert resolve_workspace_access(user=insider, workspace_id=own.workspace_id).workspace == (
        own.workspace
    )


def test_a_removed_membership_loses_access() -> None:
    membership = MembershipFactory.create()

    membership.status = MembershipStatus.REMOVED
    membership.save(update_fields=["status"])

    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_access(user=membership.user, workspace_id=membership.workspace_id)


def test_an_archived_workspace_is_not_resolvable() -> None:
    membership = MembershipFactory.create(
        workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED)
    )

    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_access(user=membership.user, workspace_id=membership.workspace_id)


def test_a_deactivated_user_loses_access() -> None:
    membership = MembershipFactory.create()
    user = membership.user
    user.is_active = False
    user.save(update_fields=["is_active"])

    with pytest.raises(WorkspaceNotFound):
        resolve_workspace_access(user=user, workspace_id=membership.workspace_id)


def test_the_error_does_not_reveal_which_workspace_was_refused() -> None:
    workspace = WorkspaceFactory.create(name="Acme Support", slug="acme-support")
    stranger = UserFactory.create()

    with pytest.raises(WorkspaceNotFound) as refusal:
        resolve_workspace_access(user=stranger, workspace_id=workspace.id)

    message = str(refusal.value)
    assert "Acme Support" not in message
    assert "acme-support" not in message


def test_require_role_accepts_a_sufficient_role() -> None:
    membership = MembershipFactory.create(role=MembershipRole.OWNER)

    access = require_role(
        user=membership.user,
        workspace_id=membership.workspace_id,
        minimum=MembershipRole.MANAGER,
    )

    assert access.membership == membership


def test_require_role_refuses_an_insufficient_role() -> None:
    membership = MembershipFactory.create(role=MembershipRole.AGENT)

    with pytest.raises(InsufficientRole) as refusal:
        require_role(
            user=membership.user,
            workspace_id=membership.workspace_id,
            minimum=MembershipRole.MANAGER,
        )

    assert refusal.value.required == MembershipRole.MANAGER
    assert membership.role not in str(refusal.value)


def test_require_role_still_hides_a_foreign_workspace() -> None:
    outsider = MembershipFactory.create()

    with pytest.raises(WorkspaceNotFound):
        require_role(
            user=UserFactory.create(),
            workspace_id=outsider.workspace_id,
            minimum=MembershipRole.AGENT,
        )


@pytest.mark.parametrize(
    ("role", "minimum", "allowed"),
    [
        (MembershipRole.OWNER, MembershipRole.OWNER, True),
        (MembershipRole.OWNER, MembershipRole.ADMIN, True),
        (MembershipRole.OWNER, MembershipRole.MANAGER, True),
        (MembershipRole.OWNER, MembershipRole.AGENT, True),
        (MembershipRole.ADMIN, MembershipRole.OWNER, False),
        (MembershipRole.ADMIN, MembershipRole.ADMIN, True),
        (MembershipRole.ADMIN, MembershipRole.MANAGER, True),
        (MembershipRole.ADMIN, MembershipRole.AGENT, True),
        (MembershipRole.MANAGER, MembershipRole.OWNER, False),
        (MembershipRole.MANAGER, MembershipRole.ADMIN, False),
        (MembershipRole.MANAGER, MembershipRole.MANAGER, True),
        (MembershipRole.MANAGER, MembershipRole.AGENT, True),
        (MembershipRole.AGENT, MembershipRole.OWNER, False),
        (MembershipRole.AGENT, MembershipRole.ADMIN, False),
        (MembershipRole.AGENT, MembershipRole.MANAGER, False),
        (MembershipRole.AGENT, MembershipRole.AGENT, True),
    ],
)
def test_role_hierarchy_matches_the_documented_matrix(
    role: str, minimum: str, allowed: bool
) -> None:
    membership = MembershipFactory.build(role=role)

    assert has_role_at_least(membership, MembershipRole(minimum)) is allowed


def test_an_unknown_stored_role_is_never_treated_as_privileged() -> None:
    membership = MembershipFactory.build(role="superuser")

    with pytest.raises(ValueError, match="Unknown membership role"):
        has_role_at_least(membership, MembershipRole.AGENT)


def test_accessible_workspaces_returns_only_active_memberships() -> None:
    user = UserFactory.create()
    first = MembershipFactory.create(user=user)
    second = MembershipFactory.create(user=user)
    removed = MembershipFactory.create(user=user, status=MembershipStatus.REMOVED)

    workspaces = accessible_workspaces(user)

    assert set(workspaces.values_list("id", flat=True)) == {
        first.workspace_id,
        second.workspace_id,
    }
    assert removed.workspace_id not in workspaces.values_list("id", flat=True)


def test_accessible_workspaces_excludes_archived_workspaces() -> None:
    user = UserFactory.create()
    active = MembershipFactory.create(user=user)
    archived = MembershipFactory.create(
        user=user, workspace=WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED)
    )

    workspaces = accessible_workspaces(user)

    assert list(workspaces.values_list("id", flat=True)) == [active.workspace_id]
    assert archived.workspace_id not in workspaces.values_list("id", flat=True)


def test_accessible_workspaces_never_includes_another_tenant() -> None:
    user = UserFactory.create()
    own = MembershipFactory.create(user=user)
    foreign = MembershipFactory.create()

    workspaces = accessible_workspaces(user)

    assert list(workspaces.values_list("id", flat=True)) == [own.workspace_id]
    assert foreign.workspace_id not in workspaces.values_list("id", flat=True)


def test_accessible_workspaces_is_empty_for_a_user_without_memberships() -> None:
    assert not accessible_workspaces(UserFactory.create()).exists()
