"""Request correlation middleware.

Every request gets a trusted correlation ID: a client-supplied ``X-Request-ID`` is
honoured only when it matches a strict allowlist pattern (so log injection and
oversized headers are rejected), otherwise one is generated. The ID is echoed back
in the response header and attached to every log record for the request.
"""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.common.logging import reset_request_id, set_request_id

REQUEST_ID_HEADER = "X-Request-ID"

_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

logger = logging.getLogger(__name__)


def normalize_request_id(raw: str | None) -> str | None:
    """Return the client ID if it is safe to log and echo, else ``None``."""
    if not raw:
        return None

    candidate = raw.strip()
    if not _PATTERN.fullmatch(candidate):
        return None

    return candidate


class RequestIdMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        request_id = normalize_request_id(request.META.get("HTTP_X_REQUEST_ID"))
        if request_id is None:
            request_id = uuid.uuid4().hex

        request.request_id = request_id
        token = set_request_id(request_id)
        started = time.monotonic()

        try:
            response = self.get_response(request)
        except Exception:
            logger.exception("%s %s -> 500 (unhandled error)", request.method, request.path)
            raise
        else:
            duration_ms = round((time.monotonic() - started) * 1000, 1)
            response[REQUEST_ID_HEADER] = request_id
            logger.info(
                "%s %s -> %s in %sms",
                request.method,
                request.path,
                response.status_code,
                duration_ms,
            )
            return response
        finally:
            reset_request_id(token)
