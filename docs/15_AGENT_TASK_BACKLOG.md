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

## T3.1 — Ticket models
**Goal:** Implement Ticket, TicketMessage, and audit/event models with indexes and constraints.
**Acceptance:** valid relationships; public reply/internal note distinction; status/priority choices; model tests.
**Out of scope:** AI, frontend.

## T3.2 — Ticket API
**Goal:** Implement list/create/detail and message endpoints per API contract.
**Acceptance:** pagination, filtering, permission checks, validation, error envelope, cross-tenant tests.
**Performance:** prevent N+1 queries using appropriate select_related/prefetch_related.

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
