"""Workspace resolution and role authorization.

A workspace identifier is a name, never a credential. Every call here resolves a
membership for the authenticated user before returning a workspace, so a client
that guesses another tenant's UUID learns nothing: unknown, archived, and
foreign workspaces all fail the same way.

The module stays free of HTTP concerns so workers and management commands apply
the same rules as the API. Views translate the failures in
``apps.organizations.exceptions`` into status codes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from apps.accounts.models import User

from .exceptions import (
    InsufficientRole,
    LastOwnerRequired,
    MembershipNotFound,
    WorkspaceNotFound,
    WorkspaceSlugTaken,
)
from .models import Membership, MembershipRole, MembershipStatus, Workspace, WorkspaceStatus

# Ordered privileges, highest last. Roles are comparable only through this table:
# the enum's declaration order is presentation, not authority.
_ROLE_RANK: dict[MembershipRole, int] = {
    MembershipRole.AGENT: 10,
    MembershipRole.MANAGER: 20,
    MembershipRole.ADMIN: 30,
    MembershipRole.OWNER: 40,
}


@dataclass(frozen=True)
class WorkspaceAccess:
    """An authorized relationship between one user and one workspace."""

    workspace: Workspace
    membership: Membership


def membership_role(value: str) -> MembershipRole:
    """Parse a stored role string, failing loudly on an unknown value.

    An unrecognized role can only arrive from a database that bypassed the
    ``CHECK`` constraint. Treating it as a low role silently would be an
    authorization bug, so it raises instead.
    """
    try:
        return MembershipRole(value)
    except ValueError as exc:
        raise ValueError(f"Unknown membership role: {value!r}") from exc


def role_rank(role: str) -> int:
    """Return the privilege rank of a stored role string."""
    return _ROLE_RANK[membership_role(role)]


def has_role_at_least(membership: Membership, minimum: MembershipRole) -> bool:
    """Whether ``membership`` is at or above ``minimum`` in privilege."""
    return role_rank(membership.role) >= role_rank(minimum)


def resolve_workspace_access(*, user: User, workspace_id: UUID) -> WorkspaceAccess:
    """Return the user's active membership in an active workspace, or raise.

    ``WorkspaceNotFound`` covers an unknown id, an archived workspace, a removed
    membership, and a deactivated account, so callers cannot accidentally build
    an existence oracle from distinct errors.
    """
    membership = (
        Membership.objects.select_related("workspace")
        .filter(
            workspace_id=workspace_id,
            user=user,
            status=MembershipStatus.ACTIVE,
            workspace__status=WorkspaceStatus.ACTIVE,
        )
        .first()
    )

    if membership is None or not user.is_active:
        raise WorkspaceNotFound

    return WorkspaceAccess(workspace=membership.workspace, membership=membership)


def require_role(*, user: User, workspace_id: UUID, minimum: MembershipRole) -> WorkspaceAccess:
    """Resolve access and require at least ``minimum`` privilege."""
    access = resolve_workspace_access(user=user, workspace_id=workspace_id)
    if not has_role_at_least(access.membership, minimum):
        raise InsufficientRole(required=minimum)
    return access


def accessible_workspaces(user: User) -> QuerySet[Workspace]:
    """Active workspaces the user may see, for list endpoints and pickers.

    Ordered by the model's default (name, id) so pagination stays deterministic.
    """
    return Workspace.objects.filter(
        status=WorkspaceStatus.ACTIVE,
        memberships__user=user,
        memberships__status=MembershipStatus.ACTIVE,
    ).distinct()


class Capability(StrEnum):
    """Actions the API exposes today, named by the resource they act on.

    Capabilities are added with the endpoints that need them rather than ahead of
    time; a capability no endpoint checks is a permission that was never tested.
    """

    MEMBERS_VIEW = "members.view"
    MEMBERS_MANAGE = "members.manage"


# Managers are deliberately not given member management: changing roles is an
# administrative act, and the MVP has no manager-specific workflow that needs it.
_ROLE_CAPABILITIES: dict[MembershipRole, frozenset[Capability]] = {
    MembershipRole.OWNER: frozenset({Capability.MEMBERS_VIEW, Capability.MEMBERS_MANAGE}),
    MembershipRole.ADMIN: frozenset({Capability.MEMBERS_VIEW, Capability.MEMBERS_MANAGE}),
    MembershipRole.MANAGER: frozenset({Capability.MEMBERS_VIEW}),
    MembershipRole.AGENT: frozenset({Capability.MEMBERS_VIEW}),
}


def has_capability(membership: Membership, capability: Capability) -> bool:
    """Whether this membership's role grants ``capability``."""
    return capability in _ROLE_CAPABILITIES[membership_role(membership.role)]


