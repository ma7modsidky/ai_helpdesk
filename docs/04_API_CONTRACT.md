# 04 — API Contract (MVP)

Base path: `/api/v1/`. JSON request/response bodies. Exact fields can be refined before implementation, but changes must update this contract and tests.

## Conventions

- Authentication required except explicitly public endpoints.
- Workspace context is selected through a validated route or membership context. A workspace ID supplied by the client is never sufficient authorization.
- Use pagination with a bounded maximum page size.
- Use ISO-8601 UTC timestamps.
- Return consistent errors, e.g. `{"error":{"code":"permission_denied","message":"You do not have access to this resource","request_id":"..."}}`.
  `request_id` always equals the `X-Request-ID` response header so a client report can be matched to a log line.
  `400 validation_error` responses additionally include `error.details` mapping field names to messages.
  Messages are stable and generic; they never reveal whether another tenant's object exists.
- Do not reveal whether another tenant's object exists. Cross-tenant object requests should generally return 404.
- Apply throttling to authentication, ticket creation, AI generation, and invitation endpoints.
- Use idempotency keys for externally retried mutation endpoints where duplicate execution would be harmful.

## Endpoints

### Identity/workspaces
- `POST /auth/register/`
- `GET /auth/me/`
- `GET /workspaces/`
- `POST /workspaces/`
- `GET /workspaces/{workspace_id}/members/`
- `POST /workspaces/{workspace_id}/invitations/`
- `PATCH /workspaces/{workspace_id}/members/{membership_id}/`
- `POST /workspaces/{workspace_id}/transfer-ownership/`

#### Ownership transfer

Implemented in T2.7.

- `POST /workspaces/{workspace_id}/transfer-ownership/` — JSON `{"membership_id": "..."}`. Owner only.
  In one transaction the target becomes `owner` and the caller becomes `admin`, so the workspace always
  retains an active owner. Returns `200` with `owner` and `previous_owner` memberships. This is the
  atomic alternative to grant-then-demote; `PATCH members` keeps enforcing the last-active-owner rule
  on its own.

| Situation | Response |
| --- | --- |
| Caller is not an owner | `403 permission_denied` |
| Target is the caller's own membership | `400 validation_error` |
| Target membership is not active | `409 conflict` |
| Target membership belongs to a different workspace | `404 not_found` |

#### Invitations

Managed under the existing `members.manage` capability (owner and admin); managers and agents cannot see
or issue invitations. A workspace holds at most one pending invitation per email address.

- `POST /workspaces/{workspace_id}/invitations/` — JSON `{"email", "role"}` with `role` one of `admin`,
  `manager`, `agent`. Returns `201` with the invitation and a one-time `accept_path` (the SPA route
  `/invite/<token>`) for the inviter to share; delivery is attempted through the configured email backend
  at the same time.
- `GET /workspaces/{workspace_id}/invitations/?status=pending&page=` — paginated. `status` defaults to
  `pending`, which returns live and expired rows together because resend is the action for either; each
  row's `status` reports which. `accepted` and `revoked` are the other filters, and `all` combines them.
- `POST /workspaces/{workspace_id}/invitations/{invitation_id}/resend/` — rotates the token, resets
  `expires_at` to seven days from now, retries delivery, and returns `200` with a new one-time
  `accept_path`.
- `DELETE /workspaces/{workspace_id}/invitations/{invitation_id}/` — revokes immediately, `204`. The
  token can no longer be accepted, and the preview still reports `revoked` so the invitee can be told
  why. An accepted invitation cannot be revoked; removing that member is a membership change.

Rows: `id`, `email`, `role`, `status`, `expires_at`, `created_at`, `invited_by` (`user_id`, `email`),
`delivery_status`. **The token and `accept_path` appear only in the create and resend responses** — never
in a list or detail read, and never in a log line.

| Situation | Response |
| --- | --- |
| Caller is not an owner or admin | `403 permission_denied` |
| Caller is not a member, or the workspace is unknown or archived | `404 not_found` |
| Invalid email, unknown role, or `role: "owner"` | `400 validation_error` |
| The address already holds an active membership | `400 validation_error` on `email` |
| A pending invitation already exists for the address | `409 conflict` — resend or revoke it instead |
| Unknown invitation, or one belonging to another workspace | `404 not_found` |
| Revoking or resending an accepted invitation | `409 conflict` |

Delivery is best effort and never the source of truth: the row is created even when sending fails,
`delivery_status` records the outcome, and resend retries. Until Celery lands (T5.1) the send is
synchronous with a bounded timeout, which is a documented limitation rather than a queue.

