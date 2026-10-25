from __future__ import annotations

import pytest
from django.test import Client, override_settings

from apps.common.pagination import BoundedPageNumberPagination
from tests.urls import PROBE_ITEM_COUNT

pytestmark = pytest.mark.urls("tests.urls")

URL = "/test-pagination/"


def test_default_page_size_and_envelope(client: Client) -> None:
    payload = client.get(URL).json()

    assert payload["count"] == PROBE_ITEM_COUNT
    assert len(payload["results"]) == 25
    assert payload["previous"] is None
    assert payload["next"] is not None


def test_second_page_continues_the_sequence(client: Client) -> None:
    payload = client.get(URL, {"page": 2}).json()

    assert payload["results"][0] == 25
    assert payload["previous"] is not None


def test_page_size_is_capped_at_the_maximum(client: Client) -> None:
    payload = client.get(URL, {"page_size": 500}).json()

    assert len(payload["results"]) == BoundedPageNumberPagination.max_page_size
    assert payload["count"] == PROBE_ITEM_COUNT


def test_page_size_can_shrink_below_default(client: Client) -> None:
    payload = client.get(URL, {"page_size": 5}).json()

    assert len(payload["results"]) == 5
    assert payload["next"] is not None


def test_page_beyond_the_end_returns_envelope_404(client: Client) -> None:
    response = client.get(URL, {"page": 99})

    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response["X-Request-ID"]


def test_non_numeric_page_size_falls_back_to_the_default(client: Client) -> None:
    # DRF ignores an unparseable page_size and uses the default rather than failing.
    payload = client.get(URL, {"page_size": "lots"}).json()

    assert payload["count"] == PROBE_ITEM_COUNT
    assert len(payload["results"]) == BoundedPageNumberPagination.page_size


def test_probe_route_is_only_reachable_with_the_test_urlconf(client: Client) -> None:
    # Guards the fixtures themselves: the probe must not exist in the product URLconf.
    with override_settings(ROOT_URLCONF="config.urls"):
        assert client.get(URL).status_code == 404
