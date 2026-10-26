"""Two simultaneous handovers must not leave a workspace without an owner.

``transaction=True`` is required: each thread needs its own committed connection,
which the default test transaction would hide.
"""

from __future__ import annotations

import threading

import pytest
from django.db import connections

from apps.accounts.tests.factories import UserFactory
from apps.organizations.exceptions import InsufficientRole
from apps.organizations.models import Membership, MembershipRole, MembershipStatus
from apps.organizations.services import resolve_workspace_access, transfer_ownership
from apps.organizations.tests.factories import MembershipFactory, WorkspaceFactory


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_transfers_leave_exactly_one_owner() -> None:
    workspace = WorkspaceFactory.create()
    owner = MembershipFactory.create(workspace=workspace, role=MembershipRole.OWNER)
    heirs = [
        MembershipFactory.create(
            workspace=workspace, user=UserFactory.create(email=f"heir{index}@example.com")
        )
        for index in range(2)
    ]

    barrier = threading.Barrier(len(heirs))
    successes: list[str] = []
    refusals: list[Exception] = []
    record_lock = threading.Lock()

    def hand_over(target: Membership) -> None:
        try:
            access = resolve_workspace_access(user=owner.user, workspace_id=workspace.id)
            # Both requests authorize while the caller is still the owner, then race.
            barrier.wait(timeout=10)
            transfer_ownership(access=access, membership_id=target.id)
            with record_lock:
                successes.append(str(target.id))
        except InsufficientRole as exc:
            with record_lock:
                refusals.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=hand_over, args=(heir,)) for heir in heirs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not any(thread.is_alive() for thread in threads)
    assert len(successes) == 1
    assert len(refusals) == 1

    # Exactly one owner remains, and the caller has stepped down.
    assert (
        Membership.objects.filter(
            workspace=workspace,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
        ).count()
        == 1
    )
    owner.refresh_from_db()
    assert owner.role == MembershipRole.ADMIN

    winner = Membership.objects.get(pk=successes[0])
    loser = next(heir for heir in heirs if str(heir.id) != successes[0])
    assert winner.role == MembershipRole.OWNER
    loser.refresh_from_db()
    assert loser.role == MembershipRole.AGENT
