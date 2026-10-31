# 08 — Implementation Plan (dependency-ordered vertical slices)

Keep each task small enough for an agent to complete, test, and explain in one bounded change. Commit after each verified slice.

`16_PHASE2_AUDIT.md` records which contract endpoints and domain entities currently have no task
here, and the decisions that must be settled before the next phase starts. Check it before
beginning a phase.

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
- T2.5 Self-registration: email and password sign-up that starts a session and creates no workspace (ADR-027).
- T2.6 Invitations and acceptance: hashed single-use token, seven-day expiry, revoke/resend, invitee preview and accept (ADR-026).
- T2.7 Atomic ownership transfer, owner only (FR-006).
**Exit:** tenant isolation is proven by tests before ticket features are added, and a workspace can be
populated and handed over through the API alone — invite and accept (T2.6), transfer (T2.7) — with no
shell access.

## Phase 3 — Ticket workflow
- T3.1 Ticket and TicketMessage models, migrations, constraints, indexes: requester contact snapshot and `version` (ADR-020, ADR-022), no `team_id` (ADR-024).
- T3.2 Ticket creation/list/detail APIs with the contract's filters and `ordering` allowlist (ADR-023), `If-Match` field edits (ADR-022), and the message endpoints.
- T3.3 Status transition and assignment services.
- T3.4 Internal notes vs public replies.
- T3.5 Audit events and API tests.
**Exit:** complete manual ticket workflow works without AI.

## Phase 4 — Frontend foundation, bilingual UI, and the ticket workspace

The frontend is built in slices that keep a working application after every task: project and gates
first, then the design and language layer, then the surfaces, then the accessibility and end-to-end
gates. Tasks are ordered so nothing is styled before tokens exist and no copy is written before the
catalogs do. Every task includes its tests in the same change (`13_DEFINITION_OF_DONE.md`).

- T4.1 Frontend project, tooling, and gates: Vite + React + TypeScript strict, pnpm lockfile, ESLint
  (type-aware) and Prettier, Vitest + Testing Library + jsdom, the frontend CI job, a Compose dev
  service, and a dev proxy to the API so the SPA talks to `/api/v1` same-origin (CORS stays off).
- T4.2 Design system and theming: token set, light and dark colour schemes with CSS variables, the
  Latin and Arabic typography scales with self-hosted fonts, MUI component defaults, the state
  primitives (loading, empty, error, forbidden, conflict), and the no-flash theme script.
- T4.3 Internationalization and RTL: react-i18next with `en` and `ar` catalogs, locale resolution and
  persistence, `html` `lang`/`dir` switching, MUI direction plus the Emotion RTL cache, `Intl`
  formatters, mirrored directional icons, the catalog-parity test, and the direction-matrix test.
- T4.4 API client and server-state layer: the single `fetch` wrapper (CSRF bootstrap, credentials,
  error envelope to typed `ApiError`, request-ID surfacing), the status-code behaviour table, and the
  TanStack Query setup with the workspace-scoped key scheme and invalidation rules.
- T4.5 Authentication screens: sign in, sign up, sign out, session restoration, protected routing,
  post-login redirect, field-level validation from `error.details`, and expired-session handling.
- T4.6 Invitation acceptance: `/invite/:token` preview, sign in or register with the invited address,
  acceptance, and the expired, revoked, accepted, and mismatched-account states.
- T4.7 Workspace picker and application shell: workspace list with roles, create-workspace flow, empty
  state for an account with no memberships, and the shell (switcher, nav built from the route table,
  language and theme controls, user menu, not-found and forbidden pages).
- T4.8 Members and invitation settings: member list, role changes and revocation mirroring the server's
  refusals, the last-owner explanation, invitation states with resend and revoke, and ownership
  transfer with its confirmation step.
- T4.9 Ticket inbox: URL-synced filters, ordering, and pagination; debounced search; status and
  priority chips; skeleton, empty, filtered-empty, error, and retry states.
- T4.10 Ticket detail and conversation: timeline with distinct public reply and internal note
  treatment, capability-driven status/priority/assignee controls, `If-Match` writes with the conflict
  prompt, and the audit history panel.
