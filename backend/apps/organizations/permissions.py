"""Endpoint authorization for workspace-scoped routes.

The matrix and the resolution rule live in ``services``; this module only turns
their domain failures into HTTP ones. Non-members get 404 so a foreign workspace
cannot be probed for existence, while a member whose role is too low gets 403.
"""

from __future__ import annotations

from typing import cast

from django.core.exceptions import ImproperlyConfigured
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView

from apps.accounts.models import User

from .exceptions import InsufficientRole, WorkspaceNotFound
from .services import Capability, WorkspaceAccess, require_capability


class HasWorkspaceCapability(BasePermission):
    """Resolve the route's workspace for the caller and enforce a capability.

    Set ``required_capability`` on the view. The resolved access is attached to the
    request so the handler reuses it instead of repeating the lookup, which also
    guarantees the object the handler acts on was authorized.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        capability = getattr(view, "required_capability", None)
        if not isinstance(capability, Capability):
            raise ImproperlyConfigured(f"{type(view).__name__} must declare required_capability.")

        workspace_id = view.kwargs.get("workspace_id")
        if workspace_id is None:
            raise ImproperlyConfigured(
                f"{type(view).__name__} is missing a workspace_id URL kwarg."
            )

        try:
            access = require_capability(
                user=cast(User, request.user),
                workspace_id=workspace_id,
                capability=capability,
            )
        except WorkspaceNotFound as exc:
            # Deliberately identical to a missing workspace.
            raise NotFound("The requested workspace was not found.") from exc
        except InsufficientRole as exc:
            raise PermissionDenied("You do not have access to this resource.") from exc

        request.workspace_access = access  # type: ignore[attr-defined]
        return True


def workspace_access_for(request: Request) -> WorkspaceAccess:
    """Return the access resolved by :class:`HasWorkspaceCapability`."""
    access = getattr(request, "workspace_access", None)
    if not isinstance(access, WorkspaceAccess):
        raise ImproperlyConfigured(
            "Workspace access was not resolved; is HasWorkspaceCapability missing?"
        )
    return access
