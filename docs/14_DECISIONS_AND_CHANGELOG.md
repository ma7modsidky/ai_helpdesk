# 14 — Architecture Decisions and Changelog

Record material decisions using this template.

## ADR template

### ADR-NNN: Short title
- **Status:** proposed / accepted / superseded
- **Date:**
- **Context:** What problem or constraint prompted this decision?
- **Decision:** What are we choosing?
- **Alternatives:** What else was considered?
- **Consequences:** Benefits, costs, risks, migration impact.
- **Verification:** What tests/metrics will validate the decision?

## Initial decisions

### ADR-001: Modular monolith
- **Status:** accepted
- **Decision:** One Django application with domain modules and separate Celery workers.
- **Reason:** Fast iteration, easier local development, clear boundaries without distributed service overhead.
- **Revisit when:** Independent scaling/deployment needs are measured.

### ADR-002: Human approval for AI replies
- **Status:** accepted
- **Decision:** AI produces drafts only; a separate authorized action publishes a reply.
- **Reason:** Reduce risk from hallucinations, prompt injection, and inappropriate messages.

### ADR-003: PostgreSQL is source of truth
- **Status:** accepted
- **Decision:** Persistent business state lives in PostgreSQL. Redis is a cache/fast-state component, not the only copy of important business data.
- **Reason:** Transactional consistency and recoverability.

### ADR-004: RabbitMQ as Celery broker
- **Status:** accepted
- **Decision:** RabbitMQ carries async task messages; Celery executes task logic; Redis is used only for explicitly defined cache/result/throttling needs.
- **Reason:** Clear separation of responsibilities and direct demonstration of the requested stack.

### ADR-005: Elapsed-time SLA for MVP
- **Status:** accepted
- **Decision:** Calculate deadlines using elapsed minutes in the first release.
- **Reason:** Avoid the complexity of business calendars until the end-to-end workflow is proven.
- **Consequence:** UI and docs must clearly state this limitation.

### ADR-006: Layered settings package
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** Local development, tests, and production need different debug flags, cookie security, and password hashing without duplicating configuration. A single settings module makes it easy to ship production with development defaults.
- **Decision:** `config/settings/{base,dev,test,prod}.py`. `base.py` owns shared configuration and all environment reads; `dev`/`test`/`prod` override only what differs. `prod.py` raises `ImproperlyConfigured` when `DEBUG` is enabled, `DJANGO_SECRET_KEY` is missing or still the example placeholder, `DJANGO_ALLOWED_HOSTS` is empty, or the database password is empty. `test.py` uses a fast password hasher for speed only.
- **Alternatives:** One module switched by env flags (rejected: no safe production defaults); separate settings files copied per environment (rejected: drift).
- **Consequences:** New configuration must be added in `base.py` plus any environment that differs. Production cannot start insecurely by accident.
- **Verification:** `apps/common/tests/test_settings.py` imports production settings in isolated subprocesses and asserts each refusal and the HTTPS/cookie defaults.

### ADR-007: Standard-library environment parsing
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** The backend needs a handful of typed environment values and must fail fast without echoing secrets.
- **Decision:** A small `config/env.py` with `env_str`, `require`, `env_bool`, `env_int`, `env_list`, and a development-only `load_dotenv`. No third-party environment library.
- **Alternatives:** `django-environ` or `pydantic-settings` (rejected: extra dependency for behavior we need in ~90 lines); raw `os.environ` at call sites (rejected: duplicated, inconsistent validation).
- **Consequences:** Error messages name the variable and never print its value. `.env` loading is opt-in for development and test settings only; production reads real environment variables. Revisit if we need URL-style DSNs or many more variables.
- **Verification:** `apps/common/tests/test_env.py` covers missing, empty, invalid, quoted, and precedence behavior, including that values never appear in error text.

