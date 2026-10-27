"""Ticket rules: creation, queries, field edits, commands, messages, audit.

Two properties shape this module. First, a workspace identifier is never trusted:
every function takes a :class:`WorkspaceAccess` that the caller already resolved,
and every query is scoped to that workspace, so a foreign ticket id is simply not
found. Second, the write paths differ on purpose (ADR-022):

* field edits are a conditional ``UPDATE`` comparing ``version``, which detects a
  concurrent edit without holding a lock;
* ``assign`` and ``transition`` lock the ticket row, because they validate
  against the current state before writing, and a report-then-write would race.

Neither path takes the workspace lock, so ticket traffic and membership changes
never wait on each other. Every write appends an audit event in the same
transaction: an operation that changes a ticket but leaves no trace is not
something the security spec allows (``10_SECURITY.md``).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from django.db import transaction
from django.db.models import F, QuerySet
from django.utils import timezone

from apps.organizations.exceptions import InsufficientRole, WorkspaceNotFound
from apps.organizations.models import (
    Membership,
    MembershipRole,
    MembershipStatus,
    Workspace,
    WorkspaceStatus,
)
from apps.organizations.services import (
    Capability,
    WorkspaceAccess,
    has_capability,
    has_role_at_least,
)

from .exceptions import (
    IllegalTransition,
    InvalidAssignee,
    InvalidRequester,
    TicketNotFound,
    TicketVersionConflict,
)
from .models import (
    MessageVisibility,
    Ticket,
    TicketEvent,
    TicketEventType,
    TicketMessage,
    TicketPriority,
    TicketStatus,
    normalize_email,
)

# Fields a client may change with an If-Match edit. Status and assignment are
# deliberately absent: each has its own command, so field edits never have to
# reason about them.
TICKET_EDITABLE_FIELDS: frozenset[str] = frozenset(
    {"subject", "description", "priority", "category", "requester_email", "requester_name"}
)

# Sortable columns. Anything else would sort on an unindexed column and would
# expose the schema, so the allowlist is the contract (ADR-023).
TICKET_ORDERING_FIELDS: tuple[str, ...] = ("created_at", "updated_at", "priority", "status")
DEFAULT_TICKET_ORDERING = "-updated_at"

# ``assignee`` filter values that are not a user id.
ASSIGNEE_ME = "me"
ASSIGNEE_UNASSIGNED = "unassigned"

# ADR-009. Statuses not listed here are terminal or have no outgoing edge.
_ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.OPEN: frozenset(
        {TicketStatus.IN_PROGRESS, TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.RESOLVED}
    ),
    TicketStatus.IN_PROGRESS: frozenset(
        {TicketStatus.WAITING_ON_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.OPEN}
    ),
    TicketStatus.WAITING_ON_CUSTOMER: frozenset(
        {TicketStatus.IN_PROGRESS, TicketStatus.RESOLVED, TicketStatus.OPEN}
    ),
    TicketStatus.RESOLVED: frozenset({TicketStatus.OPEN, TicketStatus.CLOSED}),
    TicketStatus.CLOSED: frozenset(),
}


def _current_actor(access: WorkspaceAccess) -> Membership:
    """Re-read the caller's membership so a revoked session cannot write.

    The access object was resolved when the request started. A membership can be
    revoked, or its workspace archived, before the write commits, so the rule is
    checked again here rather than trusted from the earlier resolution.
    """
    actor = (
        Membership.objects.filter(
            pk=access.membership.pk,
            workspace=access.workspace,
            status=MembershipStatus.ACTIVE,
            workspace__status=WorkspaceStatus.ACTIVE,
        )
        .select_related("workspace")
        .first()
    )
    if actor is None:
        raise WorkspaceNotFound
    return actor


def _is_active_member(workspace: Workspace, user_id: UUID) -> bool:
    """Whether ``user_id`` holds an active membership in ``workspace``."""
    return Membership.objects.filter(
        workspace=workspace,
        user_id=user_id,
        status=MembershipStatus.ACTIVE,
    ).exists()


def record_event(
    *,
    workspace: Workspace,
    actor_id: UUID | None,
    event_type: TicketEventType,
    object_id: UUID,
    metadata: dict[str, str] | None = None,
    correlation_id: str = "",
) -> TicketEvent:
    """Append an audit event.

    Metadata carries identifiers and names only. Message bodies and requester
    contact details must never be copied here: the audit trail outlives the
    content it describes and is read by more people.
    """
    return TicketEvent.objects.create(
        workspace=workspace,
        actor_id=actor_id,
        object_type="ticket",
        object_id=object_id,
        event_type=event_type,
        metadata=metadata or {},
        correlation_id=correlation_id,
    )


def parse_ordering(value: str | None) -> str:
    """Return a validated ordering expression, or raise for an unknown field."""
    candidate = DEFAULT_TICKET_ORDERING if value is None else value
    field = candidate[1:] if candidate.startswith("-") else candidate
    if field not in TICKET_ORDERING_FIELDS:
        raise ValueError(f"Unsupported ticket ordering: {value!r}")
    return candidate


def create_ticket(
    *,
    access: WorkspaceAccess,
    subject: str,
    description: str,
    requester_email: str,
    requester_name: str = "",
    requester_user_id: UUID | None = None,
    priority: str = TicketPriority.NORMAL.value,
    category: str = "",
    correlation_id: str = "",
) -> Ticket:
    """Create an open, unassigned ticket and record its creation.

    ``requester_user_id`` is optional but, when supplied, must name an active
    member of this workspace. The check is one membership lookup and produces the
    same refusal for an unknown account and for a member of another tenant, so the
    field cannot be used to enumerate users.
    """
    with transaction.atomic():
        actor = _current_actor(access)
        if requester_user_id is not None and not _is_active_member(
            access.workspace, requester_user_id
        ):
            raise InvalidRequester

        ticket = Ticket.objects.create(
            workspace=access.workspace,
            subject=subject,
            description=description,
            requester_email=requester_email,
            requester_name=requester_name,
            requester_user_id=requester_user_id,
            priority=priority,
            category=category,
        )
        record_event(
            workspace=access.workspace,
            actor_id=actor.user_id,
            event_type=TicketEventType.CREATED,
            object_id=ticket.pk,
            metadata={"status": ticket.status, "priority": ticket.priority},
            correlation_id=correlation_id,
        )

    return ticket


def get_ticket(*, access: WorkspaceAccess, ticket_id: UUID) -> Ticket:
    """Return one ticket from the caller's workspace, or raise ``TicketNotFound``."""
    ticket = (
        Ticket.objects.filter(workspace=access.workspace, pk=ticket_id)
        .select_related("assignee", "requester_user")
        .first()
    )
    if ticket is None:
        raise TicketNotFound
    return ticket