def require_capability(
    *, user: User, workspace_id: UUID, capability: Capability
) -> WorkspaceAccess:
    """Resolve access and require a capability, for endpoint authorization."""
    access = resolve_workspace_access(user=user, workspace_id=workspace_id)
    if not has_capability(access.membership, capability):
        # Member management is the only capability with a floor, so this names
        # the role that could have performed the action.
        raise InsufficientRole(required=MembershipRole.ADMIN)
    return access


def create_workspace(*, name: str, slug: str, owner: User, timezone: str = "UTC") -> Workspace:
    """Create a workspace and its first owner in one transaction.

    A workspace with no owner would be unreachable through the API, so the two
    rows are never written separately.

    The serializer's uniqueness check runs before this call and cannot be
    trusted on its own: two requests can both pass it and then race to insert,
    and the loser would otherwise get a 500 from the database. The unique
    constraint is the authority, so its violation is translated here; ``slug``
    is the only unique column of a workspace being inserted, and the membership
    written alongside it is for a workspace that did not exist a moment ago, so
    no other constraint can fire on this path. Catching the error outside the
    ``atomic`` block is deliberate: the block must roll back first, and only then
    may the connection be used again.
    """
    try:
        with transaction.atomic():
            workspace = Workspace.objects.create(name=name, slug=slug, timezone=timezone)
            Membership.objects.create(
                workspace=workspace,
                user=owner,
                role=MembershipRole.OWNER,
            )
    except IntegrityError as exc:
        raise WorkspaceSlugTaken from exc
    return workspace


def change_membership(
    *,
    access: WorkspaceAccess,
    membership_id: UUID,
    role: str | None = None,
    status: str | None = None,
) -> Membership:
    """Change a member's role or status under the role hierarchy.

    An admin may manage roles below their own but cannot create peers, touch
    another admin, or act on an owner; only an owner can grant owner. Whatever the
    caller's role, the workspace keeps at least one active owner.

    The workspace row is locked for the duration, so the owner count read here and
    the write it guards cannot interleave with another membership change in the
    same workspace. The caller's own membership is re-read inside that lock: a
    request that resolved as an admin may arrive after that admin was demoted.
    """
    with transaction.atomic():
        # Every membership mutation serialises on the tenant row; that is what turns
        # "at least one owner" from two racy queries into a check-and-write.
        workspace = (
            Workspace.objects.select_for_update()
            .filter(pk=access.workspace.pk, status=WorkspaceStatus.ACTIVE)
            .first()
        )
        if workspace is None:
            raise WorkspaceNotFound

        actor = Membership.objects.filter(
            pk=access.membership.pk,
            workspace=workspace,
            status=MembershipStatus.ACTIVE,
        ).first()
        if actor is None:
            raise WorkspaceNotFound

        actor_role = membership_role(actor.role)
        if not has_capability(actor, Capability.MEMBERS_MANAGE):
            raise InsufficientRole(required=MembershipRole.ADMIN)

        membership = Membership.objects.filter(workspace=workspace, pk=membership_id).first()
        if membership is None:
            raise MembershipNotFound

        target_role = membership_role(membership.role)
        if actor_role is not MembershipRole.OWNER and (
            target_role is MembershipRole.OWNER or role_rank(target_role) >= role_rank(actor_role)
        ):
            raise InsufficientRole(required=MembershipRole.OWNER)

        new_role = membership_role(role) if role is not None else target_role
        if new_role is not target_role and actor_role is not MembershipRole.OWNER:
            if new_role is MembershipRole.OWNER or role_rank(new_role) >= role_rank(actor_role):
                raise InsufficientRole(required=MembershipRole.OWNER)

        new_status = (
            MembershipStatus(status) if status is not None else MembershipStatus(membership.status)
        )
        if new_role is target_role and new_status is MembershipStatus(membership.status):
            return membership

        loses_ownership = target_role is MembershipRole.OWNER and (
            new_role is not MembershipRole.OWNER or new_status is not MembershipStatus.ACTIVE
        )
        if loses_ownership:
            another_owner = (
                Membership.objects.filter(
                    workspace=workspace,
                    role=MembershipRole.OWNER,
                    status=MembershipStatus.ACTIVE,
                )
                .exclude(pk=membership.pk)
                .exists()
            )
            if not another_owner:
                raise LastOwnerRequired

        membership.role = new_role.value
        membership.status = new_status.value
        membership.save(update_fields=["role", "status"])

    return membership
