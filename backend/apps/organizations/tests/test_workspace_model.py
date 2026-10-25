from __future__ import annotations

import uuid

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.organizations.models import Workspace, WorkspaceStatus
from apps.organizations.tests.factories import WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_primary_key_is_a_uuid() -> None:
    workspace = WorkspaceFactory.create()

    assert isinstance(workspace.pk, uuid.UUID)


def test_defaults_keep_a_new_workspace_active_and_utc() -> None:
    workspace = WorkspaceFactory.create()

    assert workspace.status == WorkspaceStatus.ACTIVE
    assert workspace.timezone == "UTC"
    assert workspace.settings == {}
    assert workspace.created_at is not None


def test_str_is_the_display_name() -> None:
    workspace = WorkspaceFactory.create(name="Acme Support")

    assert str(workspace) == "Acme Support"


def test_slug_is_unique_across_workspaces() -> None:
    WorkspaceFactory.create(slug="acme")

    with pytest.raises(IntegrityError), transaction.atomic():
        WorkspaceFactory.create(slug="acme")


def test_an_archived_workspace_stays_stored() -> None:
    workspace = WorkspaceFactory.create(status=WorkspaceStatus.ARCHIVED)

    assert Workspace.objects.get(pk=workspace.pk).status == "archived"


def test_database_rejects_an_unknown_status() -> None:
    workspace = WorkspaceFactory.create()

    with pytest.raises(IntegrityError), transaction.atomic():
        Workspace.objects.filter(pk=workspace.pk).update(status="deleted")


@pytest.mark.parametrize("timezone", ["UTC", "Europe/Berlin", "America/New_York"])
def test_known_iana_time_zone_passes_validation(timezone: str) -> None:
    workspace = WorkspaceFactory.build(timezone=timezone)

    workspace.full_clean()


@pytest.mark.parametrize("timezone", ["Mars/Olympus", "Europe/Berlinn", "not a zone"])
def test_unknown_time_zone_is_rejected(timezone: str) -> None:
    workspace = WorkspaceFactory.build(timezone=timezone)

    with pytest.raises(ValidationError) as rejection:
        workspace.full_clean()

    assert "timezone" in rejection.value.message_dict
