from __future__ import annotations

import pytest
from django.core.exceptions import ImproperlyConfigured
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.organizations.models import MembershipRole
from apps.organizations.permissions import (
    HasWorkspaceCapability,
    workspace_access_for,
)
from apps.organizations.services import Capability, has_capability
from apps.organizations.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("role", "capability", "allowed"),
    [
        (MembershipRole.OWNER, Capability.MEMBERS_VIEW, True),
        (MembershipRole.OWNER, Capability.MEMBERS_MANAGE, True),
        (MembershipRole.ADMIN, Capability.MEMBERS_VIEW, True),
        (MembershipRole.ADMIN, Capability.MEMBERS_MANAGE, True),
        (MembershipRole.MANAGER, Capability.MEMBERS_VIEW, True),
        (MembershipRole.MANAGER, Capability.MEMBERS_MANAGE, False),
        (MembershipRole.AGENT, Capability.MEMBERS_VIEW, True),
        (MembershipRole.AGENT, Capability.MEMBERS_MANAGE, False),
    ],
)
def test_capability_matrix(role: str, capability: Capability, allowed: bool) -> None:
    membership = MembershipFactory.build(role=role)

    assert has_capability(membership, capability) is allowed


def test_an_unknown_stored_role_grants_nothing() -> None:
    membership = MembershipFactory.build(role="superuser")

    with pytest.raises(ValueError, match="Unknown membership role"):
        has_capability(membership, Capability.MEMBERS_VIEW)


def test_a_view_without_a_declared_capability_is_misconfigured() -> None:
    view = APIView()
    view.kwargs = {"workspace_id": "irrelevant"}

    with pytest.raises(ImproperlyConfigured, match="required_capability"):
        HasWorkspaceCapability().has_permission(_request(), view)


def test_a_view_without_a_workspace_kwarg_is_misconfigured() -> None:
    class _MembersView(APIView):
        required_capability = Capability.MEMBERS_VIEW

    view = _MembersView()
    view.kwargs = {}

    with pytest.raises(ImproperlyConfigured, match="workspace_id"):
        HasWorkspaceCapability().has_permission(_request(), view)


def test_access_must_be_resolved_before_it_is_read() -> None:
    with pytest.raises(ImproperlyConfigured, match="not resolved"):
        workspace_access_for(_request())


def _request() -> Request:
    return Request(APIRequestFactory().get("/"))
