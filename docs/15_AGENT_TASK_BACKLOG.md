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

## T2.1 — Workspace and membership
**Goal:** Implement Workspace and Membership models with role choices, constraints, and migrations.
**Acceptance:** unique membership constraint; model tests; no endpoint trusts a workspace ID without membership authorization.
**Out of scope:** tickets, invitations UI.

## T2.2 — Tenant authorization
**Goal:** Implement reusable workspace membership/role authorization service and tests.
**Acceptance:** member can access own workspace; non-member cannot access another workspace; removed membership loses access.
**Security gate:** negative cross-tenant tests are required before continuing.

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
