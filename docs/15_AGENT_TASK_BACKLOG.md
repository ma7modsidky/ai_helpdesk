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

## T4.1 — Frontend project, tooling, and gates
**Goal:** Create the `frontend/` workspace: Vite + React + TypeScript in strict mode, pnpm with a committed lockfile, ESLint (type-aware, flat config) and Prettier, Vitest with Testing Library and jsdom, and the CI job that runs them.
**Acceptance:** `pnpm install --frozen-lockfile` then `lint`, `format --check`, `typecheck`, `test`, and `build` all succeed from a clean checkout and in CI; strict mode forbids implicit `any` and unsafe index access; the dev server proxies `/api` to Django so no CORS configuration is required; a Compose `frontend` service serves the dev server against the local API; `VITE_API_BASE_URL` is documented in `.env.example` and is the only build-time variable; the CI job uploads the build artifact and fails on any non-zero step; `.gitignore` excludes `node_modules` and build output.
**Out of scope:** product screens, theming, translations, end-to-end tests.
**Must read:** frontend spec, CI/CD spec, ADR-030.

## T4.2 — Design system and theming
**Goal:** Establish the token layer and light/dark themes so no screen has to invent colours, spacing, or typography.
**Acceptance:** light and dark are defined together through MUI's `colorSchemes` over CSS theme variables and switch without re-rendering the app; the default follows the operating system, the choice persists, and `index.html` applies the stored mode before the bundle runs so there is no flash of the wrong theme; Latin and Arabic fonts are self-hosted with no runtime CDN request; text meets 4.5:1 and UI boundaries 3:1 in both modes; Arabic typography raises line height and drops letter spacing through a theme rule; status and priority tokens exist for every enum value and pair colour with a label; MUI component defaults cover buttons, inputs, chips, dialogs, and tables so screens do not restate props; loading, empty, error, forbidden, and conflict primitives exist and are covered by component tests; every focusable element has a visible focus ring.
**Out of scope:** screen implementation, charts, illustration assets.
**Must read:** frontend spec §2, §4, §8, ADR-031.

## T4.3 — Internationalization and RTL
**Goal:** Make the application bilingual with correct direction from the first screen.
**Acceptance:** `en` and `ar` catalogs exist for every namespace in use and a parity test fails when a key is missing from either; no user-visible string, `aria-label`, or empty-state text is hardcoded outside a catalog (lint-enforced in T4.11); locale resolves from `?lang=`, then `localStorage`, then `navigator.languages`, then `en`, and the choice persists; switching locale updates `html lang`/`dir`, the theme direction, and the Emotion cache together, with no reload and no layout flash; directional icons mirror and non-directional icons do not; dates, numbers, and relative times render through `Intl` with the active locale while numerals stay `latn`; a direction-matrix test renders each screen component in both directions; the resolved locale is tested for an unsupported value and for a missing catalog entry.
**Out of scope:** locales beyond `en` and `ar`, translation management tooling, right-to-left asset localisation.
**Must read:** frontend spec §3, ADR-031.

## T4.4 — API client and server-state layer
**Goal:** Provide one typed HTTP client and one server-state layer so every screen handles auth, errors, and caching the same way.
**Acceptance:** `fetch` is called in exactly one module; requests send session credentials and a CSRF token obtained from the CSRF endpoint and refreshed on rejection; the uniform error envelope becomes a typed error carrying status, code, message, request id, and field details, and network failures and non-JSON responses normalise to the same type; `401` clears session state and redirects to login with a return path, `403`, `404`, `409`, `429`, and `5xx` each follow the documented behaviour; the redirect target is validated against the route allowlist so it cannot leave the origin; query keys are workspace-scoped and writes invalidate the narrowest set of keys; polling is opt-in, bounded, and stops on a terminal state; no request or response body is logged; the client has unit tests for each status mapping, for the CSRF refresh path, and for the unsafe-redirect guard.
**Out of scope:** WebSockets, offline queueing, optimistic updates.
**Must read:** API contract, frontend spec §7, security spec.

