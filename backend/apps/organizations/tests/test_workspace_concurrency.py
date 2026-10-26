"""Concurrency behaviour of workspace creation.

The unique slug cannot be reserved by a check: two requests can both pass the
serializer's uniqueness validation, then race to insert. These tests pin both
halves of the fix — the request-level mapping and the database being the
authority — because the serializer check alone would make that race a 500.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connections
from rest_framework.validators import UniqueValidator

from apps.accounts.models import User
from apps.accounts.tests.factories import DEFAULT_PASSWORD, UserFactory
from apps.organizations.exceptions import WorkspaceSlugTaken
from apps.organizations.models import Membership, Workspace
from apps.organizations.services import create_workspace
from apps.organizations.tests.factories import WorkspaceFactory
from tests.support import CsrfClient, login

pytestmark = pytest.mark.django_db

WORKSPACES = "/api/v1/workspaces/"


def test_a_slug_taken_after_validation_is_a_validation_error(
    csrf_client: CsrfClient, agent_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate the race window: the slug is claimed after this request validated."""
    WorkspaceFactory.create(slug="taken")
    login(csrf_client, email=agent_user.email, password=DEFAULT_PASSWORD)

    # Drop the pre-check so the request reaches the insert, which is where two
    # racing requests actually collide.
    monkeypatch.setattr(
        UniqueValidator, "__call__", lambda self, value, serializer_field=None: value
    )

    response = csrf_client.post_json(WORKSPACES, {"name": "Acme", "slug": "taken"})

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "slug" in error["details"]
    # The failure rolled the whole transaction back: no half-written workspace and
    # no orphaned owner membership.
    assert Workspace.objects.filter(slug="taken").count() == 1
    assert not Membership.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_creates_with_one_slug_leave_one_workspace() -> None:
    owner = UserFactory.create()
    barrier = threading.Barrier(2)
    created: list[Workspace] = []
    rejected: list[WorkspaceSlugTaken] = []
    record_lock = threading.Lock()

    def attempt() -> None:
        try:
            # Both threads enter at the same moment, so the loser hits the unique
            # constraint rather than the serializer's pre-check.
            barrier.wait(timeout=10)
            workspace = create_workspace(name="Acme", slug="acme", owner=owner)
            with record_lock:
                created.append(workspace)
        except WorkspaceSlugTaken as exc:
            with record_lock:
                rejected.append(exc)
        finally:
            # Each thread owns its own connection; close it before exiting.
            connections.close_all()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert len(created) == 1
    assert len(rejected) == 1
    assert Workspace.objects.filter(slug="acme").count() == 1
    assert (
        Membership.objects.filter(
            workspace__slug="acme",
            user=owner,
        ).count()
        == 1
    )
