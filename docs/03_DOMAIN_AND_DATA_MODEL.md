# 03 — Domain Model and Data Model

## 1. Core entities

### User
Identity and authentication fields. Avoid storing secrets or external provider tokens in plaintext.

### Workspace
Tenant boundary. Holds name, slug, timezone, settings, and lifecycle state.

### Membership
`workspace`, `user`, `role`, `status`, `created_at`. Unique constraint on `(workspace, user)`. Roles: `owner`, `admin`, `manager`, `agent`. Customer access should be modeled separately if a portal is implemented.

### Team — deferred past MVP
`workspace`, `name`, `description`. Unique name per workspace where appropriate. **Not part of the MVP
schema** (ADR-024): tickets carry `assignee_id` and no `team_id`, and there is no team routing or queue.
Recorded here so the concept is not lost; adding it later is one table plus a nullable `ticket.team_id`.

### Invitation
Issued by an owner or admin to grant a role in a workspace before the invitee has a membership (ADR-026).

- `id` UUID
- `workspace_id` (cascade)
- `email` required, trimmed, lowercased, ≤254 characters
- `role`: `admin`, `manager`, `agent` — never `owner`; ownership moves only through transfer (T2.7)
- `invited_by_id` nullable FK to `User` (`SET_NULL`) — attribution survives the inviter leaving
- `token_hash` required, unique — SHA-256 of a 32-byte `secrets.token_urlsafe` token; the raw token is never stored
- `status`: `pending`, `accepted`, `revoked`
- `expires_at` required — creation plus seven days
- `accepted_at`, `accepted_by_id` nullable
- `delivery_status`: `pending`, `sent`, `failed`; `last_sent_at` nullable
- `created_at`, `updated_at`

Constraints: partial unique on `(workspace_id, email)` where `status = 'pending'`, so one live invitation
exists per address per workspace; unique `token_hash`; `CHECK` on `role` and on `status`; index on
`(workspace_id, status)`.

Expiry is derived, not stored: a `pending` row past `expires_at` is expired, so no job has to flip
statuses. Reads report `expired`, and acceptance refuses it.

No `Membership` row exists until acceptance. A pending invitation is not a member and appears in no
member list or count, which keeps member queries and the last-owner rule unchanged.

### Ticket
- `id` UUID
- `workspace_id`
- `requester_email` required, stored lowercased; `requester_name` optional — the customer contact snapshot (ADR-020)
- `requester_user_id` nullable — set only when the requester is also an active member of this workspace
- `assignee_id` nullable — must be an active member of the same workspace
- `subject`
- `description`
- `status`: `open`, `in_progress`, `waiting_on_customer`, `resolved`, `closed`
- `priority`: `low`, `normal`, `high`, `urgent`
- `category`
- `first_response_due_at` nullable — populated once an SLA policy is applied in Phase 8
- `first_responded_at` nullable
- `resolved_at` nullable
- `created_at`, `updated_at`
- `version` integer, default 1 — optimistic concurrency for field edits (ADR-022)

There is no `team_id`: teams are deferred past MVP (ADR-024).

Indexes should be based on actual queries, likely `(workspace_id, status, updated_at)`, `(workspace_id, assignee_id, status)`, and deadline/status candidate queries. Confirm with query plans rather than adding every possible index.

### TicketMessage
`ticket_id`, `author_id`, `body`, `visibility` (`public_reply`, `internal_note`), `created_at`. Public replies and internal notes must be filtered by server-side authorization, not just hidden in UI. Every staff role that may comment may choose either visibility (ADR-021); the distinction is enforced when a surface reads messages, so a customer-facing reader filters to `public_reply` (no such endpoint exists in MVP). Rows are append-only: no edit or delete operation in MVP. Appending a message moves the ticket's `updated_at` and leaves its `version` untouched, so a reply never invalidates a field edit someone is composing (ADR-022).

### TicketEvent / AuditEvent
Append-only event record: `workspace_id`, `actor_id` nullable for system action, `object_type`,
`object_id`, `event_type`, minimal structured metadata, `created_at`, `correlation_id`.

`event_type` is one of `ticket.created`, `ticket.updated`, `ticket.assigned`, `ticket.unassigned`,
`ticket.status_changed`, `ticket.message_added`. Metadata names what changed — the edited field
names, the previous and new assignee ids, the previous and new status, or the message id and its
visibility — and never copies a message body, requester address, or name. `correlation_id` is the
request id from the access log, so an audit row can be matched to the request that produced it.

Rows are written only by the ticket services, in the same transaction as the change they describe,
and no endpoint updates or deletes one. Indexes: `(workspace_id, created_at)` for workspace history
and `(object_type, object_id, created_at)` for one object's trail. Audit events are retained for 24
months (ADR-025).

