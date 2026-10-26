"""Consistent API error envelope.

Every DRF error and every unhandled Django error is returned as::

    {"error": {"code": "...", "message": "...", "request_id": "...", "details": {...}}}

``request_id`` is the same value the middleware echoes in the ``X-Request-ID``
response header, so a user-visible error can be matched to a log line.

Messages are deliberately stable and generic: they must not reveal whether
another tenant's object exists, and they never include exception text, SQL,
stack traces, or provider responses. ``details`` is populated only for request
validation errors, where the content is derived from the caller's own input.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, JsonResponse
from rest_framework import exceptions, status
from rest_framework.views import exception_handler as drf_exception_handler

from apps.common.logging import REQUEST_ID_ABSENT

_VALIDATION_MESSAGE = "The request was invalid."
_CSRF_MESSAGE = (
    "CSRF verification failed. Fetch a token from /api/v1/auth/csrf/ "
    "and send it as the X-CSRFToken header."
)

# status code -> (code, message). Anything not listed falls back to a generic error.
_DEFAULTS: dict[int, tuple[str, str]] = {
    status.HTTP_400_BAD_REQUEST: ("invalid_request", "The request could not be processed."),
    status.HTTP_401_UNAUTHORIZED: (
        "not_authenticated",
        "Authentication credentials were not provided.",
    ),
    status.HTTP_403_FORBIDDEN: ("permission_denied", "You do not have access to this resource."),
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: (
        "unsupported_media_type",
        "Content-Type must be application/json.",
    ),
    status.HTTP_404_NOT_FOUND: ("not_found", "The requested resource was not found."),
    status.HTTP_405_METHOD_NOT_ALLOWED: ("method_not_allowed", "Method not allowed."),
    status.HTTP_409_CONFLICT: ("conflict", "The request conflicts with the current state."),
    status.HTTP_429_TOO_MANY_REQUESTS: ("throttled", "Too many requests. Try again later."),
    status.HTTP_500_INTERNAL_SERVER_ERROR: ("internal_error", "An unexpected error occurred."),
    status.HTTP_503_SERVICE_UNAVAILABLE: (
        "service_unavailable",
        "The service is temporarily unavailable.",
    ),
}


class CsrfFailure(exceptions.APIException):
    """Raised when a state-changing request arrives without a valid CSRF token."""

    status_code = status.HTTP_403_FORBIDDEN
    default_detail = _CSRF_MESSAGE
    default_code = "csrf_failed"


class Conflict(exceptions.APIException):
    """409 for a state conflict the client can resolve by re-reading the object."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with the current state."
    default_code = "conflict"


class InvitationExpiredError(exceptions.APIException):
    """409 with a distinct code, so an expired invite is not confused with other conflicts."""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "This invitation has expired."
    default_code = "invitation_expired"


def request_id_for(request: HttpRequest | None) -> str:
    """Return the correlation ID bound by the request middleware."""
    return getattr(request, "request_id", None) or REQUEST_ID_ABSENT


def build_error(
    *,
    code: str,
    message: str,
    request_id: str,
    details: Any | None = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": request_id}
    if details:
        error["details"] = details
    return {"error": error}


def error_response(
    *,
    request: HttpRequest | None,
    status_code: int,
    code: str | None = None,
    message: str | None = None,
    details: Any | None = None,
) -> JsonResponse:
    default_code, default_message = _DEFAULTS.get(
        status_code, ("error", "The request could not be processed.")
    )
    payload = build_error(
        code=code or default_code,
        message=message or default_message,
        request_id=request_id_for(request),
        details=details,
    )
    return JsonResponse(payload, status=status_code)


def _as_json_safe(value: Any) -> Any:
    """Convert DRF ``ErrorDetail`` structures into plain JSON data."""
    if isinstance(value, dict):
        return {str(key): _as_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_as_json_safe(item) for item in value]
    return str(value)


def _code_and_message(exc: Exception, status_code: int) -> tuple[str, str]:
    default_code, default_message = _DEFAULTS.get(
        status_code, ("error", "The request could not be processed.")
    )

    if isinstance(exc, exceptions.ValidationError):
        return "validation_error", _VALIDATION_MESSAGE
    if isinstance(exc, CsrfFailure):
        return exc.default_code, str(exc.detail)
    if isinstance(exc, exceptions.NotAuthenticated):
        return "not_authenticated", str(exc.detail)
    if isinstance(exc, exceptions.AuthenticationFailed):
        return "authentication_failed", str(exc.detail)
    if isinstance(exc, exceptions.Throttled):
        return "throttled", default_message
    if isinstance(exc, InvitationExpiredError):
        # A distinct code lets the invitee UI say "ask for a new invitation"
        # instead of treating every conflict as a generic state clash.
        return exc.default_code, str(exc.detail)
    if isinstance(exc, exceptions.PermissionDenied):
        # Generic on purpose: object-level denials must not describe the object.
        return "permission_denied", default_message

    return default_code, default_message


def exception_handler(exc: Exception, context: dict[str, Any]) -> Any:
    """DRF exception handler that rewrites every error into the envelope."""
    response = drf_exception_handler(exc, context)
    if response is None:
        # Not a DRF-handled error: fall through so Django renders handler500 and
        # the request middleware logs the traceback. Never expose it to the client.
        return None

    details = None
    if isinstance(exc, exceptions.ValidationError):
        details = _as_json_safe(exc.detail)

    code, message = _code_and_message(exc, response.status_code)
    response.data = build_error(
        code=code,
        message=message,
        request_id=request_id_for(context.get("request")),
        details=details,
    )
    return response


def handler404(request: HttpRequest, exception: Exception | None = None) -> JsonResponse:
    """JSON 404 for URLs that never reached a view."""
    return error_response(request=request, status_code=status.HTTP_404_NOT_FOUND)


def handler500(request: HttpRequest) -> JsonResponse:
    """JSON 500 without stack traces or exception text."""
    return error_response(request=request, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