### ADR-008: Session-cookie authentication for the SPA
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** The API must authenticate a React SPA without introducing token-storage risks or an avoidable dependency, and permission revocation must be immediate.
- **Decision:** Django session authentication with CSRF protection (`SessionAuthentication` in DRF from T1.3). Session cookie is httpOnly and `SameSite=Lax`; CSRF cookie is httpOnly and the token is delivered to the client through a bootstrap endpoint rather than by reading the cookie. Development uses a Vite proxy and production serves SPA and API on one origin, so credentialed CORS is never enabled.
- **Alternatives:** `djangorestframework-simplejwt` (rejected: refresh/rotation/blacklist lifecycle plus `localStorage` exposure for no MVP benefit, since membership is re-checked server-side per request either way).
- **Consequences:** The API contract gains `GET /api/v1/auth/csrf/`, `POST /api/v1/auth/login/`, and `POST /api/v1/auth/logout/`, to be added to `04_API_CONTRACT.md` in T1.3. The frontend client must send `X-CSRFToken` and handle 401/403 without exposing raw errors. Login brute-force protection is DRF throttling only in MVP, with no account lockout; documented as a known limitation.
- **Verification:** T1.3/T2 API tests must cover unauthenticated access, CSRF rejection, and access loss after membership removal.

### ADR-009: Reopen policy
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** `03_DOMAIN_AND_DATA_MODEL.md` allows `resolved → open` only under a documented reopen policy, and no policy had been recorded.
- **Decision:** Agents and above may move `open`, `in_progress`, and `waiting_on_customer` between permitted states and may resolve. Reopening (`resolved → open`) is restricted to `owner`, `admin`, and `manager`; only `resolved → closed` may close a ticket, and `closed` is terminal in MVP. No free-text reopen reason in MVP; audit events record actor, previous status, and new status.
- **Alternatives:** Allow agents to reopen (rejected: silently invalidates resolution metrics and SLA history); disallow reopening entirely (rejected: contradicts the model's stated transition); a full reopen workflow with reasons and customer notifications (deferred past MVP).
- **Consequences:** Enforced in the T3.3 domain transition service as a pure function, not in a view. Reopening must not resurrect a satisfied first-response SLA. A repeat issue on a closed ticket becomes a new ticket.
- **Verification:** T3.3 unit tests enumerate the full allowed/denied matrix per role.

### ADR-010: Structured logs with request correlation
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** `FR-051` requires logs with request/correlation IDs and no secrets or unnecessary ticket content. Correlation must survive through service code without threading an identifier through every function.
- **Decision:** A `RequestIdMiddleware` binds a correlation ID to a `ContextVar` and echoes it in the `X-Request-ID` response header. A logging filter attaches it to every record. Output is single-line JSON by default (`DJANGO_LOG_FORMAT=console` for local readability), at `DJANGO_LOG_LEVEL`. Client-supplied IDs are honoured only when they match `[A-Za-z0-9._-]{1,64}`; anything else (spaces, newlines, overlong values) is replaced with a generated UUID hex, preventing log injection. Completion lines record method, path without query string, status, and duration.
- **Alternatives:** Third-party JSON logging package (rejected: ~60 lines of stdlib covers it); passing a correlation ID as a function parameter (rejected: invasive); trusting any inbound `X-Request-ID` (rejected: log injection and unbounded header content).
- **Consequences:** Task/celery correlation IDs are not implemented yet; the same pattern will extend to workers in T5.1. Log content rules are enforced by convention and review, not by the formatter.
- **Verification:** `apps/common/tests/test_request_id.py` and `test_logging.py` cover allowlist rejection, header round-trip, context cleanup, correlation on failure logs, exception propagation, JSON shape, and newline escaping.

### ADR-011: Supply-chain scanning tooling
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** `12_CI_CD.md` and `10_SECURITY.md` require dependency and secret scans on every pull request. Tool choice affects licensing, runtime, and how much of the repo is inspected.
- **Decision:** Dependency scanning uses `uv audit --locked`, which reads `uv.lock` and queries OSV — no additional dependency and no second lock file. Secret scanning uses the `gitleaks` binary pinned by version and sha256 in the workflow, run as `gitleaks git` over full commit history with `--redact`. `actions/checkout` fetches full history for that reason.
- **Alternatives:** `pip-audit` (rejected: does not read `uv.lock` natively, so it needs an export step); `gitleaks/gitleaks-action` (rejected: requires a paid license key once the repository belongs to a GitHub organization); `detect-secrets` (rejected: scans the working tree only, so secrets committed and later removed go unnoticed); `uv-secure` (rejected: duplicates what uv now provides).
- **Consequences:** `uv audit` is flagged experimental, so its invocation may need revisiting on uv upgrades. Scans require network access to OSV and GitHub releases. Findings must be fixed or ignored explicitly with a justification; the pytest upgrade to 9.1.1 was driven by this gate.
- **Verification:** The workflow is validated against GitHub's workflow schema and the scan commands were exercised locally (clean history scan, placeholder-only `.env.example`).

### ADR-012: JSON-only bodies and explicit CSRF enforcement
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** DRF views are CSRF-exempt, so login and logout need an explicit CSRF check. DRF's own check reads `request.POST`, which triggers body parsing, which in turn rejects any content type without a parser. Separately, DRF downgrades unauthenticated requests from 401 to 403 when the authenticator provides no challenge header, collapsing "log in" and "not allowed" into one status.
- **Decision:** `apps.common.csrf.enforce_csrf` wraps DRF's session CSRF check and raises a dedicated `csrf_failed` error; every state-changing request must send `Content-Type: application/json` (empty `{}` when there is no payload); `apps.accounts.authentication.SessionAuthentication` declares a `Session` challenge so unauthenticated requests stay 401.
- **Alternatives:** Allow form/multipart parsing (rejected: the contract is JSON and form parsing widens the surface); rely on Django's `CsrfViewMiddleware` (rejected: DRF views are exempt); accept DRF's 403 for anonymous clients (rejected: clients cannot tell "authenticate" from "forbidden", and `04_API_CONTRACT.md` specifies 401).
- **Consequences:** Logout requires a JSON content type even with no payload; a form-encoded request returns `415 unsupported_media_type`. Login is throttled at 10 attempts per minute using the default local-memory cache, which is per-process until a shared cache lands in T5.1.
- **Verification:** `apps/accounts/tests/test_auth_api.py` and `apps/common/tests/test_errors.py` cover the 401/403/415/429 paths, CSRF rejection, token rotation, and session teardown; the flow was also exercised over HTTP with a real server.

### ADR-013: Factories for test data and a branch-coverage floor
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** T1.4 requires factory fixtures and coverage, `11_TEST_STRATEGY.md` asks for a pragmatic baseline on domain code rather than a gamed global percentage, and `12_CI_CD.md` requires publishing a coverage report. Inline `Model.objects.create` setup would drift from the write path production uses and duplicate across tenant and ticket tests.
- **Decision:** Use `factory_boy`, with one `factories.py` per app under `apps/<app>/tests/` (`UserFactory` writes through `User.objects.create_user`). Measure branch coverage over `apps` plus `config/env.py` and `config/urls.py`, excluding migrations, tests, and process entry points. Settings modules are excluded because they are declarative and the production one is imported only inside test subprocesses. Floor is 90% against a measured 97%.
- **Alternatives:** Hand-written fixtures only (rejected: duplicated setup, and every new model adds another copy); `model_bakery` (rejected: calls `objects.create`, bypassing the manager invariants that `test_user_model.py` exists to guard); measuring `config/settings/prod.py` (rejected: only imported in a subprocess, so coverage would report 0% forever); setting the floor at the exact measured value (rejected: one uncovered error branch would fail unrelated builds).
- **Consequences:** Each new app adds a `factories.py` beside its tests; the floor should be raised as the codebase matures; new code arrives with tests or CI fails. Coverage of production settings stays invisible to coverage.py by design and is still asserted by `test_settings.py`.
- **Verification:** The suite reports 97% branch coverage with `--cov`; a deliberately higher floor exits non-zero, confirming the gate rather than only the report.

### ADR-014: Static typing with mypy and Django/DRF stubs
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** `12_CI_CD.md` lists type checks in the pull-request pipeline and the README's MVP-done list repeats it, but nothing enforced annotations. Django and DRF resolve most attributes dynamically, so a checker without stubs and plugins would either flood with false positives or check almost nothing.
- **Decision:** mypy in strict mode with `mypy_django_plugin` and `mypy_drf_plugin`; `[tool.django-stubs]` points the plugin at `config.settings.test`; CI runs `mypy .` after the format check.
- **Alternatives:** Pyright (rejected: no comparable Django ORM plugin, and it would add a Node toolchain to a Python-only job); checking only already-annotated files (rejected: leaves most of the code unchecked); adding `django-stubs-ext` as a runtime dependency with `monkeypatch()` in settings (rejected for now: every generic base this code parameterises — `BaseUserManager`, `ModelSerializer`, `DjangoModelFactory` — is already subscriptable in Django 5.2 and DRF 3.16, so it would ship a runtime package with no consumer; add it when a `ModelAdmin[_T]`-style base is actually needed).
- **Consequences:** A handful of narrow `type: ignore`s document places where third-party typing cannot express this project — `UserAdmin` is bound to `AbstractUser` while ours derives from `AbstractBaseUser` (so it cannot be parameterised at all), drf-spectacular ships an untyped extension base, factory_boy's declarations and metaclass `__call__` are untyped, the middleware attaches `request_id` dynamically, and a list is passed to a queryset-typed paginator in a test-only view. Tests use `UserFactory.create()` rather than calling the factory class for the same reason.
- **Verification:** `mypy .` reports no issues across 48 files; a deliberately invalid annotation fails the command, so the gate is proven rather than assumed.

### ADR-015: Workspace and membership as the tenancy primitive
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** T2.1 introduces the tenant boundary that every later table hangs off. `03_DOMAIN_AND_DATA_MODEL.md` defines `Workspace` and `Membership` with a unique `(workspace, user)` constraint and the roles `owner`, `admin`, `manager`, `agent`, and `FR-003`/`FR-004` require that access is decided by membership rather than by a client-supplied workspace ID. The model has to be correct before any ticket table references it, because a missing constraint cannot be backfilled once rows exist.
- **Decision:** A new `apps.organizations` app owns `Workspace` (UUID primary key, name, globally unique slug, IANA time zone validated through `zoneinfo`, JSON `settings`, `active`/`archived` status, timestamps) and `Membership` (workspace and user foreign keys with `CASCADE`, required role, `active`/`removed` status, `created_at`). Uniqueness is enforced by `unique_membership_per_workspace_user`; the allowlisted role, membership status, and workspace status are each additionally enforced by a database `CHECK` constraint. Authorization, workspace resolution, and the last-owner invariant are deliberately not implemented here — they belong to T2.2, which must consume these rows rather than duplicating the rule in views.
- **Alternatives:** A single `owner_id`/tenant column on `User` (rejected: the PRD requires one user in several workspaces with a different role in each); modelling roles as Django groups and permissions (rejected: groups are global objects, so a role could not differ per tenant, and `FR-003` checks membership); hard-deleting memberships instead of a status column (rejected: `03` specifies `status`, and revocation history is needed by audit and by T2.2's "removed membership loses access" tests); relying on `choices` alone without `CHECK` constraints (rejected: choices are validated only by forms and serializers, so a data migration or raw update could write a role nothing recognizes — an authorization-relevant silent failure).
- **Consequences:** Every tenant-owned model must carry a workspace foreign key or reach one through a parent, and every query added from T2.2 onward must filter on an authorized membership. Slugs are globally unique, so workspace creation must derive or reject collisions rather than silently suffixing. `archived` exists in the schema but its access semantics are decided in T2.2; nothing currently treats it specially. Changing a role or status value requires a migration, which is the intended trade for database-level validation. The `settings` JSON blob is intentionally schemaless until the features that read it are specified.
- **Verification:** `apps/organizations/tests/` covers UUID identity, defaults, unique slug, IANA validation (accepted and rejected names), the unique membership constraint, multi-workspace membership, required role, unknown role/status rejection by the database, and both cascade paths. The migration was applied to PostgreSQL and the unique and `CHECK` constraints were confirmed in the live schema (`\d organizations_membership`). Full suite: 128 tests, 97.67% branch coverage. No endpoint was added in this task, so "no endpoint trusts a workspace ID alone" is enforced from T2.2 onward.

### ADR-016: Workspace access is resolved through membership, never through an ID
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** T2.1 created workspace and membership rows; T2.2 has to decide how a workspace identifier becomes access, what the four roles mean relative to each other, and how refusals are expressed. `FR-003`/`FR-004` require membership and role checks on every protected operation, `04_API_CONTRACT.md` says cross-tenant requests should return 404 rather than reveal existence, and `T2.2` makes negative cross-tenant tests a security gate. Several later services (tickets, knowledge base, SLA) will all need the same rule, so it must exist once rather than per view.
- **Decision:** A domain service in `apps/organizations/services.py`. `resolve_workspace_access` performs one query joining membership to workspace and returns a `WorkspaceAccess(workspace, membership)` only when the membership is active, the workspace is active, and the user account is active; otherwise it raises `WorkspaceNotFound`. `require_role` builds on it and raises `InsufficientRole(required=...)`. Roles are compared through an explicit rank table (`agent` 10, `manager` 20, `admin` 30, `owner` 40) rather than the enum's declaration order, and an unrecognized stored role raises instead of defaulting to a low rank. `accessible_workspaces` returns the active workspaces a user may list. Exceptions live in `apps/organizations/exceptions.py`, subclass `WorkspaceAccessError`, and carry no request or DRF dependency, so workers and management commands can use the same rules; the API layer maps them to 404 and 403 when endpoints arrive in T2.3.
- **Alternatives:** Checking membership inside each view or permission class (rejected: the rule would be re-implemented per endpoint and eventually forgotten, which is exactly the failure T2.4 tests for); Django groups and permissions (rejected: they are global objects, so a user could not hold different roles in different tenants); raising 403 for a foreign workspace (rejected: it turns the endpoint into an existence oracle, contradicting the contract's 404 guidance); treating an archived workspace as still readable (rejected for now: no archive feature is specified yet, so the safe default is that it is not addressable; this is one query to revisit); defaulting an unknown role to `agent` (rejected: a silent privilege decision should fail loudly); a `Workspace.objects.visible_to(user)` manager method (rejected: hidden in manager chains it reads as a filter rather than an authorization boundary, and it cannot express role requirements).
- **Consequences:** Every tenant-owned endpoint added from T2.3 must call `require_role` — or `resolve_workspace_access` where any member may act — and map the two exceptions to 404/403; a missing call is a cross-tenant hole, so T2.4 must add a negative test per resource. Adding a role requires both the `CHECK` constraint migration and an entry in `_ROLE_RANK`. Archived-workspace semantics change in one place. `accessible_workspaces` prefers `.distinct()` over a subquery, which is fine at MVP scale but should be measured once membership counts grow.
- **Verification:** `apps/organizations/tests/test_access_service.py` covers resolution for all four roles, the 16-cell role hierarchy matrix, removal, archived workspaces, deactivated users, unknown ids, an unknown stored role, list scoping, and the negative cross-tenant cases (a member of one workspace cannot resolve another, and a stranger learns nothing from the error text). `apps/organizations` is at 100% coverage; the full suite is 162 tests at 97.86%.

### ADR-017: Capability-based endpoint authorization and membership management
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** T2.2 gave the codebase a way to resolve a workspace and compare roles, but nothing consumed it: no endpoint existed, so the matrix was unenforced. `04_API_CONTRACT.md` lists workspace listing, creation, member listing, and member updates, and it requires 404 for cross-tenant objects, 403 for authenticated-but-forbidden, and a stable error envelope. The role matrix also needed a home that a new endpoint cannot silently bypass.
- **Decision:** Capabilities are declared in `services.Capability` with a per-role table, limited to the actions endpoints actually expose (`members.view` for every role, `members.manage` for owner and admin). A DRF permission class, `HasWorkspaceCapability`, resolves access once per request through `require_capability`, maps `WorkspaceNotFound` to 404 and `InsufficientRole` to 403, and stores the resolved `WorkspaceAccess` on the request so the handler cannot act on an object it did not authorize. Views only scope queries to that access. Shipping endpoints are `GET/POST /workspaces/`, `GET /workspaces/{id}/members/`, and `PATCH /workspaces/{id}/members/{membership_id}/`. Workspace creation writes the workspace and its first owner in one transaction. Membership changes are hierarchical: an admin may manage roles strictly below their own but cannot create a peer, touch another admin, or act on an owner; only an owner may grant owner; and any change that would leave no active owner returns 409 `conflict`.
- **Alternatives:** A database-backed role/permission table (rejected at MVP scale: four roles and two capabilities, no runtime administration requirement, and every check would gain a join for a matrix that ships with the code); inline role comparisons in each view (rejected: the duplication T2.2 exists to remove, and it fails closed only if every author remembers); returning 403 for a foreign workspace (rejected: it confirms the tenant exists); letting admins manage peers (rejected: an admin could demote the other admin and then act unopposed); deleting membership rows on removal (rejected: audit history and the status semantics T2.2 tests); implementing the invitations endpoint now (rejected: no invitation model or token lifecycle is specified yet, and a half-built invite flow is worse than none).
- **Consequences:** A new workspace-scoped endpoint that forgets `HasWorkspaceCapability` or `required_capability` raises `ImproperlyConfigured` rather than defaulting to allow, and T2.4 must add the matching cross-tenant test. Reactivating a removed membership is possible by an admin because `status` is a lifecycle flag; that should be revisited when invitations land. A slug collision that slips past serializer validation between two simultaneous requests still surfaces as a database `IntegrityError` — a known race to close when workspace creation sees real traffic. Capabilities grow one endpoint at a time; none are declared ahead of use.
- **Verification:** 204 tests at 98.70% coverage, with `apps/organizations` at 100%. API tests cover unauthenticated 401, non-member 404 (including a removed member and a member of another workspace), 403 for an agent attempting a role change, 403 for a role change without a CSRF token, 403 for an admin creating a peer or touching another admin or an owner, 400 for empty/unknown/invalid input, 409 for the last owner, 404 for a membership addressed through the wrong workspace, and re-verified that revocation immediately ends the target's access. `GET /api/v1/schema/` still passes drf-spectacular's validator with the new routes.

## Changelog
Add dated entries as features or specs change. Keep this file concise; detailed implementation notes belong in pull requests.

- 2026-10-25: T2.3 workspace endpoints and authorization. Added `GET/POST /api/v1/workspaces/`, member listing and member role/status updates, a capability matrix enforced by `HasWorkspaceCapability`, transactional workspace creation with an owner membership, the role hierarchy and last-owner rule, and 42 tests including cross-tenant negatives. Recorded ADR-017.

- 2026-10-25: T2.2 workspace access service. Added membership resolution, an explicit role hierarchy with `require_role`, `accessible_workspaces`, and domain access exceptions; covered by 34 tests including the full role matrix and negative cross-tenant cases. Recorded ADR-016.

- 2026-10-25: T2.1 tenancy models. Added `apps.organizations` with `Workspace` (UUID, globally unique slug, validated IANA time zone, JSON settings, active/archived) and `Membership` (owner/admin/manager/agent, active/removed, unique per workspace and user, `CHECK` constraints), plus factories and 24 model tests. Recorded ADR-015.

- 2026-10-25: Phase 1 closeout. Backfilled the T1.2 and T1.3 backlog entries, corrected the documented coverage scope in the README, added `DJANGO_CSRF_TRUSTED_ORIGINS` to `.env.example`, made CI apply migrations to its database explicitly, and replaced an inert `CORS_ALLOW_CREDENTIALS` setting with a note explaining why no CORS configuration exists.

- 2026-10-25: Type checking. Added mypy in strict mode with django-stubs and DRF stubs, annotations across models, serializers, views, admin, middleware, and the test suite, and a CI `mypy .` step. Recorded ADR-014.

- 2026-10-25: T1.4 test infrastructure. Added `factory_boy` fixtures writing through the model managers, branch coverage over application code with a 90% floor against a measured 97%, a `coverage.xml` artefact in CI, and the backlog entry that defines the task. Recorded ADR-013.

- 2026-10-25: T1.3 API foundation. DRF mounted at `/api/v1/` with URL path versioning, session authentication, a uniform error envelope carrying the request ID, bounded pagination, login throttling, and an OpenAPI 3 document at `/api/v1/schema/`. Added `GET/POST /auth/csrf|login|logout|me` and documented them in `04_API_CONTRACT.md`. 104 tests passing. Recorded ADR-012.

- 2026-10-25: Supply-chain gates in CI. Added `uv audit --locked` and a pinned, checksum-verified gitleaks history scan to `backend-ci.yml`. Upgraded pytest 8.4.2 to 9.1.1 because the audit gate flagged CVE-2025-71176 in the pinned version; suite re-run green. Recorded ADR-011.
- 2026-10-25: T0.4 CI skeleton. `.github/workflows/backend-ci.yml` installs from `uv.lock` and runs ruff lint/format, Django checks, migration consistency, and pytest against a PostgreSQL 16 service. Frontend jobs and container builds are deferred until those targets exist.
- 2026-10-25: T1.2 logging. Structured JSON logging with request correlation IDs, `X-Request-ID` handling, and request completion lines; 76 tests passing. Recorded ADR-010.
- 2026-10-25: T1.1 backend foundation. Django 5.2 project with layered settings, custom `accounts.User` (UUID primary key, email login), `/health/live/` and `/health/ready/`, datastore-only Compose services, `.env.example` placeholders, and 43 passing tests. Recorded ADR-006 to ADR-009.