### TaskRecord — background work (T5.2, ADR-033)
`task_name`, `idempotency_key`, `status` (`pending`, `running`, `succeeded`, `failed`), `attempts`,
`request_id`, `result` JSON, `last_error`, `created_at`, `updated_at`, `started_at`, `finished_at`.
Unique constraint on `(task_name, idempotency_key)`; `CHECK` on status; indexes on
`(status, created_at)` and `(task_name, -created_at)`.

It is not a result backend: it records whether the work ran, how many attempts it took, and a small
validated result. The dispatcher derives the idempotency key from the work itself
(`ticket:<id>:classify:v<version>`), so a repeated HTTP request and a redelivered message converge on
the same row. A worker claims a row only from `pending` or `failed`, so finished work is skipped and a
retry is allowed. `last_error` stores the exception *class*, never its message, because a provider
error can quote a credential or a customer's text.

### SLAPolicy
`workspace_id`, `name`, `priority`, `first_response_minutes`, `is_active`, policy/version timestamps. MVP uses elapsed minutes unless business-hours support is explicitly implemented.

### EscalationRule
`workspace_id`, `trigger` (e.g. `approaching_deadline`, `breached_deadline`, `unassigned_too_long`), threshold, action, target role/team, active flag.

### EscalationEvent
`workspace_id`, `ticket_id`, `rule_id`, `event_key`, `occurred_at`, `delivery_status`, metadata. Unique constraint on an idempotency/event key to avoid duplicate escalation records.

### AIJob / AIResult
Track entity, workspace, job type, status, provider/model, attempts, started/completed times, safe error category, and result JSON validated against a schema. Do not persist raw chain-of-thought or unnecessary full prompts. Store only what is needed for product functionality and debugging.

### KnowledgeArticle
`workspace_id`, title, body, status (`draft`, `published`, `archived`), version, created/updated timestamps, author.

### KnowledgeChunk
`workspace_id`, `article_id`, `article_version`, `chunk_index`, `content`, optional embedding, token estimate. Unique constraint on `(article_id, article_version, chunk_index)`. Never retrieve across workspace boundaries.

### Notification
`workspace_id`, recipient, channel, type, status, dedupe key, created/sent timestamps, safe error details.

## 2. Relationship sketch

```text
User ──< Membership >── Workspace
                            │
                            ├──< Invitation
                            ├──< Ticket ──< TicketMessage
                            │       ├──< TicketEvent
                            │       ├──< AIJob/AIResult
                            │       └──< EscalationEvent
                            ├──< SLAPolicy
                            ├──< EscalationRule
                            ├──< KnowledgeArticle ──< KnowledgeChunk
                            └──< Notification
```

## 3. Invariants

- Every tenant-owned record has a workspace/tenant association directly or through a parent.
- A pending invitation is not a membership: it appears in no member list, count, or permission check; acceptance creates or reactivates the membership.
- An invitation grants its role only when it is `pending`, unexpired, and accepted by an account whose email matches the invited address. Raw tokens are never stored or logged.
- At most one pending invitation exists per `(workspace, email)`; resending rotates the token and extends `expires_at` rather than creating a second row.
- Invitation roles never include `owner`; ownership changes only through transfer (T2.7).
- A ticket's `assignee_id`, and its `requester_user_id` when set, must reference an active member of the same workspace. `requester_email` and `requester_name` are contact data for a customer who does not need an account (ADR-020).
- Any active member of a workspace may read every ticket in it: visibility is workspace-wide, not assignee-scoped (ADR-021).
- A ticket's `version` changes when a ticket field changes, not when a message is appended, so a reply never makes a pending field edit stale (ADR-022).
- A user can only access a ticket if they have an authorized relationship to its workspace and role.
- Ticket status transitions are validated in a domain service.
- A public response can set `first_responded_at` only once and only if it qualifies under policy.
- AI-generated text is a draft and cannot become a public message without an explicit authorized action.
- Knowledge retrieval applies tenant and publication filters before returning candidates.
- Escalation and notification actions are deduplicated.
- Background work is identified by `(task_name, idempotency_key)`; duplicate dispatch, duplicate
delivery, and two workers racing all leave one row and one completed execution.
- Audit events are append-only at the application layer.
- Database constraints protect uniqueness and referential invariants where feasible.

## 4. Suggested status transition policy

- `open` → `in_progress`, `waiting_on_customer`, `resolved`
- `in_progress` → `waiting_on_customer`, `resolved`, `open`
- `waiting_on_customer` → `in_progress`, `resolved`, `open`
- `resolved` → `open` only under documented reopen policy; otherwise `closed`
- `closed` is terminal in MVP unless an explicit reopen workflow is designed

Implement transitions in a service and test allowed and disallowed transitions. Do not let a client set arbitrary status values without validating the transition.
