"""CSRF enforcement for authentication endpoints.

Login and logout are ``csrf_exempt`` DRF views by default, so CSRF must be
checked explicitly. The frontend fetches a token from ``/api/v1/auth/csrf/`` and
sends it as ``X-CSRFToken``; the token cookie itself is httpOnly.
"""

from __future__ import annotations

from rest_framework.authentication import SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request

from apps.common.errors import CsrfFailure


def enforce_csrf(request: Request) -> None:
    """Raise ``CsrfFailure`` unless the request carries a valid CSRF token."""
    try:
        SessionAuthentication().enforce_csrf(request)
    except PermissionDenied as exc:
        raise CsrfFailure() from exc