Throttles: `invitation_create` at 30 per hour per user for creating and resending, `invitation_accept`
at 30 per hour per IP for the invitee endpoints below. The limiter is per process until a shared cache
is configured (T5.1).

### Invitations (invitee side)

Implemented in T2.6. These two routes authorize with the token, not with a membership, and the token
travels in the JSON body rather than the path or query string: request logs record the path (`ADR-010`)
and URLs leak through referrers and browser history.

- `POST /invitations/preview/` — public, JSON `{"token"}`. Returns `200` with `workspace_name`, `role`,
  `status` (`pending`, `expired`, `accepted`, `revoked`) and `expires_at`. It does not return the invited
  email. An unknown token is `404 not_found`. The SPA reads the token from its own route, not from the
  response.
- `POST /invitations/accept/` — authenticated session with `X-CSRFToken`, JSON `{"token"}`. Returns `200`
  with `workspace` and `membership`. The signed-in account's email must equal the invited address; joining
  creates the membership with the invited role, reactivates a `removed` membership with that role, and
  marks the invitation `accepted`.

| Situation | Response |
| --- | --- |
| No session | `401 not_authenticated` |
| Signed in as a different address | `403 permission_denied` |
| Token unknown or revoked | `404 not_found` |
| Token expired | `409 conflict` with code `invitation_expired` |
| Already accepted by this caller | `200`, idempotent |
| An active membership with a different role already exists | `409 conflict` |

### Tickets

Every route below resolves the caller's active membership first, then requires the capability in this
table. A missing capability is `403`; a workspace the caller cannot see is `404`.

| Capability | owner | admin | manager | agent | Covers |
|---|---|---|---|---|---|
| `tickets.view` | yes | yes | yes | yes | list and read any ticket in the workspace |
| `tickets.create` | yes | yes | yes | yes | create a ticket |
| `tickets.comment` | yes | yes | yes | yes | post a public reply or an internal note |
| `tickets.assign_self` | yes | yes | yes | yes | assign to the caller, or release the caller's own assignment |
| `tickets.assign_others` | yes | yes | yes | no | assign to, or unassign, anyone else |
| `tickets.transition` | yes | yes | yes | yes | change status through an allowed transition |

Visibility is workspace-wide: any active member reads any ticket (ADR-021). There is no
assignee-scoped visibility and no customer-facing ticket surface in MVP.

