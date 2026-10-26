"""Concurrency behaviour of membership changes.

``transaction=True`` is required: the default pytest-django test runs inside an
uncommitted transaction, so a second thread on another connection could not see
the rows this test creates.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connections

from apps.organizations.exceptions import LastOwnerRequired
from apps.organizations.models import Membership, MembershipRole, MembershipStatus
from apps.organizations.services import change_membership, resolve_workspace_access
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory


@pytest.mark.django_db(transaction=True)
def test_simultaneous_demotions_leave_exactly_one_owner() -> None:
    workspace = WorkspaceFactory.create()
    owners = [
        MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER) for _ in range(2)
    ]

    barrier = threading.Barrier(len(owners))
    successes: list[str] = []
    refusals: list[Exception] = []
    record_lock = threading.Lock()

    def demote_self(membership: Membership) -> None:
        try:
            access = resolve_workspace_access(user=membership.user, workspace_id=workspace.id)
            # Both requests resolve while both users are still owners, then race.
            barrier.wait(timeout=10)
            change_membership(
                access=access,
                membership_id=membership.id,
                role=MembershipRole.AGENT,
            )
            with record_lock:
                successes.append("changed")
        except LastOwnerRequired as exc:
            with record_lock:
                refusals.append(exc)
        finally:
            # Each thread owns its own connection; close it before exiting.
            connections.close_all()

    threads = [threading.Thread(target=demote_self, args=(owner,)) for owner in owners]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert len(successes) == 1
    assert len(refusals) == 1
    assert (
        Membership.objects.filter(
            workspace=workspace,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        ).count()
        == 1
    )
