# 08 — Implementation Plan (dependency-ordered vertical slices)

Keep each task small enough for an agent to complete, test, and explain in one bounded change. Commit after each verified slice.

## Phase 0 — Repository and decisions
- T0.1 Create repo, README, docs, `.editorconfig`, ignore files.
- T0.2 Add Docker Compose for PostgreSQL, Redis, RabbitMQ, backend, frontend, worker, beat.
- T0.3 Configure environment variables and `.env.example` with placeholders only.
- T0.4 Add CI skeleton and baseline lint/test commands.
**Exit:** clean clone starts dependencies; CI runs.

## Phase 1 — Backend foundation
- T1.1 Create Django project and custom user model if needed before first migration.
- T1.2 Configure settings split, environment validation, logging, health endpoints.
- T1.3 Add DRF, API versioning, pagination, exception envelope, OpenAPI schema.
- T1.4 Add pytest, factory fixtures, coverage, and test database setup.
**Exit:** migrations work; tests and checks pass in CI.

## Phase 2 — Tenancy and access control
- T2.1 Workspace and Membership models with constraints.
- T2.2 Workspace resolution and authorization services.
- T2.3 Role/permission matrix and endpoint permissions.
- T2.4 Cross-tenant negative tests for every tenant-owned resource.
**Exit:** tenant isolation is proven by tests before ticket features are added.

## Phase 3 — Ticket workflow
- T3.1 Ticket and TicketMessage models, migrations, constraints, indexes.
- T3.2 Ticket creation/list/detail APIs and pagination/filtering.
- T3.3 Status transition and assignment services.
- T3.4 Internal notes vs public replies.
- T3.5 Audit events and API tests.
**Exit:** complete manual ticket workflow works without AI.

## Phase 4 — Frontend baseline
- T4.1 App shell, authentication, workspace selector.
- T4.2 Ticket inbox and filters.
- T4.3 Ticket detail/conversation UI.
- T4.4 Role-aware actions and accessible loading/error states.
**Exit:** user can resolve a ticket end to end.

## Phase 5 — Async infrastructure
- T5.1 Configure Celery with RabbitMQ broker and Redis only for explicitly chosen cache/result use.
- T5.2 Add task status model and idempotency conventions.
- T5.3 Add test worker/task harness and retry/backoff defaults.
- T5.4 Add a simulated slow/failing task and observability.
**Exit:** tasks run locally and failure behavior is tested.

## Phase 6 — AI classification and reply drafts
- T6.1 Define provider interface and deterministic fake provider.
- T6.2 Implement structured classification with schema validation.
- T6.3 Implement asynchronous processing states and retries.
- T6.4 Add draft-generation endpoint and UI.
- T6.5 Enforce human approval; no automatic public sends.
- T6.6 Add AI evaluation fixtures and usage limits.
**Exit:** ticket creation works without LLM; AI draft is generated and safely reviewed.

## Phase 7 — Knowledge base and RAG
- T7.1 Article CRUD and publication lifecycle.
- T7.2 Chunking and indexing pipeline.
- T7.3 Implement PostgreSQL full-text search first or `pgvector` if embeddings are in scope.
- T7.4 Tenant-scoped retrieval and source citations.
- T7.5 Prompt-injection and cross-tenant retrieval tests.
**Exit:** draft references correct tenant-scoped published sources.

## Phase 8 — SLA and escalations
- T8.1 SLA policy and deadline service.
- T8.2 Public-response tracking.
- T8.3 Periodic deadline task and deduplicated escalation events.
- T8.4 Notification delivery with retry/idempotency.
- T8.5 Manager escalation UI and tests.
**Exit:** simulated deadline causes exactly one correct escalation.

## Phase 9 — Hardening and deployment
- T9.1 Query review, indexes, N+1 tests or query-count checks where valuable.
- T9.2 Security headers, CORS/CSRF review, throttling, upload limits if uploads exist.
- T9.3 Dependency, secret, SAST and container scans.
- T9.4 Staging deployment, migrations, smoke tests, rollback instructions.
- T9.5 Seeded demo data, screenshots, architecture diagram, demo script.
**Exit:** CI green, staging demo reliable, documented known limitations.

## Scope rule

Do not start the next phase until the current phase's exit criteria pass. If a task discovers a specification conflict, stop and propose a spec change rather than silently inventing behavior.