- `GET /workspaces/{workspace_id}/tickets/?status=&priority=&assignee=&search=&ordering=&page=&page_size=`
- `POST /workspaces/{workspace_id}/tickets/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/`
- `PATCH /workspaces/{workspace_id}/tickets/{ticket_id}/` — field edits, requires `If-Match`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/assign/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/transition/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/messages/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/messages/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/ai-draft/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/ai-status/`

#### Ticket representation

`id`, `subject`, `description`, `status`, `priority`, `category`, `requester_email`,
`requester_name`, `requester_user_id`, `assignee_id`, `version`, `first_response_due_at`,
`first_responded_at`, `resolved_at`, `created_at`, `updated_at`. `first_response_due_at` is null until
an SLA policy is applied; it is read-only.

#### Creating

JSON: `subject` 1–200 characters, `description` 1–10000, `requester_email` required and stored
lowercased, `requester_name` optional up to 200, `requester_user_id` optional, `priority` optional
(default `normal`), `category` optional up to 100. `status` and `assignee_id` are not accepted: new
tickets are `open` and unassigned, and both have their own commands.

`requester_user_id` is accepted only when it names an active member of this workspace; otherwise the
request fails with `400 validation_error`, with the same message whether that user exists or not.
`requester_email` is captured regardless, so a customer never needs an account (ADR-020).

#### Listing and filtering

- `status`, `priority` — one value each, validated against the enum; unknown value → `400`.
- `assignee` — `me`, `unassigned`, or a user UUID. A well-formed UUID that is not a member of this
  workspace matches nothing, so the parameter is not an existence oracle. Anything else → `400`.
- `search` — case-insensitive substring over `subject` only; trimmed; 1–100 characters, longer → `400`.
- `ordering` — allowlist `created_at`, `updated_at`, `priority`, `status`, optionally prefixed with `-`
  for descending; default `-updated_at`; anything else → `400`. Ties are broken by `id` so pages are
  stable across requests.
- Filters combine with AND. Pagination follows the conventions in this document.

#### Field edits and concurrency (PATCH)

Permitted fields: `subject`, `description`, `priority`, `category`, `requester_email`,
`requester_name`. `status`, `assignee_id`, `requester_user_id`, and the timestamps are rejected with
`400`, because status and assignment have their own commands.

The request must send `If-Match: "<version>"` with the value from the client's last read. The check
and the increment happen in a single statement, so a stale or missing header cannot overwrite a
newer edit:

| Situation | Response |
| --- | --- |
| `If-Match` missing, malformed, or not the current version | `409 conflict`; `error.details.version` reports the current version |
| A field outside the permitted set | `400 validation_error` |

#### Commands

- `POST .../assign/` with `{"assignee_id": "<uuid>" | null}`. The target must be an active member
  (otherwise `400`). Self-assignment and releasing your own assignment need `tickets.assign_self`;
  acting on anyone else needs `tickets.assign_others` (otherwise `403`).
- `POST .../transition/` with `{"status": "<status>"}`. Legality is decided by the domain service
  per ADR-009: agents and above move between `open`, `in_progress`, `waiting_on_customer` and may
  resolve; `resolved → open` (reopen) requires manager or above; `resolved → closed` is the only way
  to close and `closed` is terminal. An illegal transition is `409 conflict`; an unknown status is
  `400`.
- Both commands apply to the current state, take a row lock on the ticket, and return the updated
  ticket including its new `version`. They do not require `If-Match`: they name the state they want
  rather than overwriting fields (ADR-022).
- `POST .../messages/` with `{"body": "…" (1–20000), "visibility": "public_reply" | "internal_note"}`,
  defaulting to `public_reply`, and returns `201` with the message. Appending a message updates the
  ticket's `updated_at` but does not change its `version`. Messages are append-only in MVP with no
  edit or delete route; `GET .../messages/` returns both visibilities to any member, because there is
  no customer-facing reader yet and the field exists so one can be added without migrating rows.

| Situation | Response |
| --- | --- |
| Caller is not a member, or the workspace is unknown or archived | `404 not_found` |
| Caller lacks the capability (for example an agent assigning to someone else) | `403 permission_denied` |
| Invalid filter, ordering value, or body | `400 validation_error` |
| Stale `If-Match`, or an illegal status transition | `409 conflict` |
| Ticket belongs to a different workspace | `404 not_found` |

### Knowledge base
- `GET /workspaces/{workspace_id}/articles/`
- `POST /workspaces/{workspace_id}/articles/`
- `GET /workspaces/{workspace_id}/articles/{article_id}/`
- `PATCH /workspaces/{workspace_id}/articles/{article_id}/`
- `POST /workspaces/{workspace_id}/articles/{article_id}/publish/`
- `POST /workspaces/{workspace_id}/articles/{article_id}/reindex/`

### SLA
- `GET /workspaces/{workspace_id}/sla-policies/`
- `POST /workspaces/{workspace_id}/sla-policies/`
- `PATCH /workspaces/{workspace_id}/sla-policies/{policy_id}/`
- `GET /workspaces/{workspace_id}/escalations/`

There is no analytics endpoint in MVP: it was unspecified and is removed by ADR-025. Adding it later
needs metrics, aggregates, and a permission rule, not just a route.

### Operational endpoints
- `GET /health/live/` — process is alive
- `GET /health/ready/` — readiness and required dependency status, without leaking internals

## Authentication flow (implemented)

Session-cookie authentication with CSRF protection. No bearer tokens are issued to the browser.

1. `GET /auth/csrf/` — public. Sets the httpOnly `csrftoken` cookie and returns
   `{"csrf_token": "..."}`. JavaScript reads the value here, not from the cookie.
2. `POST /auth/register/` — public, requires `X-CSRFToken`, JSON body `{"email", "password"}`.
   Returns `201` with the same body as login and starts a session. The address is stored lowercased and
   the password is checked against the configured validators. A duplicate address or a weak password
   returns `400 validation_error` with `error.details`. Throttled at 10 attempts per hour per client.
   The account has no workspace: it joins one by creating a workspace or accepting an invitation.
3. `POST /auth/login/` — public, requires `X-CSRFToken`, JSON body `{"email", "password"}`.
   Returns `200`:
   ```json
   {
     "user": {"id": "uuid", "email": "agent@example.com", "is_staff": false},
     "csrf_token": "..."
   }
   ```
   The session and CSRF token rotate on login, so clients must replace their stored token with the
   returned one. Unknown email, wrong password, and inactive account all return the same
   `401 authentication_failed` message so the endpoint cannot be used to enumerate accounts.
   Throttled at 10 attempts per minute per client.
4. `POST /auth/logout/` — authenticated, requires `X-CSRFToken`. Returns `204`.
5. `GET /auth/me/` — authenticated. Returns the user object above.

All state-changing requests must send `Content-Type: application/json` (use `{}` when there is no
payload) together with `X-CSRFToken`. Resulting status codes:

| Situation | Response |
| --- | --- |
| Invalid registration input (malformed or duplicate email, weak password) | `400 validation_error` + `error.details` |
| No session | `401 not_authenticated` + `WWW-Authenticate: Session` |
| Authenticated but not allowed | `403 permission_denied` |
| Missing or invalid CSRF token | `403 csrf_failed` |
| Non-JSON request body | `415 unsupported_media_type` |
| Too many login attempts | `429 throttled` + `Retry-After` |

The ticket, knowledge-base, and SLA endpoints listed above remain the target contract and are
implemented by later tasks, except the analytics endpoint, which is removed from MVP (ADR-025).
Registration, invitations, and ownership transfer are implemented (T2.5, T2.6, T2.7); their error tables
above are enforced by `apps/accounts/tests/test_register_api.py`,
`apps/organizations/tests/test_invitation_*.py`, and `apps/organizations/tests/test_ownership_*.py`.

## Workspaces and members (implemented)

Session-authenticated. Every workspace route resolves the caller's active membership before doing
any work, so a workspace the caller cannot see is indistinguishable from one that does not exist.

- `GET /workspaces/` — paginated list of active workspaces where the caller has an active
  membership. Rows: `id`, `name`, `slug`, `timezone`, `status`, `created_at`.
- `POST /workspaces/` — JSON `{"name", "slug", "timezone"?}`; `timezone` is an IANA name and
  defaults to `UTC`. Returns `201` with the workspace, and the caller becomes its `owner` in the
  same transaction. A duplicate or malformed slug, or an unknown time zone, returns
  `400 validation_error` with `error.details`.
- `GET /workspaces/{workspace_id}/members/` — paginated active memberships; readable by any active
  member. Rows: `id`, `user_id`, `email`, `role`, `status`, `created_at`.
- `PATCH /workspaces/{workspace_id}/members/{membership_id}/` — JSON with `role` and/or `status`
  (`active` or `removed`); at least one is required. Returns `200` with the membership.

| Situation | Response |
| --- | --- |
| Caller is not a member, or the workspace is unknown or archived | `404 not_found` |
| Caller's role lacks the capability (for example an agent changing a role) | `403 permission_denied` |
| Admin targets another admin or any owner, or grants a role at or above their own | `403 permission_denied` |
| The change would leave the workspace without an active owner | `409 conflict` |
| Unknown role or status, or an empty body | `400 validation_error` |
| The membership belongs to a different workspace | `404 not_found` |

Only an owner may grant `owner`. Revoking a member keeps the row with `status: "removed"` and
withdraws access immediately; an owner or admin can set it back to `active`.

## Versioning, pagination, and schema

- Base path `/api/v1/`. An unsupported version (for example `/api/v2/...`) returns `404`.
- List responses use `{"count", "next", "previous", "results"}` with `page` (1-based) and
  `page_size` (default 25, maximum 100). Larger values are clamped; an unparseable `page_size`
  falls back to the default; a page past the end returns `404 not_found`.
- `GET /api/v1/schema/` returns the OpenAPI 3 document. Public, no authentication required.

## Ticket creation example

Request:
```json
{
  "subject": "Duplicate subscription charge",
  "description": "I see two charges for my monthly subscription.",
  "priority": "normal"
}
```

Response should confirm persistence immediately and return the AI job state without waiting for the LLM:
```json
{
  "id": "uuid",
  "subject": "Duplicate subscription charge",
  "status": "open",
  "priority": "normal",
  "ai_status": "pending",
  "created_at": "2026-01-01T12:00:00Z"
}
```

## AI draft contract

`POST .../ai-draft/` creates or schedules a draft-generation job and returns `202 Accepted` with a job/result identifier and status. It must not send a public message.

A completed draft response contains:
- `status`
- `draft_text`
- `source_articles`: identifiers and titles of retrieved sources
- `provider/model` if safe and useful
- `created_at`
- `requires_human_approval: true`

## Error behavior

- `400`: validation/domain input error
- `401`: unauthenticated
- `403`: authenticated but not permitted, when revealing object existence is safe
- `404`: unknown or inaccessible tenant-scoped object
- `409`: state conflict or idempotency conflict
- `429`: throttled
- `500`: generic internal error with request ID
- `503`: dependency unavailable where request cannot be served safely

Do not leak stack traces, SQL, tokens, prompts, or internal provider responses to clients.
