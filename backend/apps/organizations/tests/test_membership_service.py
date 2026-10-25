from __future__ import annotations

import pytest

from apps.organizations.exceptions import InsufficientRole
from apps.organizations.models import MembershipRole
from apps.organizations.services import (
    change_membership,
    resolve_workspace_access,
)
from apps.organizations.tests.factories import MembershipFactory

pytestmark = pytest.mark.django_db


def test_a_member_without_manage_capability_cannot_change_roles() -> None:
    agent = MembershipFactory.create(role=MembershipRole.AGENT)
    target = MembershipFactory.create(workspace=agent.workspace)
    access = resolve_workspace_access(user=agent.user, workspace_id=agent.workspace_id)

    with pytest.raises(InsufficientRole):
        change_membership(
            access=access,
            membership_id=target.id,
            role=MembershipRole.MANAGER,
        )


def test_an_unchanged_update_is_a_no_op() -> None:
    owner = MembershipFactory.create(role=MembershipRole.OWNER)
    target = MembershipFactory.create(workspace=owner.workspace, role=MembershipRole.AGENT)
    access = resolve_workspace_access(user=owner.user, workspace_id=owner.workspace_id)

    result = change_membership(
        access=access,
        membership_id=target.id,
        role=MembershipRole.AGENT,
    )

    assert result == target
    assert result.role == MembershipRole.AGENT