- T4.11 Frontend test and accessibility gate: per-screen axe assertions in both directions, keyboard
  and focus tests, the coverage floor for `src/`, and the hardcoded-copy rule enforced in lint.
- T4.12 End-to-end journey in both directions: Playwright runs register → create workspace → invite →
  accept → create ticket → resolve in `en` and `ar`, wired into CI against a seeded backend.

**Exit:** a new user can register, create or join a workspace, and resolve a ticket end to end in the
browser in English (LTR) and Arabic (RTL), in light and dark themes; every screen has loading, empty,
forbidden, and error states; the axe gate, the direction matrix, and the Playwright journey pass in CI;
and every permission decision is still made by the API. Proof: `frontend/src/**/*.test.tsx`,
`frontend/e2e/journey.spec.ts`, and the frontend CI job.

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
- T6.4 Add draft-generation endpoint and the AI panels in the existing shell: classification (category,
  sentiment, suggested priority, rationale), draft with source article links, processing states with
  bounded polling, regenerate and retry, an editable field, and the explicit send action. The panels are
  bilingual and RTL from the start like every other surface (FR-021, FR-024, FR-035).
- T6.5 Enforce human approval; no automatic public sends.
- T6.6 Add AI evaluation fixtures and usage limits.
**Exit:** ticket creation works without LLM; AI draft is generated and safely reviewed.

## Phase 7 — Knowledge base and RAG
- T7.1 Article CRUD and publication lifecycle.
- T7.2 Chunking and indexing pipeline.
- T7.3 Implement PostgreSQL full-text search first or `pgvector` if embeddings are in scope.
- T7.4 Tenant-scoped retrieval and source citations.
- T7.5 Prompt-injection and cross-tenant retrieval tests.
- T7.6 Knowledge base UI (FR-030, FR-033): article list and editor with draft, published, and archived
  state, the publish capability reflected per role, reindex status with its failure states, and a clear
  warning that only published content is used for retrieval.
**Exit:** draft references correct tenant-scoped published sources.

## Phase 8 — SLA and escalations
- T8.1 SLA policy and deadline service.
- T8.2 Public-response tracking.
- T8.3 Periodic deadline task and deduplicated escalation events.
- T8.4 Notification delivery with retry/idempotency.
- T8.5 SLA settings and escalation UI (FR-040, FR-045): policy editing per priority with the deadline
  rule stated in the form, validation against the service, and the manager escalation view with overdue
  state, remaining time, and escalation history.
**Exit:** simulated deadline causes exactly one correct escalation.

## Phase 9 — Hardening and deployment
- T9.1 Query review, indexes, N+1 tests or query-count checks where valuable.
- T9.2 Security headers, CORS/CSRF review, throttling, upload limits if uploads exist.
- T9.3 Dependency, secret, SAST and container scans.
- T9.4 Staging deployment, migrations, smoke tests, rollback instructions, and production email delivery for invitation links (provider credentials backend-only).
- T9.5 Seeded demo data, screenshots in both locales and both themes, architecture diagram, demo script.
- T9.6 Retention and deletion command implementing the documented policy (FR-054).
- T9.7 Frontend release hardening: production build served as an artifact with a bundle-budget check,
  container image, offline-safe fonts confirmed, an RTL/LTR and light/dark visual review pass, and the
  documented frontend rollback path.
**Exit:** CI green, staging demo reliable, documented known limitations.

## Scope rule

Do not start the next phase until the current phase's exit criteria pass. If a task discovers a specification conflict, stop and propose a spec change rather than silently inventing behavior.

## Frontend ordering rules

- No user-visible string outside a translation catalog, and no component styled before the token set
  exists: T4.2 before T4.5, T4.3 before any screen copy is written.
- Every screen added after T4.12 (T6.4, T7.6, T8.5) must land with its axe assertion and its catalog
  entries in both locales, because the direction matrix and parity test only cover what exists.
- A frontend feature is not done until the API path it depends on is documented in
  `04_API_CONTRACT.md`; the UI never invents an endpoint, a field, or a permission rule.
