"""Liveness and readiness probes.

Liveness reports whether the process can serve traffic at all. Readiness reports
whether required dependencies are reachable. Neither endpoint exposes versions,
credentials, connection strings, or exception text.
"""

from __future__ import annotations

import logging

from django.db import connection
from django.http import HttpRequest, JsonResponse

logger = logging.getLogger(__name__)


def liveness(request: HttpRequest) -> JsonResponse:  # noqa: ARG001 - Django view signature
    return JsonResponse({"status": "ok"})


def readiness(request: HttpRequest) -> JsonResponse:  # noqa: ARG001 - Django view signature
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 - readiness must degrade, not raise
        logger.warning("Readiness check failed: database unavailable (%s).", type(exc).__name__)
        return JsonResponse({"status": "unavailable"}, status=503)

    return JsonResponse({"status": "ok"})
