"""Domain failures raised by the ticket services.

The service layer never speaks HTTP: it reports what is wrong with the request or
the current state, and views translate each case into the contract's status code.
Keeping them separate is what lets a management command or a future worker reuse
the same rules.
"""

from __future__ import annotations


class TicketError(Exception):
    """Base class for every refused ticket operation."""


class TicketNotFound(TicketError):
    """No ticket with this id exists in the caller's workspace."""

    def __init__(self) -> None:
        super().__init__("The requested ticket was not found.")


class TicketVersionConflict(TicketError):
    """A field edit was based on a version that is no longer current."""

    def __init__(self, *, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("The ticket changed since it was read.")


class InvalidRequester(TicketError):
    """``requester_user_id`` does not name an active member of this workspace.

    The message is deliberately the same whether the user does not exist or
    belongs to another workspace, so the field cannot be used to probe accounts.
    """

    def __init__(self) -> None:
        super().__init__("The requester must be an active member of this workspace.")


class InvalidAssignee(TicketError):
    """The assignment target is not an active member of this workspace."""

    def __init__(self) -> None:
        super().__init__("The assignee must be an active member of this workspace.")


class IllegalTransition(TicketError):
    """The requested status change is not legal from the ticket's current state."""

    def __init__(self, *, current: str, requested: str) -> None:
        self.current = current
        self.requested = requested
        super().__init__(f"A ticket cannot move from {current} to {requested}.")