def list_tickets(
    *,
    access: WorkspaceAccess,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | UUID | None = None,
    search: str | None = None,
    ordering: str | None = None,
) -> QuerySet[Ticket]:
    """Tickets in one workspace, filtered and ordered deterministically.

    ``assignee`` accepts ``me``, ``unassigned``, or a user id. A well-formed id
    that is not a member of this workspace matches nothing rather than being
    rejected, which keeps the filter from answering "does this user exist".
    """
    # Validate the sort before touching the database, so an unsupported column is
    # a rejected request rather than an error from the ORM.
    order_by = parse_ordering(ordering)
    queryset = (
        Ticket.objects.filter(workspace=access.workspace)
        .select_related("assignee", "requester_user")
        .order_by(order_by, "id")
    )

    if status is not None:
        queryset = queryset.filter(status=status)
    if priority is not None:
        queryset = queryset.filter(priority=priority)
    if assignee == ASSIGNEE_ME:
        queryset = queryset.filter(assignee_id=access.membership.user_id)
    elif assignee == ASSIGNEE_UNASSIGNED:
        queryset = queryset.filter(assignee__isnull=True)
    elif isinstance(assignee, UUID):
        queryset = queryset.filter(assignee_id=assignee)
    if search is not None:
        queryset = queryset.filter(subject__icontains=search)

    return queryset


