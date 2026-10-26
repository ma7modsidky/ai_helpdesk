# 15 — Ready-to-use Agent Task Backlog

Use one task prompt per implementation slice. The coding agent must read `09_AGENT_WORKFLOW.md`.

## T0.2 — Docker Compose foundation
**Goal:** Create local Compose services for PostgreSQL, Redis, RabbitMQ, backend, frontend, Celery worker, and Celery Beat, with health checks and persistent local database volume.
**Acceptance:** `docker compose config` succeeds; services use environment variables; no credentials are committed; README documents startup.
**Out of scope:** Kubernetes, production deployment, application features.

## T1.1 — Django foundation
**Goal:** Create Django project, settings configuration, custom user model if required, and initial health endpoints.
**Acceptance:** migrations run on PostgreSQL; system checks pass; DEBUG/secret config comes from environment; tests run.
**Must read:** architecture, security, CI/CD specs.

## T1.2 — Settings, environment, logging, and health endpoints
**Goal:** Split settings per environment, validate configuration from environment variables, add structured logging with request correlation, and expose health endpoints.
**Acceptance:** production settings refuse to start with missing, placeholder, or insecure configuration; no secret appears in an error message or a log line; every log line carries a request ID that is echoed in `X-Request-ID`; liveness and readiness report process and dependency state without leaking internals.
**Out of scope:** container health-check wiring, metrics, external error tracking.
**Must read:** architecture, security, CI/CD specs.

## T1.3 — API foundation
**Goal:** Add DRF with URL path versioning, bounded pagination, a uniform error envelope, session authentication, and an OpenAPI document.
**Acceptance:** every API error uses `{"error": {"code", "message", "request_id"}}`, including routing misses and unhandled exceptions; page size is bounded above and falls back safely below; an unsupported version returns 404; the OpenAPI document is served and passes its own validator.
**Out of scope:** workspace, ticket, knowledge-base, and SLA endpoints.
**Must read:** API contract, architecture, security specs.

## T1.4 — Test infrastructure
**Goal:** Standardise backend tests with factory fixtures, measured coverage, and a CI baseline that publishes the report.
**Acceptance:** test objects are created through factories rather than inline setup, and factories reuse the manager methods production uses; branch coverage is measured over application code; a configured floor fails CI when coverage drops; the report is uploaded as a CI artifact.
**Out of scope:** raising coverage of deliberately untested paths, frontend tests.
**Must read:** test strategy, CI/CD specs.

## T2.1 — Workspace and membership
**Goal:** Implement Workspace and Membership models with role choices, constraints, and migrations.
**Acceptance:** unique membership constraint; model tests; no endpoint trusts a workspace ID without membership authorization.
**Out of scope:** tickets, invitations UI.

## T2.2 — Tenant authorization
**Goal:** Implement reusable workspace membership/role authorization service and tests.
**Acceptance:** member can access own workspace; non-member cannot access another workspace; removed membership loses access.
**Security gate:** negative cross-tenant tests are required before continuing.

## T2.3 — Role/permission matrix and endpoint permissions
**Goal:** Define the role capability matrix and enforce it on workspace endpoints through a reusable permission class.
**Acceptance:** every workspace-scoped endpoint resolves membership before doing work; a non-member receives 404 and an insufficient role 403 in the standard error envelope; workspace creation assigns the creator as owner in the same transaction; the matrix is covered by tests for every role and capability.
**Out of scope:** invitations, ticket and knowledge-base permissions.
**Must read:** API contract, security spec, domain model.

## T2.4 — Cross-tenant negative tests for every tenant-owned resource
**Goal:** Prove that no endpoint can reach another tenant's data, and keep that proof current as new tenant-owned resources appear.
**Acceptance:** for every tenant-owned model and endpoint, a test asserts that a user of one workspace cannot list, read, or mutate another workspace's rows — the result is 404 or an empty list, never data; a new tenant-owned resource lands with its negative test in the same change.
**Security gate:** never permanently complete; re-run for every resource added in later phases.
**Must read:** security spec, test strategy.

## T2.5 — Self-registration
**Goal:** Add `POST /api/v1/auth/register/` so a new user can create an account with an email and password, and land signed in with no workspace.
**Acceptance:** public endpoint requiring a CSRF token; the address is stored lowercased and must be unique; Django's configured password validators are enforced and reported as `error.details.password`; a duplicate address is a 400 on `email`; success is 201 with the login response shape and an active session (`GET /auth/me/` returns the user); no workspace or membership is created; the throttle scope is enforced; tests use the client with CSRF enforcement on.
**Out of scope:** email verification, password reset, invitation acceptance (T2.6), frontend screens.
**Must read:** API contract, security spec, ADR-027.