## T4.5 — Authentication screens
**Goal:** Sign in, sign up, sign out, and session restoration, with the app's first bilingual screens.
**Acceptance:** sign-up and sign-in submit JSON with a CSRF token and show field-level errors from `error.details`; password requirements are read from the server's response rather than re-implemented; success lands signed in, with sign-up going to the workspace picker and its empty state explaining that an invitation grants access to an existing workspace; a page reload restores the session from the session endpoint without flashing an unauthenticated shell while it resolves; protected routes redirect unauthenticated visitors to login and return them to the attempted route afterwards; an expired session explains itself once and does not loop; both screens expose the language and theme controls; tests cover validation failure, wrong credentials, a throttled response, session restoration, and the redirect round trip.
**Out of scope:** password reset, email verification, social login, remember-me.
**Must read:** API contract, frontend spec §6.1, ADR-027.

## T4.6 — Invitation acceptance
**Goal:** Let an invited person see what they are joining and accept it.
**Acceptance:** `/invite/:token` renders the workspace name, offered role, and invitation state from the public preview before any action; an unauthenticated visitor is routed to sign in or register with the invited address preserved; a signed-in visitor with a different email is told clearly and offered a way to switch account; acceptance lands inside the workspace inbox; expired, revoked, accepted, and unknown tokens each have a distinct, honest message with no action that cannot succeed; the token never appears in a log line, an analytics event, or a `Referer`-bearing external request; tests cover every invitation state and the mismatched-account refusal.
**Out of scope:** creating an account on the invitee's behalf, invitation emails beyond what T2.6 sends.
**Must read:** API contract, frontend spec §6.2, ADR-026.

## T4.7 — Workspace picker and application shell
**Goal:** Give the app its navigation frame and a place to choose or create a workspace.
**Acceptance:** the picker lists every workspace with the caller's role, offers creation through a validated dialog, and has a distinct empty state for an account with no memberships; the shell provides the workspace switcher, a navigation list generated from the route table, the language and theme controls, and the user menu; the current workspace is visible at all times and switching workspaces rewrites the URL rather than hiding state; creating a workspace lands in its inbox; a workspace the user cannot see renders a not-found state and returns to the picker after the workspace list is refreshed; the shell is keyboard navigable with a skip link, and its navigation is tested in both directions so the rail mirrors correctly.
**Out of scope:** global search, notifications centre, workspace settings beyond membership.
**Must read:** frontend spec §6.3, API contract.

## T4.8 — Members and invitation settings
**Goal:** Administer a workspace's people from the UI, mirroring the server's rules instead of guessing them.
**Acceptance:** the member list shows role, status, and join date; role changes and revocation are offered only where the capability matrix allows and a server refusal is displayed rather than hidden; the last-owner refusal is explained in place; pending, expired, and accepted invitations show their state with resend and revoke, and the accept link is displayed exactly once at creation with a copy action; ownership transfer is offered only to the owner, requires choosing an active member, and confirms that the caller becomes an admin; tests cover a refused role change, the last-owner case, an expired invitation, and the transfer confirmation.
**Out of scope:** bulk import, member profiles, per-member notification settings.
**Must read:** API contract, frontend spec §6.4, ADR-026, ADR-028.

## T4.9 — Ticket inbox
**Goal:** The working surface: find, filter, and open tickets in the current workspace.
**Acceptance:** filters for status, priority, and assignee (`me`, `unassigned`, member), search on subject, and ordering are sent to the server using only allowlisted values, and are reflected in the URL so a view reloads and shares identically; search is debounced and the previous request is discarded rather than racing; pagination uses the contract's bounded page size and the total from `count`; rows show subject, requester, status and priority chips, assignee, and last update; loading uses a skeleton shaped like the list, and empty, filtered-empty, error, and retry states are distinct and tested; no data from another workspace can render after a workspace switch; the list is keyboard navigable and opens a ticket on `Enter`; axe passes in both directions.
**Out of scope:** saved views, bulk actions, virtualised scrolling, column customisation.
**Must read:** API contract, frontend spec §6.5, ADR-023.