def update_ticket_fields(
    *,
    access: WorkspaceAccess,
    ticket_id: UUID,
    fields: dict[str, Any],
    expected_version: int,
    correlation_id: str = "",
) -> Ticket:
    """Apply a field edit only if the client's version is still current.

    The comparison and the increment are one statement, so two editors cannot both
    succeed: the loser's ``UPDATE`` matches no row and is reported as a conflict
    carrying the version it should reload. A lost update is therefore impossible
    without holding a lock for the duration of a user's think time.
    """
    unknown = set(fields) - TICKET_EDITABLE_FIELDS
    if unknown:
        raise ValueError(f"Fields are not editable: {sorted(unknown)}")
    if not fields:
        raise ValueError("At least one field is required.")

    updates = dict(fields)
    if "requester_email" in updates:
        updates["requester_email"] = normalize_email(str(updates["requester_email"]))

    with transaction.atomic():
        actor = _current_actor(access)
        scoped = Ticket.objects.filter(workspace=access.workspace)
        updated = scoped.filter(pk=ticket_id, version=expected_version).update(
            version=F("version") + 1,
            updated_at=timezone.now(),
            **updates,
        )
        if updated == 0:
            current_version = scoped.filter(pk=ticket_id).values_list("version", flat=True).first()
            if current_version is None:
                raise TicketNotFound
            raise TicketVersionConflict(current_version=current_version)

        ticket = scoped.select_related("assignee", "requester_user").get(pk=ticket_id)
        record_event(
            workspace=access.workspace,
            actor_id=actor.user_id,
            event_type=TicketEventType.UPDATED,
            object_id=ticket.pk,
            metadata={"fields": ",".join(sorted(updates))},
            correlation_id=correlation_id,
        )

    return ticket


def assign_ticket(
    *,
    access: WorkspaceAccess,
    ticket_id: UUID,
    assignee_id: UUID | None,
    correlation_id: str = "",
) -> Ticket:
    """Assign a ticket to an active member, or release it with ``None``.

    Idempotent: assigning the current holder again changes nothing and records no
    event, so a retried request does not inflate the audit trail or the version.
    """
    with transaction.atomic():
        actor = _current_actor(access)
        ticket = (
            Ticket.objects.select_for_update()
            .filter(workspace=access.workspace, pk=ticket_id)
            .first()
        )
        if ticket is None:
            raise TicketNotFound

        if assignee_id is not None and not _is_active_member(access.workspace, assignee_id):
            raise InvalidAssignee

        previous_assignee_id = ticket.assignee_id

        # Agents may claim work and release their own, but moving work to someone
        # else is managerial (ADR-021). The check lives here because it depends on
        # the current assignee as well as the requested one, which a route-level
        # capability cannot see. It runs before the no-op return so "assign it to
        # yourself" refusals do not depend on who currently holds the ticket.
        acts_on_someone_else = (assignee_id is not None and assignee_id != actor.user_id) or (
            assignee_id is None
            and previous_assignee_id is not None
            and previous_assignee_id != actor.user_id
        )
        if acts_on_someone_else and not has_capability(actor, Capability.TICKETS_ASSIGN_OTHERS):
            raise InsufficientRole(required=MembershipRole.MANAGER)

        if previous_assignee_id == assignee_id:
            return ticket

        ticket.assignee_id = assignee_id
        ticket.version += 1
        ticket.save(update_fields=["assignee", "version", "updated_at"])

        metadata: dict[str, str] = {}
        if previous_assignee_id is not None:
            metadata["previous_assignee_id"] = str(previous_assignee_id)
        if assignee_id is not None:
            metadata["assignee_id"] = str(assignee_id)
        record_event(
            workspace=access.workspace,
            actor_id=actor.user_id,
            event_type=(
                TicketEventType.ASSIGNED if assignee_id is not None else TicketEventType.UNASSIGNED
            ),
            object_id=ticket.pk,
            metadata=metadata,
            correlation_id=correlation_id,
        )

    return ticket


