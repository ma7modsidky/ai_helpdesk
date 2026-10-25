"""Workspace access failures.

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


class LastOwnerRequired(WorkspaceAccessError):
    """The change would leave a workspace with no active owner."""

    def __init__(self) -> None:
        super().__init__("A workspace must keep at least one active owner.")
