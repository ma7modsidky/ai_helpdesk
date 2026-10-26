"""Workspace domain failures.

These are domain errors, not HTTP errors: the service that raises them has no
request object and no DRF dependency, so tasks and management commands can reuse
the same rules. The API layer maps ``WorkspaceNotFound`` to 404 and
``InsufficientRole`` to 403, which is also what keeps a cross-tenant miss
indistinguishable from a genuinely missing workspace.
"""

from __future__ import annotations

from .models import MembershipRole


class WorkspaceAccessError(Exception):
    """Base class for every refusal to resolve a workspace."""


class WorkspaceNotFound(WorkspaceAccessError):
    """The workspace is unknown, archived, or invisible to this user.

    One error covers all three cases on purpose: a client must not be able to tell
    "no such workspace" from "that workspace belongs to someone else".
    """

    def __init__(self) -> None:
        super().__init__("The requested workspace was not found.")


class InsufficientRole(WorkspaceAccessError):
    """The user is a member, but their role is below what the operation needs."""

    def __init__(self, *, required: MembershipRole) -> None:
        self.required = required
        super().__init__("Your role in this workspace does not permit this action.")


class MembershipNotFound(WorkspaceAccessError):
    """No such membership in the workspace the caller is authorized for."""

    def __init__(self) -> None:
        super().__init__("The requested membership was not found.")


class WorkspaceSlugTaken(Exception):
    """Another workspace already owns this slug.

    Raised from the unique constraint rather than from a pre-check, because a
    pre-check cannot be trusted: two requests can both pass it and then race to
    insert. Not a ``WorkspaceAccessError`` — this is a conflict on input, not a
    refusal to resolve a workspace.
    """

    def __init__(self) -> None:
        super().__init__("A workspace with this slug already exists.")


class LastOwnerRequired(WorkspaceAccessError):
    """The change would leave a workspace with no active owner."""

    def __init__(self) -> None:
        super().__init__("A workspace must keep at least one active owner.")


class OwnershipTransferError(Exception):
    """Base class for refusals to hand a workspace over.

    Not a ``WorkspaceAccessError``: the caller is authorized, but the requested
    change is not valid input or not valid for the target's state.
    """


class OwnershipTransferToSelf(OwnershipTransferError):
    """The caller already owns the workspace, so there is nothing to hand over."""

    def __init__(self) -> None:
        super().__init__("You already own this workspace.")


class OwnershipTargetNotActive(OwnershipTransferError):
    """The target membership is removed, so it cannot become the owner."""

    def __init__(self) -> None:
        super().__init__("Only an active member can become the workspace owner.")


class InvitationError(Exception):
    """Base class for invitation lifecycle failures.

    Deliberately not a ``WorkspaceAccessError``: an invitation is reached through
    its own token, and these failures describe the state of that invitation rather
    than a refusal to resolve a workspace.
    """


class InvitationNotFound(InvitationError):
    """No invitation matches the token, or the workspace is no longer addressable."""

    def __init__(self) -> None:
        super().__init__("The requested invitation was not found.")


class InvitationExpired(InvitationError):
    """The invitation is still pending but past its expiry."""

    def __init__(self) -> None:
        super().__init__("This invitation has expired.")


class InvitationNotPending(InvitationError):
    """The invitation was already accepted, or was revoked."""

    def __init__(self) -> None:
        super().__init__("This invitation can no longer be used.")


class InvitationAlreadyPending(InvitationError):
    """A live invitation for this address already exists in the workspace."""

    def __init__(self) -> None:
        super().__init__("An invitation for this address is already pending.")


class InvitationRoleNotAllowed(InvitationError):
    """The requested role cannot be granted through an invitation."""

    def __init__(self) -> None:
        super().__init__("An invitation cannot grant the owner role.")


class InvitationEmailTaken(InvitationError):
    """The address already holds an active membership in the workspace."""

    def __init__(self) -> None:
        super().__init__("This address is already a member of this workspace.")


class InvitationEmailMismatch(InvitationError):
    """The signed-in account does not own the invited address."""

    def __init__(self) -> None:
        super().__init__("This invitation was addressed to a different account.")


class MembershipRoleConflict(InvitationError):
    """Accepting would silently change an existing active member's role."""

    def __init__(self) -> None:
        super().__init__("This account already has a different role in this workspace.")
