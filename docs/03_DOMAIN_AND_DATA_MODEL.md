# 03 — Domain Model and Data Model

## 1. Core entities

### User
Identity and authentication fields. Avoid storing secrets or external provider tokens in plaintext.

### Workspace
Tenant boundary. Holds name, slug, timezone, settings, and lifecycle state.

### Membership
`workspace`, `user`, `role`, `status`, `created_at`. Unique constraint on `(workspace, user)`. Roles: `owner`, `admin`, `manager`, `agent`. Customer access should be modeled separately if a portal is implemented.

### Team
`workspace`, `name`, `description`. Unique name per workspace where appropriate.

### Ticket
- `id` UUID
- `workspace_id`
- `requester_id`
- `assignee_id` nullable
- `team_id` nullable
- `subject`
- `description`
- `status`: `open`, `in_progress`, `waiting_on_customer`, `resolved`, `closed`
- `priority`: `low`, `normal`, `high`, `urgent`
- `category`
- `first_response_due_at`
- `first_responded_at` nullable
- `resolved_at` nullable
- `created_at`, `updated_at`
- `version` integer for optimistic concurrency if needed

Indexes should be based on actual queries, likely `(workspace_id, status, updated_at)`, `(workspace_id, assignee_id, status)`, and deadline/status candidate queries. Confirm with query plans rather than adding every possible index.

### TicketMessage
`ticket_id`, `author_id`, `body`, `visibility` (`public_reply`, `internal_note`), `created_at`. Public replies and internal notes must be filtered by server-side authorization, not just hidden in UI.

### TicketEvent / AuditEvent
Append-only event record: `workspace_id`, `actor_id` nullable for system action, `object_type`, `object_id`, `event_type`, minimal structured metadata, `created_at`, `correlation_id`. Avoid storing full message bodies or secrets in metadata.

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
User ──< Membership >── Workspace ──< Team
                            │
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
- A ticket's requester/assignee/team must be valid for the same workspace according to the product's membership model.
- A user can only access a ticket if they have an authorized relationship to its workspace and role.
- Ticket status transitions are validated in a domain service.
- A public response can set `first_responded_at` only once and only if it qualifies under policy.
- AI-generated text is a draft and cannot become a public message without an explicit authorized action.
- Knowledge retrieval applies tenant and publication filters before returning candidates.
- Escalation and notification actions are deduplicated.
- Audit events are append-only at the application layer.
- Database constraints protect uniqueness and referential invariants where feasible.

## 4. Suggested status transition policy

- `open` → `in_progress`, `waiting_on_customer`, `resolved`
- `in_progress` → `waiting_on_customer`, `resolved`, `open`
- `waiting_on_customer` → `in_progress`, `resolved`, `open`
- `resolved` → `open` only under documented reopen policy; otherwise `closed`
- `closed` is terminal in MVP unless an explicit reopen workflow is designed

Implement transitions in a service and test allowed and disallowed transitions. Do not let a client set arbitrary status values without validating the transition.