## T2.6 — Invitations and acceptance
**Goal:** Implement the `Invitation` model and the contract's invitation endpoints — create, list, resend, revoke, invitee preview, and accept — with a hashed single-use token.
**Acceptance:** the raw token is never stored, logged, or returned by a list or detail read; create returns `accept_path` exactly once and resend returns a fresh one; a partial unique constraint allows one pending invitation per address, so a second create is 409 while resend rotates the token and extends expiry; create rejects `owner`, an invalid email, and an address that is already an active member; only owner and admin may manage invitations (403 otherwise) and non-members get 404; revoke invalidates the token immediately; acceptance requires a signed-in account whose email matches (403 otherwise), is idempotent for the same caller, is 409 when expired or when an active membership holds a different role, and reactivates a removed membership with the invited role; archived workspaces are not addressable; a delivery failure leaves `delivery_status` failed while the invitation survives, and resend retries; both throttle scopes are enforced; tests use the locmem email backend and never call a provider.
**Out of scope:** self-registration (T2.5), email verification, choosing an email provider, moving delivery to Celery (T5.1), frontend screens.
**Must read:** API contract, domain model, security spec, ADR-026.

## T2.7 — Atomic ownership transfer
**Goal:** Add `POST /workspaces/{id}/transfer-ownership/` so an owner can hand the workspace to another active member in one transaction.
**Acceptance:** owner-only (403 otherwise); the target becomes `owner` and the actor `admin` atomically, so an active owner always remains; self-transfer is 400; an inactive target is 409 and a foreign membership 404; two concurrent transfers cannot leave the workspace ownerless; cross-tenant negatives and the existing last-owner rule still pass.
**Out of scope:** invitations, teams, a dedicated ownership-history table (the audit stream records the change once T3.5 lands).
**Must read:** API contract, security spec, ADR-017, ADR-018, ADR-025.

## T3.1 — Ticket models
**Goal:** Implement Ticket, TicketMessage, and audit/event models with indexes and constraints, using the requester contact snapshot and optimistic-concurrency `version` from ADR-020 and ADR-022, and no `team_id` (ADR-024).
**Acceptance:** valid relationships; `requester_email` required and stored lowercased; `requester_user_id` accepted only for an active member of the same workspace; `version` defaults to 1 and does not change when a message is appended; public reply/internal note distinction; status/priority choices enforced by database constraints as well as choices; model tests for each rule.
**Out of scope:** AI, frontend.

## T3.2 — Ticket API
**Goal:** Implement list/create/detail and message endpoints per API contract, including the `ordering` allowlist, the `assignee` values (`me`, `unassigned`, UUID), and `If-Match` field edits.
**Acceptance:** the capability matrix in the contract is enforced per route (403); invalid filter or ordering values and out-of-allowlist `PATCH` fields are 400 with field details; a stale or missing `If-Match` is 409 reporting the current version; appending a message does not invalidate a held version; pagination is stable across ties; cross-tenant tests; error envelope.
**Performance:** prevent N+1 queries using appropriate select_related/prefetch_related; verify the list query plan against the documented indexes.

## T5.1 — Celery/RabbitMQ
**Goal:** Configure Celery with RabbitMQ broker, task autodiscovery, worker and Beat.
**Acceptance:** sample task runs; retry behavior is tested; health/logging instructions documented; no real external call required in CI.

## T6.1 — AI provider interface
**Goal:** Define provider abstraction and deterministic fake provider.
**Acceptance:** unit tests do not need network/API keys; timeout and provider error types are modeled; credentials remain backend-only.

## T6.2 — AI classification
**Goal:** Add async classification job with strict structured schema and persisted job status.
**Acceptance:** ticket creation is not blocked by AI; invalid model output is rejected; duplicate task delivery is safe; tenant-scoped data only.

## T6.3 — AI reply draft
**Goal:** Generate a draft and return source references; never publish automatically.
**Acceptance:** `202 Accepted`; UI-visible states; explicit send endpoint required; permission and prompt-injection tests.

## T7.1 — Knowledge base
**Goal:** Implement article CRUD and publication lifecycle.
**Acceptance:** only authorized roles can publish; drafts are excluded from retrieval; tenant isolation tests.

## T7.2 — RAG retrieval
**Goal:** Implement tenant-scoped full-text or vector retrieval and source references.
**Acceptance:** only published articles in current workspace can be returned; source IDs are validated; no-source fallback is safe.

## T8.1 — SLA service
**Goal:** Calculate first-response deadlines and track qualifying public response.
**Acceptance:** internal notes do not count; boundary tests; timezone-aware timestamps; policy behavior documented.

## T8.2 — Escalation task
**Goal:** Periodically detect approaching/breached deadlines and create deduplicated escalation events.
**Acceptance:** repeated task runs create no duplicate events; task rechecks current ticket state; notification failure doesn't duplicate escalation.

## T9.1 — Release hardening
**Goal:** Add/verify CI security checks, container build, staging smoke test, deployment and rollback docs.
**Acceptance:** clean CI; no secrets; known limitations and demo flow documented.