## T4.10 — Ticket detail and conversation
**Goal:** Read a ticket, reply, leave an internal note, and change its state within the caller's capabilities.
**Acceptance:** the header shows subject, status, priority, assignee, requester contact, and timestamps with a breadcrumb to the inbox; the timeline renders public replies and internal notes with clearly distinct labels and treatment and never blurs them; the composer makes the visibility mode explicit and does not silently default; field edits send `If-Match` with the version that was read, and a stale version produces a "this ticket changed" prompt that reloads the ticket while preserving unsaved composer text; assignment and transition use the command endpoints and their legality comes from the server; controls are disabled with an explanation where the role lacks the capability, and a refusal is surfaced rather than swallowed; the audit panel lists the ticket's events when the endpoint exists; tests cover the conflict prompt, note versus reply rendering, a refused assignment, and an illegal transition.
**Out of scope:** SLA panel (T8.5), AI panels (T6.4), attachments, mentions.
**Must read:** API contract, frontend spec §6.6, ADR-009, ADR-021, ADR-022, ADR-029.

## T4.11 — Frontend test and accessibility gate
**Goal:** Make the accessibility and quality claims above enforceable rather than aspirational.
**Acceptance:** every screen component has an `axe-core` assertion in both directions and in both themes where colour is asserted; keyboard and focus tests cover dialogs, drawers, the composer, and the inbox list; a coverage floor is configured for `src/` and fails CI below it; the no-hardcoded-copy rule and the `dangerouslySetInnerHTML` ban are enforced by lint rather than review; the catalog-parity and direction-matrix tests are part of the default run; the production build is checked for the bundle budget and the check fails the CI job when exceeded.
**Out of scope:** visual regression snapshots, cross-browser matrix (Chromium plus one other browser in T9.7).
**Must read:** frontend spec §8, §11, test strategy.

## T4.12 — End-to-end journey in both directions
**Goal:** Prove the phase's exit criterion the way a user experiences it, in both languages.
**Acceptance:** a Playwright suite runs register → create workspace → invite → accept in a second session → create ticket → assign → reply → resolve, and is parameterised over `en` and `ar`; the Arabic run asserts `dir="rtl"` on the document, that key landmarks mirror, and that no catalog key leaks as a raw identifier; the suite runs against a seeded backend in CI on Chromium with traces retained on failure; a flaky or failing journey blocks the pipeline; the journey is documented as the manual demo script too.
**Out of scope:** full cross-browser coverage, visual diffing, performance profiling in the browser.
**Must read:** frontend spec §3.4, test strategy, CI/CD spec.

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

## T7.6 — Knowledge base UI
**Goal:** Let an authorized member manage articles and see how indexing is going.
**Acceptance:** article list and editor with title and body, draft, published, and archived state, and the publish capability reflected per role with a refusal surfaced rather than hidden; the editor warns that only published content feeds AI retrieval; reindex status shows queued, running, done, and failed with a retry path; unsaved changes are guarded before navigation; every string is catalog-backed and every state is tested in both directions; axe passes.
**Out of scope:** rich text, attachments, image upload, version history browsing.
**Must read:** frontend spec, API contract (knowledge endpoints), ADR-030, ADR-031.

## T9.7 — Frontend release hardening
**Goal:** Ship the frontend the way the backend is shipped: built, bounded, and reviewable.
**Acceptance:** the production build is produced in CI and served by a container image that proxies the API on one origin; the bundle-budget check from T4.11 is a required step with the measured size reported; fonts and icons are served from the build with no external request; the RTL/LTR and light/dark review pass is recorded with screenshots in both locales; a deployment and rollback note covers the static artifact and its cache headers; a second browser is exercised by the Playwright journey.
**Out of scope:** CDN configuration, edge caching, i18n beyond the two shipped locales.
**Must read:** frontend spec §9, §12, CI/CD spec.