def can_transition(*, current: TicketStatus, requested: TicketStatus, actor: Membership) -> bool:
    """Whether ``actor`` may move a ticket between these two statuses.

    Kept pure and public so the rule is testable without HTTP and identical for
    every caller. Reopening a resolved ticket is a managerial act (ADR-009); every
    other legal edge is available to any role that may transition at all.
    """
    if requested not in _ALLOWED_TRANSITIONS[current]:
        return False
    if current is TicketStatus.RESOLVED and requested is TicketStatus.OPEN:
        return has_role_at_least(actor, MembershipRole.MANAGER)
    return True


def transition_ticket(
    *,
    access: WorkspaceAccess,
    ticket_id: UUID,
    status: str,
    correlation_id: str = "",
) -> Ticket:
    """Move a ticket to a new status under a row lock, or refuse the change."""
    with transaction.atomic():
        actor = _current_actor(access)
        ticket = (
            Ticket.objects.select_for_update()
            .filter(workspace=access.workspace, pk=ticket_id)
            .first()
        )
        if ticket is None:
            raise TicketNotFound

        current = TicketStatus(ticket.status)
        requested = TicketStatus(status)
        if not can_transition(current=current, requested=requested, actor=actor):
            raise IllegalTransition(current=current.value, requested=requested.value)

        ticket.status = requested.value
        if requested is TicketStatus.RESOLVED:
            ticket.resolved_at = timezone.now()
        elif current is TicketStatus.RESOLVED and requested is TicketStatus.OPEN:
            # A reopened ticket is unresolved again; keeping the timestamp would
            # report a resolution that no longer holds.
            ticket.resolved_at = None
        ticket.version += 1
        ticket.save(update_fields=["status", "resolved_at", "version", "updated_at"])

        record_event(
            workspace=access.workspace,
            actor_id=actor.user_id,
            event_type=TicketEventType.STATUS_CHANGED,
            object_id=ticket.pk,
            metadata={"from": current.value, "to": requested.value},
            correlation_id=correlation_id,
        )

    return ticket


def list_messages(*, access: WorkspaceAccess, ticket_id: UUID) -> QuerySet[TicketMessage]:
    """Messages on one ticket in the caller's workspace, oldest first.

    Both visibilities are returned: there is no customer-facing reader in MVP, and
    the column exists so adding one is a filter on this queryset, not a migration.
    """
    ticket_exists = Ticket.objects.filter(workspace=access.workspace, pk=ticket_id).exists()
    if not ticket_exists:
        raise TicketNotFound
    return (
        TicketMessage.objects.filter(ticket_id=ticket_id)
        .select_related("author")
        .order_by("created_at", "id")
    )


def add_message(
    *,
    access: WorkspaceAccess,
    ticket_id: UUID,
    body: str,
    visibility: str = MessageVisibility.PUBLIC_REPLY.value,
    correlation_id: str = "",
) -> TicketMessage:
    """Append a reply or note, bumping the ticket's activity but not its version.

    The version is deliberately untouched: a colleague's reply must not make a
    description edit in flight stale (ADR-022). ``updated_at`` does move, because
    it is the inbox's activity signal.
    """
    with transaction.atomic():
        actor = _current_actor(access)
        ticket = (
            Ticket.objects.select_for_update()
            .filter(workspace=access.workspace, pk=ticket_id)
            .first()
        )
        if ticket is None:
            raise TicketNotFound

        message = TicketMessage.objects.create(
            ticket=ticket,
            author_id=actor.user_id,
            body=body,
            visibility=visibility,
        )
        Ticket.objects.filter(pk=ticket.pk).update(updated_at=timezone.now())
        record_event(
            workspace=access.workspace,
            actor_id=actor.user_id,
            event_type=TicketEventType.MESSAGE_ADDED,
            object_id=ticket.pk,
            metadata={"message_id": str(message.pk), "visibility": message.visibility},
            correlation_id=correlation_id,
        )

    return message


def events_for(ticket: Ticket) -> QuerySet[TicketEvent]:
    """Audit trail for one ticket, newest first. Used by tests and future reads."""
    return TicketEvent.objects.filter(
        workspace_id=ticket.workspace_id,
        object_type="ticket",
        object_id=ticket.pk,
    )
