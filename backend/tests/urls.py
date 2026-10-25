"""Test-only URLconf.

The paginator and the unhandled-error path have no product endpoint yet, so they
are exercised through routes that exist only for tests.
"""

from __future__ import annotations

from django.http import HttpRequest
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from apps.common.pagination import BoundedPageNumberPagination

PROBE_ITEM_COUNT = 150


class PaginationProbeView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    def get(self, request):  # type: ignore[no-untyped-def]
        paginator = BoundedPageNumberPagination()
        page = paginator.paginate_queryset(list(range(PROBE_ITEM_COUNT)), request, view=self)
        return paginator.get_paginated_response(page)


def boom(request: HttpRequest):  # type: ignore[no-untyped-def]
    raise RuntimeError("boom-should-never-reach-the-client")


# Django resolves error handlers from the active URLconf, so the test URLconf
# must declare them for the 500 path to reach our JSON handler.
handler404 = "apps.common.errors.handler404"
handler500 = "apps.common.errors.handler500"

urlpatterns = [
    path("test-pagination/", PaginationProbeView.as_view(), name="test-pagination"),
    path("test-boom/", boom, name="test-boom"),
]
