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
- `GET /auth/me/`
- `GET /workspaces/`
- `POST /workspaces/`
- `GET /workspaces/{workspace_id}/members/`
- `POST /workspaces/{workspace_id}/invitations/`
- `PATCH /workspaces/{workspace_id}/members/{membership_id}/`

### Tickets
- `GET /workspaces/{workspace_id}/tickets/?status=&priority=&assignee=&search=&page=`
- `POST /workspaces/{workspace_id}/tickets/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/`
- `PATCH /workspaces/{workspace_id}/tickets/{ticket_id}/` for permitted fields only
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/assign/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/transition/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/messages/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/messages/`
- `POST /workspaces/{workspace_id}/tickets/{ticket_id}/ai-draft/`
- `GET /workspaces/{workspace_id}/tickets/{ticket_id}/ai-status/`

### Knowledge base
- `GET /workspaces/{workspace_id}/articles/`
- `POST /workspaces/{workspace_id}/articles/`
- `GET /workspaces/{workspace_id}/articles/{article_id}/`
- `PATCH /workspaces/{workspace_id}/articles/{article_id}/`
- `POST /workspaces/{workspace_id}/articles/{article_id}/publish/`
- `POST /workspaces/{workspace_id}/articles/{article_id}/reindex/`

### SLA and analytics
- `GET /workspaces/{workspace_id}/sla-policies/`
- `POST /workspaces/{workspace_id}/sla-policies/`
- `PATCH /workspaces/{workspace_id}/sla-policies/{policy_id}/`
- `GET /workspaces/{workspace_id}/escalations/`
- `GET /workspaces/{workspace_id}/analytics/overview/`

### Operational endpoints
- `GET /health/live/` — process is alive
- `GET /health/ready/` — readiness and required dependency status, without leaking internals

## Authentication flow (implemented)

Session-cookie authentication with CSRF protection. No bearer tokens are issued to the browser.

1. `GET /auth/csrf/` — public. Sets the httpOnly `csrftoken` cookie and returns
   `{"csrf_token": "..."}`. JavaScript reads the value here, not from the cookie.
2. `POST /auth/login/` — public, requires `X-CSRFToken`, JSON body `{"email", "password"}`.
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
3. `POST /auth/logout/` — authenticated, requires `X-CSRFToken`. Returns `204`.
4. `GET /auth/me/` — authenticated. Returns the user object above.

All state-changing requests must send `Content-Type: application/json` (use `{}` when there is no
payload) together with `X-CSRFToken`. Resulting status codes:

| Situation | Response |
| --- | --- |
| No session | `401 not_authenticated` + `WWW-Authenticate: Session` |
| Authenticated but not allowed | `403 permission_denied` |
| Missing or invalid CSRF token | `403 csrf_failed` |
| Non-JSON request body | `415 unsupported_media_type` |
| Too many login attempts | `429 throttled` + `Retry-After` |

The workspace, ticket, knowledge-base, and SLA endpoints listed above remain the target contract and
are implemented by later tasks.

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
