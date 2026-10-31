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
- **Consequences:** A new workspace-scoped endpoint that forgets `HasWorkspaceCapability` or `required_capability` raises `ImproperlyConfigured` rather than defaulting to allow, and T2.4 must add the matching cross-tenant test. Reactivating a removed membership is possible by an admin because `status` is a lifecycle flag; that should be revisited when invitations land. A slug collision that slips past serializer validation between two simultaneous requests was left surfacing as a database `IntegrityError`; ADR-019 closes that race. Capabilities grow one endpoint at a time; none are declared ahead of use.
- **Verification:** 207 tests at 98.70% coverage, with `apps/organizations` at 100%. API tests cover unauthenticated 401, non-member 404 (including a removed member and a member of another workspace), 404 for archived workspaces on both read and write, 401 for a deactivated account whose session stopped resolving, 403 for an agent attempting a role change, 403 for a role change without a CSRF token, 403 for an admin creating a peer or touching another admin or an owner, 400 for empty/unknown/invalid input, 409 for the last owner, 404 for a membership addressed through the wrong workspace, and re-verified that revocation immediately ends the target's access. `GET /api/v1/schema/` still passes drf-spectacular's validator with the new routes.

### ADR-018: Serialising membership changes on the workspace row
- **Status:** accepted
- **Date:** 2026-10-25
- **Context:** ADR-017's last-owner rule counted active owners and then wrote, so two administrators demoting the two remaining owners at the same moment could both pass the check and leave the workspace with none. An ownerless workspace is unreachable through the API, and no ordinary SQL constraint can express "at least one active owner" without a trigger. The permission decision also happened before the request reached the service, so a demoted admin's in-flight request still carried owner authority.
- **Decision:** `change_membership` runs in a single transaction that first locks the workspace row with `select_for_update`, and only then reads the actor's membership, the target membership, and the active-owner count. Because every membership mutation goes through this function, that row acts as a per-tenant mutex. The actor is re-read under the lock, so stale `WorkspaceAccess` no longer authorizes someone who has since been demoted or removed. Lock order is always workspace, then membership rows.
- **Alternatives:** Locking every owner row (rejected: it is a predicate over a set that can shrink, and with one owner there is nothing to lock); a database trigger or deferred constraint (rejected: "at least one of a set" needs procedural SQL that is hard to test and to keep portable); `SERIALIZABLE` isolation with retry loops (rejected: every caller would need retries and the blast radius covers unrelated queries); an in-process mutex (rejected: multiple workers and processes defeat it); advisory locks (rejected: extra key management for no gain over the tenant row).
- **Consequences:** Membership changes in one workspace serialize; acceptable because they are administrative and infrequent, while reads stay lock-free. Any future write path that bypasses `change_membership` loses the guarantee, so membership writes must remain in this service. A just-demoted admin's in-flight request now fails with 403 instead of acting on stale authority. Nothing long-running may be added inside the locked block, since it would hold up other administrators.
- **Verification:** `apps/organizations/tests/test_membership_concurrency.py` runs two threads on separate connections behind a barrier and asserts exactly one demotion succeeds, one is refused, and exactly one active owner remains. Removing `select_for_update` makes that test fail 5 out of 5 runs; restoring it passes 3 out of 3. Deterministic tests cover a stale owner after demotion, a workspace archived mid-request, and an actor removed mid-request. Suite: 211 tests, 98.71% coverage, `apps/organizations` at 100%.

### ADR-019: The unique index, not the serializer, decides a workspace slug
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** Workspace creation validated the slug with `ModelSerializer`'s `UniqueValidator` and then inserted. Two requests naming the same slug can both pass that check and race to insert; the loser got a raw `IntegrityError`, which the error envelope reported as a 500 `internal_error`. `04_API_CONTRACT.md` requires a duplicate slug to be a 400 validation error, and a 500 for ordinary user input is both wrong and noisy. A `CHECK`/unique index cannot be replaced by any amount of pre-checking: only the index can arbitrate a race.
- **Decision:** `create_workspace` keeps its transaction and wraps it in `except IntegrityError`, translating the violation into a domain error, `WorkspaceSlugTaken`. The view maps that to DRF `ValidationError({"slug": [...]})`, which produces the same envelope (`validation_error`) and the same field key as the serializer's own rejection, so a client cannot tell a lost race from an eagerly rejected slug. The serializer pre-check stays as the cheap, friendly path. The `except` sits outside the `atomic` block on purpose: the block must roll back before the connection is used again.
- **Alternatives:** Reserving the slug with a lock or a slug-registry row (rejected: an extra object and lock order to maintain for exclusivity the index already provides); `get_or_create`/`update_or_create` (rejected: it would silently adopt an existing workspace belonging to another tenant); generating a suffixed slug on collision (rejected: the client chooses the slug, and quietly rewriting it makes the URL they were given wrong); catching `IntegrityError` broadly around every write (rejected: real constraint bugs must stay 500 — this catch covers one insert path whose only unique column is the slug); `SERIALIZABLE` isolation for the create (rejected: wider blast radius than the problem, as in ADR-018).
- **Consequences:** A lost race now returns 400 and the losing request leaves nothing behind, because the workspace and its owner membership share the transaction. Non-HTTP callers (tasks, shell, tests) receive `WorkspaceSlugTaken` instead of a driver exception. The mapping attributes any `IntegrityError` on this insert to the slug, which is correct today because `slug` is the only unique column of a workspace being created and the membership written alongside it belongs to a brand-new workspace; adding another unique column to creation would require narrowing this catch, and the docstring says so.
- **Verification:** `apps/organizations/tests/test_workspace_concurrency.py` covers both halves: two threads on separate connections behind a barrier create the same slug (exactly one succeeds, one raises `WorkspaceSlugTaken`, one workspace and one owner membership exist), and an API test disables `UniqueValidator` so the request reaches the insert, asserting 400 `validation_error` with a `slug` detail and no half-written rows. Reverting the `except` to a non-matching type makes both tests fail with the original `IntegrityError`/500; restoring it passes. Suite: 213 tests, 98.73% coverage, `apps/organizations` at 100%.

### ADR-020: The requester is captured on the ticket, not as an account
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `03_DOMAIN_AND_DATA_MODEL.md` gave `Ticket` a `requester_id`, which implies a `User`. Customers are deliberately not workspace members, no portal is in scope, and `01_PRD.md` forbids a customer portal in MVP, so requiring an account per customer would create accounts for people who never log in — an onboarding wall, an identity surface to protect, and personal data with no purpose. `FR-011` still requires every ticket to name its requester.
- **Decision:** Three columns: `requester_email` (required, trimmed, lowercased), `requester_name` (optional) and `requester_user_id` (nullable FK). `requester_user_id` may only reference an active member of the same workspace; rejection is a `400 validation_error` with a message that does not depend on whether the user exists. There is no automatic linking by matching email. The email and name are the contact record shown on the ticket; editing a member's account email never rewrites historical tickets.
- **Alternatives:** Require a `User` per requester (rejected: accounts for customers, plus deletion and retention questions for inactive identities); one free-text requester field (rejected: unvalidated, cannot answer "what has this customer sent us", no place to put a name); a separate `Contact` model (rejected for MVP: no contact UI, no merge/dedupe rules; revisit with a portal); storing only the FK when present and nothing otherwise (rejected: silently loses the customer, which is the common case).
- **Consequences:** Requester email is personal data, so retention (FR-054, ADR-025) applies, and the rule against logging ticket bodies extends to it. "Same customer, many tickets" is a query, not a relation until a portal exists. A portal would link by verified email deliberately rather than implicitly. Ticket creation validates the optional FK, which is one extra membership lookup.
- **Verification:** T3.1 model tests (email required, lowercase normalization, invalid email rejected, non-member `requester_user_id` rejected) and T3.2 API tests asserting the generic 400 message for both a nonexistent user and a foreign member.

### ADR-021: Ticket capabilities, and visibility is workspace-wide
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** ADR-017 declared only `members.view` and `members.manage`, but Phase 3 adds creation, assignment, transitions, and two message visibilities. Without an explicit matrix, each view would invent its rule, which is exactly the failure T2.4 tests for. Nothing in the spec set said whether members see every ticket or only their own, and `FR-014` plus `10_SECURITY.md` require internal notes never to surface on a customer-facing path.
- **Decision:** `Capability` gains `tickets.view`, `tickets.create`, `tickets.comment`, `tickets.assign_self`, `tickets.assign_others` and `tickets.transition`, held by all four roles except `tickets.assign_others`, which requires manager or above. Visibility is workspace-wide: any active member reads any ticket, with no assignee-scoped rule. Every role may post either visibility; the flag is enforced when messages are read, not by role. Transition legality stays in the T3.3 domain service (ADR-009) rather than in the matrix.
- **Alternatives:** Separate `tickets.note` and `tickets.reply` (rejected: identical holders today, and it would encode a customer-facing role that does not exist); assignee-scoped visibility (rejected: managers must see the whole queue, and `07_FRONTEND_SPEC.md` describes a workspace inbox); restricting notes to managers (rejected: internal notes are a core agent tool); putting transition rules in the permission class (rejected: the matrix answers "may this endpoint be called" while the service answers "is this change legal"; merging them duplicates ADR-009).
- **Consequences:** A fifth role would be a table change plus a test for every new role × capability cell. Agents receive 403 when assigning a colleague, which the frontend must reflect from the same matrix rather than duplicating it. Internal notes are protected only on the read side, so a future customer surface must filter `visibility = "public_reply"` and needs its own test.
- **Verification:** T3.1/T3.2 test the full role × capability matrix (24 cells) plus route-level 403 and cross-tenant 404; T3.4 tests that a public-only reader never returns a note.

### ADR-022: Version plus If-Match for field edits, row lock for commands
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `03_DOMAIN_AND_DATA_MODEL.md` listed `version` as "if needed", which left the most common Phase 3 race — two agents editing one ticket — undefined, and left the frontend without a conflict story. ADR-018 established that writes depending on read state are serialised at the row those writes concern.
- **Decision:** `Ticket.version` is an integer starting at 1 and is returned in every representation. `PATCH` requires `If-Match: "<version>"`; the check and the increment are one statement (`filter(pk=…, version=n).update(version=F("version") + 1, …)`), so a zero-row update is the conflict signal, returned as `409 conflict` with the current version in `error.details.version`. `assign/` and `transition/` are commands: they lock the ticket row with `select_for_update`, validate against the current state, write, and bump the version; they do not take `If-Match`. Appending a message updates the ticket's `updated_at` but not its `version`. Ticket writes never take the workspace lock and membership changes never take a ticket lock, so the two lock domains cannot interleave.
- **Alternatives:** `If-Match` on every mutation (rejected: a client that just read a ticket would have to refresh before clicking resolve, and a command already names the state it wants); last-write-wins (rejected: silent overwrite of another agent's edit); a separate ETag table (rejected: the row already carries the counter); `updated_at` as the validator (rejected: a reply would fail a perfectly valid description edit); `412 Precondition Failed` (rejected: `409` is already in the contract and envelope, and the client cannot evaluate the precondition without the object anyway).
- **Consequences:** Every ticket write must go through the service or the counter drifts; serializers must not write model fields directly. `PATCH` cannot change status or assignee, which keeps one write path per kind of change. A 409 carries the current version so the UI can offer reload-and-reapply without a second request.
- **Verification:** T3.1 (default 1, no bump on message); T3.2 (two concurrent `PATCH` requests yield one 200 and one 409 reporting the version; a missing header is 409; concurrent transitions yield one legal change and one conflict).

### ADR-023: Deterministic, allowlisted ticket list queries
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `FR-016` requires ordering, but the contract's ticket list named only `status`, `priority`, `assignee`, `search` and `page`. Unconstrained ordering risks sorts on unindexed columns and schema leakage; an unstable sort makes pagination skip or duplicate rows; queue triage needs "mine" and "unassigned"; and a filter that validates UUID existence would become an oracle for other tenants' users.
- **Decision:** Filters combine with AND. `status` and `priority` take one value each, validated against the enum. `assignee` accepts `me`, `unassigned`, or a user UUID, where a well-formed UUID that is not a member matches nothing. `search` is a case-insensitive substring over `subject` only, trimmed, 1–100 characters. `ordering` accepts `created_at`, `updated_at`, `priority`, `status` with an optional `-` prefix, defaults to `-updated_at`, and breaks ties by `id`. Any invalid value is `400 validation_error`.
- **Alternatives:** `django-filter` (rejected: a dependency for five parameters that still would not provide the allowlist, tie-break, or 400 semantics); arbitrary `ordering` (rejected: sorts on unindexed or expression columns and reveals schema); search across description and messages (rejected for MVP on cost and content exposure, revisit with full-text in T7); `400` for a foreign assignee (rejected as an existence oracle); repeated/multi-value filters (deferred: the inbox can offer status views).
- **Consequences:** The allowlist lives in one constant so the error message, docs and tests cannot drift. `icontains` is the starting point; T9.1 measures whether a trigram or full-text index is needed. Adding a sortable field is an allowlist line plus an index check.
- **Verification:** T3.2 tests each allowed field and direction, every invalid value, page-boundary stability across ties, `me`/`unassigned`/foreign UUID behaviour, and search length bounds; T9.1 confirms the query plan against the documented indexes.

### ADR-024: Teams are out of MVP
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `03_DOMAIN_AND_DATA_MODEL.md` defined `Team` and gave `Ticket` a nullable `team_id`; the PRD's owner persona configured teams and `07_FRONTEND_SPEC.md` had a team control. No phase created a team, so the column would have existed with no product path, an unused index, and an unanswered permission question.
- **Decision:** No `Team` table, no `ticket.team_id`, and no team control or filter in MVP. The entity stays in `03` marked deferred so the design intent is not lost. Assignment targets a member. The PRD persona, non-goals, frontend spec and Phase 3 task text were updated to match.
- **Alternatives:** Build teams now (rejected: adds team CRUD, membership-in-team, filtering and permission semantics that no requirement tests); keep the nullable FK unused (rejected: invites accidental use and an index nobody needs); delete the entity from the docs (rejected: loses the intent and forces a rediscovery).
- **Consequences:** Re-adding teams is a table plus a nullable column with a null backfill. The PRD no longer promises team configuration, so the omission is explicit rather than implied. Queue- or group-based routing is post-MVP.
- **Verification:** A T3.1 model test asserts `Ticket` exposes no `team` field, and the specs are cross-checked so "team" appears only in the deferred note and this ADR.

### ADR-025: MVP cut line — analytics out, portal out, transfer and retention in
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** The Phase 2 audit (`16_PHASE2_AUDIT.md`) found four surfaces that were neither planned nor declared out of scope: `GET .../analytics/overview/` in the contract, the customer-portal persona, ownership transfer (required by `10_SECURITY.md`), and retention/deletion (also required by `10_SECURITY.md`). Each would otherwise be settled ad hoc, mid-implementation, by whoever touched it first.
- **Decision:** Analytics is removed from the contract and declared a non-goal. The customer portal is a non-goal: customers are contact data on tickets (ADR-020) and no customer-readable endpoint exists. Ownership transfer is in scope as T2.7 (`POST /workspaces/{id}/transfer-ownership/`, FR-006), an atomic swap under the same workspace lock as ADR-018 that leaves the workspace with an active owner. Retention is in scope as a documented policy enforced by T9.6 (FR-054): tickets and messages 24 months after the ticket's last update, audit events 24 months, AI job payloads and results 90 days, archived workspaces purged 90 days after archival by a manual command with `--dry-run` and no automatic purge, backups 30 days. Deletion logs counts, never content.
- **Alternatives:** Ship a thin analytics endpoint (rejected: no metrics, permission rule, or acceptance criterion were defined, which produces an untestable widget); allow portal read endpoints (rejected: a second auth surface, per-ticket visibility, and a note filter that each need their own tests); leave transfer as grant-then-demote (rejected: two writes that can leave zero owners if interrupted, and the security spec names the flow); leave retention undocumented (rejected: the security spec requires it, and "we keep everything forever" is a review finding).
- **Consequences:** No `apps/analytics` exists and the demo shows ticket lists and SLA state instead of charts. Transfer becomes one more Phase 2 endpoint, sequenced after invitations. The retention periods are MVP defaults that need review before any real customer data, and moving any surface back in requires a superseding ADR rather than a code change.
- **Verification:** T2.7 tests ownership transfer including two concurrent transfers; T9.6 tests `--dry-run` counts, the exact 24-month boundary, and that ticket cleanup leaves audit rows intact; the contract and PRD are checked to contain no analytics route.

### ADR-026: Invitations are hashed, expiring, single-use links
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `FR-005` requires inviting members and `04_API_CONTRACT.md` named `POST /workspaces/{id}/invitations/`, but no entity, token lifecycle, status set, or acceptance path existed — the gap the Phase 2 audit records as F-01/D-09. Three constraints shaped the design: `Membership.status` is `active|removed`, so "pending" had nowhere to live; ADR-010 logs the request path, so a token in a URL would land in logs; and ADR-017 deliberately deferred reactivation semantics "when invitations land". There is also no email provider configured, while the demo has to work from a clean checkout.
- **Decision:** A new `Invitation` row: `workspace`, `email` (trimmed, lowercased), `role` (`admin`, `manager` or `agent` — never `owner`), `invited_by` (`SET_NULL`), `token_hash` (unique), `status` (`pending`, `accepted`, `revoked`), `expires_at` (seven days), `accepted_at`/`accepted_by`, `delivery_status`, `created_at`/`updated_at`, with a partial unique constraint on `(workspace, email)` for pending rows. The token is 32 random bytes, stored only as SHA-256, single-use, and expiry is derived rather than stored so no job has to flip rows. No `Membership` is written until acceptance, and acceptance creates the membership with the invited role or reactivates a `removed` one. Workspace-side operations reuse the existing `members.manage` capability (owner and admin); the invitee endpoints are `POST /invitations/preview/` (public) and `POST /invitations/accept/` (session plus CSRF), both taking the token in the body. `accept_path` (the SPA route `/invite/<token>`) is returned only by create and resend. Delivery goes through Django's configured email backend with the outcome recorded in `delivery_status`, synchronously until Celery lands in T5.1, and idempotency comes from the 409 on duplicate pending invitations rather than an idempotency key.
- **Alternatives:** Reuse `Membership` with an `invited` status (rejected: every member list, count, and the last-owner arithmetic would have to exclude invited rows, and an expired invitation would leave a phantom member); store the token in plaintext (rejected: a database read becomes membership); put the token in the URL path or query string (rejected: ADR-010 logs the path, and URLs leak through referrers, browser history, and proxy logs); no expiry (rejected: a forwarded link becomes permanent access); allow inviting as `owner` (rejected: ownership moves only through T2.7, so a shared link must not be able to confer it); fail the request when delivery fails (rejected: the invitation is the durable record and resend is the retry path); a notification orchestration service such as Knock (considered through the service index and rejected for MVP: it requires connecting a downstream email provider anyway and adds a second template and credential surface, while Django's email backend keeps the transport configurable with no dependency).
- **Consequences:** Expired invitations need no scheduled job; revoke is the only way to retract an unused link and resend rotates it. `delivery_status` is diagnostic, not a state machine, and provider errors are logged by category rather than stored. Acceptance refuses to silently change a role when the invitee already holds an active membership with a different one, so privileges never move without an explicit members change. `PATCH members` still accepts `status: active`, which remains the documented restore path alongside acceptance. Because sign-up is unverified (D-10), anyone who registers the invited address can accept; invitations are revocable and short-lived, and email verification must be scheduled before public deployment. The frontend needs the `/invite/:token` route (D-16).
- **Verification:** T2.6 tests cover the database holding only a hash, list and detail responses never exposing the token or `accept_path`, the partial unique constraint blocking a second pending invitation while resend rotates and extends, `owner` rejected, mismatched email 403, expired 409, same-caller repeat 200, a removed membership reactivated with the invited role, revoke killing the token immediately, a delivery failure recorded without losing the invitation, both throttle scopes, archived workspaces, and cross-tenant access — all with the locmem email backend.

### ADR-027: Open self-registration with no workspace
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** `FR-001` requires authentication, but the API only had login: an account could only be created from a shell or `createsuperuser`, so the README's "create or join a workspace" journey was unreachable and invitation acceptance (ADR-026) had no way to produce the invitee's account. `D-10` left the rules open: whether sign-up is open or invite-only, whether it creates a workspace, and how verification is handled.
- **Decision:** `POST /api/v1/auth/register/` is public, requires `X-CSRFToken` (it starts a session), and takes `email` and `password`. The address is trimmed and lowercased, uniqueness is enforced by the existing column, and the password runs through `AUTH_PASSWORD_VALIDATORS` with a transient `User` so the similarity validator has the email to compare against. Success returns `201` with the same `{user, csrf_token}` body as login and signs the user in. The account is created through `User.objects.create_user` and gets no workspace and no membership. Failures are `400 validation_error` with `error.details`, so a duplicate address is a field error rather than a separate status. The endpoint is throttled at 10 attempts per hour per client (`auth_register`).
- **Alternatives:** Invite-only registration (rejected: no bootstrap path, and `Journey A` assumes a user can sign up); creating a personal workspace during sign-up (rejected: `D-10` keeps workspace creation an explicit act, and an empty workspace would pollute lists and analytics); returning `409` for a duplicate address (rejected: the contract's field-level details envelope is defined for `400`); automatically linking a pending invitation at registration (rejected: acceptance stays an explicit act, so the user sees which workspace and role they are joining); email verification now (deferred: it needs the same token machinery as invitations plus a provider, and is recorded as a pre-public-deployment requirement); resetting passwords (out of scope for MVP, tracked as a known gap).
- **Consequences:** A duplicate-address error confirms that an account exists; it is rate limited and the alternative is a worse sign-up experience, which is documented rather than hidden. Unverified addresses weaken invitation acceptance (ADR-026), so both limitations travel together. A new account has an empty workspace list, which the frontend spec must handle. Unused accounts are not garbage-collected: FR-054 covers content retention, not dormant identities, which stays an accepted MVP gap.
- **Verification:** `apps/accounts/tests/test_register_api.py` covers CSRF rejection, a successful sign-up that then reads `/auth/me/`, lowercased storage, duplicate and malformed addresses, weak passwords reported on the `password` field, no workspace or membership created, and the throttle returning `429`.

### ADR-028: Ownership transfer is one locked swap, not grant-then-demote
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** ADR-025 brought ownership transfer into MVP (`FR-006`) because `10_SECURITY.md` names the flow. Without a dedicated operation the only way to hand a workspace over was two `PATCH members` calls — grant the target `owner`, then demote yourself — which can fail between steps and leaves a window with two owners or, if the second call is lost, an abandoned owner. `members.manage` also admits admins, so the endpoint's permission layer alone cannot express "only the current owner may do this".
- **Decision:** A domain service, `transfer_ownership`, runs in one transaction that locks the workspace row (the same per-tenant mutex as ADR-018) and re-reads the caller's membership under that lock. It requires the caller to hold `owner` at that moment, requires the target to be an active membership of the same workspace, refuses a self-transfer, promotes the target before demoting the caller to `admin`, and returns both memberships. The route is `POST /workspaces/{id}/transfer-ownership/`, gated by `members.manage` so an admin reaches the owner check and receives 403 rather than a misleading 404.
- **Alternatives:** Two `PATCH members` calls (rejected: a partial failure leaves the workspace with two owners or none, and the client has to orchestrate an invariant the server should own); a new `owners.transfer` capability (rejected: the capability table answers "may this endpoint be called", while ownership is a rank test the service already performs under the lock, and duplicating it would let the two drift); allowing transfer to a removed membership (rejected: a removed member cannot act, so the workspace would be effectively ownerless); treating self-transfer as a no-op (rejected: hides a client bug and reports success without a change); demoting the caller to `manager` (rejected: they usually still administer the workspace, and `admin` keeps member management available to them).
- **Consequences:** Transfers serialize with membership changes and with each other, so two concurrent handovers cannot both succeed; the loser is refused with 403 because the caller is no longer an owner. The caller always ends as `admin`, never removed, and the target's previous role is replaced rather than remembered, so a later step-down is an ordinary membership change. Ownership still never travels through an invitation (ADR-026).
- **Verification:** `apps/organizations/tests/test_ownership_transfer.py` covers the resulting roles and single-owner invariant, co-owner handover, owner-only enforcement (admin 403, manager/agent 403), non-member 404, foreign membership 404, self-transfer 400, removed target 409, archived workspace 404, missing CSRF, malformed body, and stale authority after demotion and after removal. `test_ownership_concurrency.py` runs two transfers from one owner on separate connections behind a barrier: exactly one succeeds, the other is refused, and exactly one active owner remains.

### ADR-029: Ticket field edits have their own capability, and every ticket write is audited
- **Status:** accepted
- **Date:** 2026-10-26
- **Context:** Phase 3's capability matrix in ADR-021 named view, create, comment, assignment and transition, but the contract also exposes `PATCH .../tickets/{id}/` for field edits, and no row covered it — an endpoint whose permission rule would have been invented by whichever view implemented it first. `10_SECURITY.md` separately requires audit records for assignment, status changes and public replies, and `FR-015` requires an append-only event stream, but no model or write path existed.
- **Decision:** `tickets.edit` is added to the matrix (amending ADR-021) and held by all four roles, matching who can already create, comment and transition; the route never borrows `tickets.view` or `tickets.comment`, so a future read-only or note-only role is a matrix edit rather than a new endpoint. Every ticket write records a `TicketEvent` in the same transaction as the change: `ticket.created`, `ticket.updated` (field names only), `ticket.assigned`/`ticket.unassigned` (previous and new assignee ids), `ticket.status_changed` (previous and new status) and `ticket.message_added` (message id and visibility). The actor is the authenticated member, `correlation_id` is the request id from the access log, and metadata never contains a body, an address or a name. Field edits compare and increment `version` in one `UPDATE`; assignment and transition lock the ticket row, validate against the state they read under that lock, and bump the version; appending a message moves `updated_at` only.
- **Alternatives:** Reuse `tickets.comment` for edits (rejected: a capability whose name no longer describes what it guards); reuse `tickets.view` (rejected: makes a read capability authorize writes); no audit until a later phase (rejected: `FR-015` and the security spec are Phase 3 requirements, and a retrofitted trail can never reconstruct what already happened); one table per event type (rejected: the queries are identical and the object is always a ticket for now); store before/after values in metadata (rejected: copies ticket content and requester details into a longer-lived table); throttle every ticket route (rejected: only creation adds rows on demand, so only it gets the `ticket_create` scope of 120 per hour).
- **Consequences:** Ticket writes must go through `services`; a serializer that wrote a field directly would skip both the version bump and the audit row. Roles are re-read inside each write, so a membership revoked mid-request is refused, but ticket writes never take the workspace lock, so they cannot block or be blocked by membership changes. Audit rows are readable through no endpoint yet and are retained 24 months. Membership, invitation and ownership-transfer changes are still unaudited: `10_SECURITY.md` requires role-change auditing, the model can carry it, and it is recorded here as the remaining gap to close in T9.2 rather than claimed as done.
- **Verification:** `apps/tickets/tests/` covers the 25 status pairs per role, the version-conflict statement under two concurrent edits, two concurrent resolutions, concurrent message appends, the full role × ticket-capability matrix, `If-Match` in quoted, unquoted, weak and malformed forms, and one audit event per write with identifiers only.

### ADR-030: Frontend stack, server state, and single-origin serving
- **Status:** accepted
- **Date:** 2026-10-27
- **Context:** `07_FRONTEND_SPEC.md` offered "React + TypeScript + Vite, or Next.js if SSR/routing is a specific learning goal" and deliberately left the component library, the server-state layer, the package manager, and the test runner unnamed. Phase 4 is starting, so those choices are about to be made implicitly by whichever screen is written first — the same failure mode ADR-021 and ADR-029 recorded on the backend, where an unnamed rule is invented at the point of use. The deployment question sits in the same gap: a separate origin for the SPA would require credentialed CORS plus `CSRF_TRUSTED_ORIGINS`, and `10_SECURITY.md` warns against wildcard credentialed CORS.
- **Decision:** A Vite single-page application: React + TypeScript (strict, with unsafe index access and exact optional properties as errors), **MUI** as the only component kit, Emotion as the styling engine with MUI's official RTL stylis plugin, React Router for routing with route-level code splitting, and **TanStack Query** for server state (justified concretely by list caching and invalidation after writes, URL-state pagination, and the bounded polling FR-024 needs for AI job state). No global state library: the server is the source of truth and local state is component state. pnpm with a committed lockfile, ESLint (type-aware, flat config) plus Prettier, Vitest with Testing Library and jsdom for component tests, axe-core for accessibility assertions, and Playwright (Chromium) for the end-to-end journey. The SPA is served on the **same origin** as the API in development (Vite proxy) and in deployment (the frontend container proxies `/api`), so no CORS configuration is added and `CSRF_TRUSTED_ORIGINS` stays empty.
- **Alternatives:** Next.js (rejected: nothing in the product needs SSR or server routing, it adds a second runtime to build, test and deploy, and the portfolio value is the domain model rather than a rendering strategy); leaving the kit unnamed until a screen demands one (rejected: that is how an app ends up with three button styles and no theme); Mantine or Chakra (rejected: credible RTL and theming, but MUI ships an official, MUI-version-matched RTL plugin, the deepest accessibility coverage, and the largest ecosystem for the tables, drawers and pickers this product needs); Tailwind plus bespoke components (rejected by the same reasoning in reverse: it maximises styling work for a team of one and re-implements accessibility that MUI already tests); a global store such as Redux or Zustand (rejected: caching, invalidation and pagination are server-state concerns, which is exactly what the query layer solves); hand-written query hooks (rejected: caching, deduplication, stale-while-revalidate and bounded polling would all be re-implemented, and that custom code is what bugs live in); Jest (rejected: a second transform pipeline alongside Vite); separate API origin with credentialed CORS (rejected: more moving parts, a looser browser security posture, and CSRF trusted-origin configuration for no product gain).
- **Consequences:** The initial bundle is the thing to watch, because MUI is a large dependency — hence named imports by path, route-level splitting, and the bundle budget that T4.11 enforces and T9.7 reports. Every screen composes theme defaults instead of restyling, and `features/*` may not import another feature's internals. Query keys are workspace-scoped, so a workspace switch cannot serve a cached list from another tenant. Serving on one origin means a deployment that later wants a separate CDN or origin must add CORS and CSRF configuration deliberately rather than discovering it in production. Login is a session cookie, so the app stores no token of its own.
- **Verification:** T4.1 proves the toolchain from a frozen lockfile in CI; T4.4 tests the client's status mapping, CSRF refresh and redirect guard; T4.9/T4.10 test the URL-state and invalidation behaviour; T4.11 fails the build when the bundle budget is exceeded; T9.7 builds the container image that serves the SPA and proxies the API on one origin.

### ADR-031: Bilingual UI with RTL from the first screen, and light/dark themes
- **Status:** accepted
- **Date:** 2026-10-27
- **Context:** The product direction is an English **and** Arabic interface with right-to-left layout from the start, a professional visual language, and both light and dark themes — none of which any document required: `01_PRD.md` had no localization or theming requirement at all, and `07_FRONTEND_SPEC.md` implicitly assumed English-only, single-theme screens. RTL is not a stylesheet flip: direction changes layout order, icon orientation, scroll behaviour, component internals (drawer anchor, tab scrolling, autocomplete placement, tooltip offsets), and typography. Retrofitting it after a dozen screens exist means editing all of them and re-reviewing all of them. The locale's storage location was also open: a per-user column on the server, or client-side only.
- **Decision:** Two shipped locales, `en` (LTR) and `ar` (RTL), with the architecture able to accept more. **i18next + react-i18next** catalogs are the only source of user-visible copy — including labels, placeholders, `aria-label`s and empty-state text — and a parity test fails when the two catalogs disagree. Locale resolution is `?lang=` → `localStorage` → `navigator.languages` → `en`, persisted client-side; the API stays locale-agnostic and gains no column (client-only, as chosen). Direction is applied in exactly one provider that updates `html dir`/`lang`, rebuilds the MUI theme with `direction`, and swaps the Emotion cache for the RTL one built with MUI's RTL stylis plugin; app code uses logical CSS properties, mirrors directional icons through a single `DirectionalIcon` component, and keeps numbers and timestamps in a consistent order. Typography is self-hosted Inter Variable (Latin) and Noto Sans Arabic Variable (Arabic) in one stack, with Arabic line-height compensation and no letter spacing applied as a locale rule in the theme. Dates, numbers and relative times go through `Intl` with `latn` numerals by deliberate choice, matching regional business-software practice. Themes: light and dark are declared together through MUI's `colorSchemes` over CSS theme variables, the default follows the operating system with a persisted three-state control, and an inline script in `index.html` applies the stored mode before the bundle runs so there is no flash of the wrong theme.
- **Alternatives:** a per-user `locale` column and API field (rejected for MVP: a migration and a contract change for a presentation preference no requirement depends on; the cost is recorded rather than hidden — invitation and notification emails stay English until a server-side locale exists); locale in the URL path (rejected: it would complicate every route and share link, while `?lang=` covers deep-linking a language); `dir` on the element without `theme.direction` and the RTL cache (rejected: MUI's own components would keep LTR internals, producing mirrored-looking but subtly broken widgets); a mirrored second stylesheet with physical properties (rejected: two sources of truth that drift, and every future rule duplicated); keeping English-only and translating later (rejected: direction touches every layout, so the cost only grows); shipping dark mode later (rejected: colour tokens would be retrofitted across every component, and a single-theme palette tends to encode assumptions that break in the other mode); MUI's `palette` API with a hand-rolled mode switch (rejected: `colorSchemes` gives system detection, cross-tab synchronisation and zero re-render, all of which hand-rolled state would have to reproduce); Arabic as a right-to-left-only variant with Latin as the default fallback order (rejected: the fallback must follow the user's browser, not a fixed priority).
- **Consequences:** Every new screen after T4.12 must land with both catalogs, its direction-matrix coverage and its axe assertion, or the gates stop covering it — which is why `08_IMPLEMENTATION_PLAN.md` states that rule for T6.4, T7.6 and T8.5. A third locale becomes a catalog plus a direction entry rather than a refactor. Contrast has to be reviewed twice, in both themes. The Arabic copy in these catalogs is authored during implementation and must be reviewed by a native speaker before any demo or public deployment; it is not machine-translated at runtime. `latn` numerals are a product decision that a future locale may revisit. Emails remain English. Because the locale is client-only, two devices can show the same account in different languages, which is intentional.
- **Verification:** a catalog-parity test over `en`/`ar`; a direction-matrix test rendering each screen component in both directions; axe assertions in both directions; formatter tests for `Intl` output and `latn` numerals; T4.12 runs the end-to-end journey once per direction and asserts `dir="rtl"` and that no catalog key leaks as a raw identifier; T9.5 records screenshots in both locales and both themes.

### ADR-035: A strict classification schema, and a job row per ticket version
- **Status:** accepted
- **Date:** 2026-10-31
- **Context:** T6.2 is the first place untrusted model output would touch stored data. Three
  questions had to be answered before writing it: what a classification is allowed to say, where
  its status lives, and what happens when a ticket is edited while the work is queued. ADR-033
  already put task state in the database with a text key; a classification needs typed fields and a
  ticket relationship that the API's status endpoint can read in one query.
- **Decision:** `apps/ai_assistant/schemas.py` owns the output contract: exactly five keys, an
  allowlisted sentiment, a `suggested_priority` drawn from `TicketPriority`, a confidence in
  `[0, 1]` that rejects `NaN`, `Infinity`, and booleans, and a rationale bounded to one short
  sentence. Unknown keys are refused rather than ignored, because they mean the model answered a
  different question. `category` is checked by shape, not by allowlist: workspaces name their own
  categories (`Ticket.category` is free text), while the enum the system owns stays pinned. Jobs
  live in `TicketClassification`, unique on `(ticket, ticket_version)`, holding status, attempts,
  provenance, and the validated fields; the workspace is copied from the ticket so no caller can
  file a job under another tenant. A prompt edit carries `CLASSIFICATION_PROMPT_VERSION` with every
  result. The row is per version, so an edit queues a new job and the old answer keeps referring to
  the text it described; a worker that reaches superseded text finishes the job without calling the
  model. Dispatch is `get_or_create` plus `enqueue`, so a retried request, a redelivered message, and
  two workers racing converge on one execution; a claim moves the row only from `pending` or
  `failed`.
- **Alternatives:** Reusing `TaskRecord.result` for the typed fields was rejected: the API's status
  endpoint would have to find the row by a `LIKE` over a text key, and nothing would stop two
  differently-shaped results from sharing a column. Storing the raw model text and validating at
  read time was rejected: an invalid row would then be indistinguishable from a valid one whose
  fields happened to be empty. Allowing an arbitrary `category` string was rejected because a model
  can then emit a sentence, which no filter or report can use. Applying the suggestion to
  `Ticket.category` automatically was rejected on ADR-002's principle: AI output is untrusted, and a
  human decides what a ticket says. Keeping one job per ticket (overwritten on edit) was rejected
  because the UI could then show a suggestion for text nobody is reading.
- **Consequences:** A classification is a suggestion, never a write path: nothing here changes a
  ticket, so the API's AI panel can present it for approval without a second review mechanism. Each
  edit costs one more provider call, which is the price of never displaying a stale answer. Because
  the row is keyed by version, reclassifying the same version is impossible by design; a manual
  retry re-runs a `failed` row. AI work is not visible to the `task_status` command, which counts
  `TaskRecord` rows — the operator view for these jobs is the workspace/status index, and closing
  that gap is the honest cost of typed results.
- **Verification:** `test_schemas.py` covers every rejection path (unparseable, wrong shape, unknown
  key, invented enum, out-of-range and non-finite confidence, long rationale) and asserts a refusal
  never quotes the response; `test_prompts.py` asserts the text is bounded, that ticket text cannot
  close its data block, and that the instructions name it as data; `test_classification.py` asserts
  the validated answer is stored with provenance, one job per version, that an edit produces a new
  job, that a duplicate delivery is skipped, that superseded work never calls the model, that
  invalid output is recorded without a retry while a timeout is left for retry, that another
  tenant's ticket is refused, and that a ticket is still created when the queue is unavailable.

### ADR-034: One provider adapter, fake first
- **Status:** accepted
- **Date:** 2026-10-31
- **Context:** Phase 6 is the first code that calls a model. Two failure modes follow from doing
  that naively: a test suite that needs a key and a network (so CI is neither offline nor
  deterministic), and prompt-construction logic tangled with one vendor's request format (so the
  fourth provider is a rewrite). `05_AI_AND_RAG_SPEC.md` already requires an adapter, explicit
  timeouts, bounded retries, and a fake provider for tests; nothing yet said what the interface is
  or where the retry decision lives.
- **Decision:** A single narrow interface, `AIProvider.complete(CompletionRequest) -> Completion`,
  with `name`, `model`, and `timeout_seconds` on the adapter. Prompts and output schemas are built
  by the calling code (T6.2), so the adapter knows nothing about tickets. Errors are modelled by
  type and carry a `retryable` flag: timeout, unavailable, and rate-limited are transient;
  `AIResponseInvalid` is permanent, because the same prompt fails the same way. Adapter messages are
  written in `providers.py` and never copy provider text, which can quote the prompt. The provider
  is selected by `AI_PROVIDER` from a name registry, and the deterministic `FakeAIProvider` is the
  only adapter in the MVP — scripted responses and an injectable failure make both the happy and
  the failure paths testable, with no network and no credential.
- **Alternatives:** Calling a vendor SDK directly from the task is less code now and couples
  classification, drafts, and evaluation to that vendor. A single `generate(prompt) -> str` interface
  would hide provenance and latency, which FR-026 requires storing. Auto-retrying inside the adapter
  was rejected: the task owner decides what a duplicate execution means (ADR-033), and an adapter
  that sleeps holds a worker slot without the queue knowing. Shipping a real vendor in this task was
  rejected because CI must not need a key, and a fake that returns fixed text would make every
  downstream test vacuous.
- **Consequences:** Classification and drafts are validated in application code, so a provider that
  returns plausible prose but bad JSON fails safely (T6.2). The demo and CI run entirely on the fake
  adapter, which means the MVP demonstrates the flow rather than the model's quality; evaluation
  fixtures (T6.6) and any real adapter remain out of scope until then, and that limitation must be
  stated rather than glossed. A real adapter's key is read from the environment inside the backend
  process and is never a build-time variable.
- **Verification:** `apps/ai_assistant/tests/test_providers.py` asserts selection and unknown-name
  failure, determinism across instances, scripted ordering, error typing and retryability, that error
  text never contains the prompt, that a completion reports provenance and latency, and that the fake
  provider works with `socket` disabled; `test_settings.py` asserts a non-positive timeout fails at
  import.

### ADR-033: Task state in the database, idempotency by key
- **Status:** accepted
- **Date:** 2026-10-31
- **Context:** ADR-032 left every task without a record of what ran, how often, and with what
  outcome, and D-08 had been open since the Phase 2 audit: the contract asks for "idempotency keys
  where duplicate execution would be harmful" but names no header or store. Celery's `acks_late`
  makes duplicate delivery normal, so a task that writes twice is a correctness bug waiting for a
  worker restart.
- **Decision:** Every unit of work has a `TaskRecord` (T5.2) unique on `(task_name,
  idempotency_key)`. The dispatcher derives the key from the work itself
  (`ticket:<id>:classify:v<version>`) and calls `dispatch_once`; a second call with the same key
  queues nothing and returns `None`. The worker claims the row with a conditional update from
  `pending` or `failed`: finished work is skipped, a retry is allowed, and two workers receiving the
  same message cannot both claim it. `last_error` stores the exception class only; `result` holds a
  small validated payload, not a transcript. The table is the only task-state store — there is no
  result backend — and an HTTP `Idempotency-Key` header is **not** adopted in the MVP, because the
  only duplicate-execution risks today are queue deliveries, which the task key already covers.
- **Alternatives:** The contract's literal reading — `Idempotency-Key` plus a
  `(workspace, key, endpoint)` row storing the response — would make a repeated `POST` replay its
  first response, which no client needs yet and which adds a second state machine per endpoint.
  Relying on natural keys (`ticket_id`) instead of a derived key would make "reclassify after an
  edit" silently a no-op. A Redis result backend would answer "did it run?" until a restart, which
  is exactly when the question matters.
- **Consequences:** A dispatcher has to name its work; there is no default key, because a wrong
  default would either suppress real work or run it twice. Re-running failed work deliberately needs
  a new key or a Celery retry, not a re-dispatch — `failed` is a state the operator sees, not a
  queue. `TaskRecord` grows with every dispatched unit, so T9.6's retention policy must cover it.
- **Verification:** `apps/common/tests/test_task_records.py` covers one row per key, a refused
  second claim while running, an allowed retry after failure, a refused claim after success, the
  exception-class-only error field, one queued message per key, and the request id copied from the
  dispatcher; `test_celery.py` covers a duplicate delivery being skipped and a failure being
  recorded and requeued; `test_task_command.py` covers the status report and `--fail-on-stuck`.

### ADR-032: Celery wiring and task conventions
- **Status:** accepted
- **Date:** 2026-10-31
- **Context:** Phase 5 starts the asynchronous path. AI classification and drafts (Phase 6), article
  indexing (Phase 7), and SLA sweeps (Phase 8) all run outside a request. ADR-004 fixes RabbitMQ as
  the broker and Redis for explicitly chosen cache use, but nothing yet said where task state lives,
  how a task is retried, how it correlates with the work that queued it, or whether it may be
  published before its transaction commits.
- **Decision:** Celery is configured once in `config/celery.py`, reading Django settings through the
  `CELERY_` namespace, with autodiscovery from `apps/<app>/tasks.py`. There is no result backend
  (`result_backend` unset, `task_ignore_result` on): durable task state is a database row (T5.2), so
  no process depends on a result a worker restart would lose. Every task inherits
  `apps.common.tasking.CorrelatedTask`, which binds the Celery task ID to the logging context for the
  duration of the run — the task-side counterpart of `request_id`. Retries are bounded at three with
  a 30-second default delay and per-task backoff; `acks_late` with `reject_on_worker_lost` makes a
  killed worker redeliver rather than drop, which is why every task must be idempotent.
  `enqueue()` publishes with `transaction.on_commit`, never inside an open transaction. A shared Redis
  cache (`DJANGO_CACHE_URL`) lands with this task: optional locally, required in production, because
  LocMem throttling is per process.
- **Alternatives:** A Redis result backend would let callers poll `AsyncResult`, but it duplicates the
  audit trail in a store that empties on restart; a database row keeps one record and is what the UI
  needs to render processing states. Publishing at call time and retrying on failure is simpler than
  `on_commit`, but a worker can then read a row that a rollback deletes. A separate Celery
  configuration file would drift from Django's environment handling. Using `DjangoTransactionTask`
  from the Celery docs was rejected as more machinery than the MVP needs.
- **Consequences:** A task has no return value its caller can read; anything that must survive must
  be written by the task itself (T5.2). Anything enqueued has to be idempotent, because duplicate
  delivery is normal rather than exceptional. Development still needs only PostgreSQL: tasks run
  eagerly in tests and the cache falls back to LocMem, and `prod.py` refuses to start without a broker
  and a cache URL. The Compose worker and Beat services still wait on the backend image (T9.1), so
  today both are started by hand.
- **Verification:** `apps/common/tests/test_celery.py` asserts that the broker and task class come
  from settings, that discovery finds the smoke task, that a retryable failure becomes a `Retry`
  carrying its cause and that the bound re-raises instead of looping, that the task ID reaches the
  log record and the JSON line, and that `enqueue` publishes only after commit;
  `test_settings.py` asserts production refuses to start without `DJANGO_CACHE_URL` or
  `CELERY_BROKER_URL`.

## Changelog
Add dated entries as features or specs change. Keep this file concise; detailed implementation notes belong in pull requests.

- 2026-10-31: T6.2 AI classification, the first untrusted output to reach stored data. Added
  `apps/ai_assistant/schemas.py` (strict five-key contract, allowlisted sentiment, priority drawn
  from `TicketPriority`, confidence bounded and finite, bounded rationale), `prompts.py` (versioned
  `classify-v1` prompt, bounded input, requester identity withheld, ticket text fenced so it cannot
  close its block), `models.TicketClassification` (unique on `(ticket, ticket_version)`, status,
  attempts, provenance, validated fields), `runner.py` (conditional claim, success, class-only
  failure, supersede), and `tasks.classify_ticket` with `request_classification` (once per version,
  published after commit). Ticket creation queues the job and never fails with it. Recorded ADR-035.
  625 tests, 98.01% branch coverage.

- 2026-10-31: T6.1 AI provider adapter and deterministic fake, the start of Phase 6. Added
  `apps/ai_assistant` with `providers.py`: the `AIProvider` protocol (`complete(CompletionRequest) ->
  Completion`, plus `name`, `model`, `timeout_seconds`), typed request/result dataclasses carrying
  provenance and latency, modelled errors with a `retryable` contract (timeout, unavailable,
  rate-limited retryable; invalid output permanent), the deterministic `FakeAIProvider` with scripted
  responses and an injectable failure, and a name registry behind `AI_PROVIDER`. Settings add
  `AI_PROVIDER`, `AI_MODEL`, and `AI_REQUEST_TIMEOUT_SECONDS` (fail-fast on a non-positive value);
  no credential is read anywhere, so CI stays offline. Recorded ADR-034. 569 tests, 98.06% branch
  coverage.

- 2026-10-31: T5.2–T5.4 task state, harness, and observability, completing Phase 5. Added
  `apps.common.models.TaskRecord` (unique on `(task_name, idempotency_key)`, `CHECK` on status,
  indexes for the status report) and `apps/common/task_records.py`: `register`, `dispatch_once`
  (one message per key, after commit), `begin`/`start` (a conditional claim that refuses finished
  work and running duplicates but allows a retry), `succeed`, `fail` (exception class only), and
  `summary`. `simulate_work` is the slow/failing task the conventions are exercised with, logged as
  one structured outcome line per run (`task_name`, `task_outcome`, `task_duration_ms`), and
  `manage.py task_status [--stale-minutes] [--fail-on-stuck]` reports counts, backlog age, and stuck
  work without touching the broker. The test harness is the eager runner plus a `captured_logs`
  fixture behind `RequestIdFilter` and `TaskRecordFactory`. D-08 is settled by ADR-033: task-level
  keys, no HTTP `Idempotency-Key` header in the MVP. 553 tests, 98.03% branch coverage.

- 2026-10-31: T5.1 Celery and RabbitMQ, the start of Phase 5. `config/celery.py` configures Celery
  from Django's `CELERY_` settings with autodiscovery from every installed app's `tasks.py`;
  `apps/common/tasking.py` adds `CorrelatedTask` (binds the task ID to the logging context, installed
  as the app's task class so a new task inherits it) and `enqueue()` (`transaction.on_commit`, so a
  worker never reads a row a rollback removes); `apps/common/tasks.py` adds the `ping` smoke task
  whose log line proves broker → worker → logs. `apps/common/logging.py` gained `task_id` alongside
  `request_id` in both formatters, closing FR-051's task half. The shared cache D-13 was waiting for
  arrives too: `DJANGO_CACHE_URL` selects Redis, LocMem otherwise, tests always LocMem, and
  production now refuses to start without it or without `CELERY_BROKER_URL`. 530 tests, 98.19%
  branch coverage; a worker started locally against RabbitMQ answered `inspect ping` and ran the
  smoke task.

- 2026-10-31: T4.11 closeout, the last two items Phase 4 was missing. The no-hardcoded-copy rule is
  now a local ESLint rule (`frontend/eslint-rules/no-hardcoded-copy.js`): it fails on JSX text and on
  text attributes (`aria-label`, `aria-description`, `aria-placeholder`, `aria-roledescription`,
  `alt`, `placeholder`, `title`, `label`, `helperText`, `caption`, `description`, `heading`,
  `subtitle`) written as a literal rather than passed through `t(...)`. Only string literals are
  reported — a computed value is not the rule's business — text without a letter (a separator, a
  numeral) is allowed, and tests are exempt because asserting copy through `t()` would make the
  assertion follow the catalog instead of pinning it. The existing screens needed no changes: every
  user-visible string already came from a catalog, so the rule closes the gap for future work rather
  than fixing past work. `frontend/scripts/check-bundle-budget.mjs` runs after `vite build` and fails
  the gate on gzipped JavaScript above 300 kB, CSS above 20 kB, or a single chunk above 200 kB, and
  prints the measured sizes in both outcomes. Measured now: 240.3 kB JavaScript, 1.7 kB CSS, largest
  chunk 112.2 kB. Both are steps in `pnpm gate` and in `frontend-ci.yml`.

- 2026-10-27: T4.12 end-to-end journey. `frontend/e2e/` drives a real browser against a real API on
  one origin: `seed.ts` and `global-setup.ts` create the demo workspace and its tickets through the
  public contract (idempotent, fictional data, no fixture file), `journey.spec.ts` runs
  register → create workspace → invite → accept in a second browser context → create ticket → assign →
  reply → resolve once per direction, and `seeded.spec.ts` reads the seeded queue through a
  server-side filter. The Arabic run asserts `dir`/`lang` on the document, that the navigation rail
  mirrors the content, and that no catalog key leaks as raw text. Two defects the journey found are
  fixed: the create-ticket serializer defaulted `requester_name` and `category` to the empty string
  while rejecting an explicit `""`, so a form that submits every field it rendered was told they were
  blank; and the locale resolved from `?lang=` was never persisted, so an invitee who opened an
  invitation in Arabic was handed back to English by the sign-up link on the page they landed on.
  `frontend-ci.yml` runs the frontend gates and the
  journey against a throwaway PostgreSQL service with traces retained on failure, and `config.settings.e2e`
  raises the client throttles for the suite because it registers accounts on every run (the backend
  tests still assert each throttle scope). Documented as the manual demo script in the README.

- 2026-10-27: T4.1–T4.10 frontend implemented, and the frontend gates now run. The SPA exists under
  `frontend/`: Vite + React 19 + TypeScript strict, MUI 9 with Emotion and MUI's RTL stylis plugin,
  TanStack Query as the only server-state layer, React Router 7 with a code-split inbox, and i18next
  with `en`/`ar` catalogs (ADR-030, ADR-031). Implemented: theme tokens with both colour schemes, the
  direction provider that swaps the Emotion cache and `html dir`/`lang`, `DirectionalIcon`, the API
  client (CSRF token handling, request-id capture, envelope-to-field-error mapping) and query client
  (401 sets the session to `null`; no retry for a definite 4xx answer), `/login`, `/register`,
  `/invite/:token` with expiry, revoked, accepted and wrong-account states, `/app/workspaces` with its
  empty state and create dialog, the authenticated shell (navigation from one table, workspace
  switcher, account menu, skip link, mobile drawer), the ticket inbox with URL-state filters and the
  empty-versus-filtered-empty distinction, the guard that waits for the session and explains an
  expiry, and the `/app` root redirect and not-found route. `pnpm gate` (format check, lint, type
  check, coverage, build) passes: 160 tests at 89.63% statements, 87.06% branches, 81.98% functions,
  89.59% lines against the 80/75/80/80 floors.

- 2026-10-27: Frontend lint gate repaired after it had never run. The type-checked ESLint configs were
  applied to every file while the parser program was configured only for TypeScript, so `eslint .`
  aborted with a parser error on `eslint.config.js` and linted nothing — which is why 30 findings had
  accumulated unseen. The configs are now scoped to `**/*.{ts,tsx}` and the findings are fixed rather
  than suppressed: router navigations are explicitly voided (`useNavigate` returns a promise),
  `RequireAuth` reads its session ref in the effect that redirects instead of during render, the
  create-workspace dialog is mounted only while open so no reset effect exists, `createQueryClient`
  keeps its `const`, and test mocks no longer declare `async` without awaiting. The axe assertion also
  runs against `document.body` so dialogs and menus rendered in a portal are covered, which is how a
  heading-order violation in the workspace list was found. Still open from T4.11: the
  no-hardcoded-copy lint rule and the bundle-budget check that fails the build; T4.12's end-to-end
  journey is not written.

- 2026-10-27: **Phase 4 pre-flight: the frontend is specified before it is built.** Phase 4 was four
  tasks with no design, language, or accessibility owner (audit F-11). `07_FRONTEND_SPEC.md` is rewritten
  with the chosen stack, a design language (tokens, typography, icons, component inventory, mandatory
  screen states), an internationalization and RTL section, theming, the route table including the missing
  `/register` and `/invite/:token` (D-16), API integration and status-code behaviour, WCAG 2.2 AA targets,
  a bundle budget, and the frontend quality gates. `01_PRD.md` gains FR-060 to FR-063 and a bilingual
  success criterion; `08` expands Phase 4 from four tasks to twelve (T4.1–T4.12) and adds T7.6, T9.7 plus
  frontend ordering rules; `15` gains the matching prompts; `02`, `10`, `11`, `12` and `13` gain the
  frontend boundaries, security rules, test layers, CI steps and definition-of-done items; `16` resolves
  D-16 and F-07 for the frontend and records F-11. Recorded ADR-030 (stack, server state, single-origin
  serving) and ADR-031 (bilingual RTL UI, client-only locale, light/dark themes). No frontend code exists
  yet; T4.1 is next.

- 2026-10-26: Phase 3 ticket workflow, T3.1–T3.5. New `apps/tickets`: `Ticket` (requester contact snapshot, optional `requester_user_id`, `version`, three query indexes), `TicketMessage` (public reply versus internal note), and `TicketEvent` (append-only audit). Endpoints: list with the allowlisted filters and `ordering`, create, detail, `PATCH` with `If-Match`, `assign`, `transition`, and message list/create. Transitions follow ADR-009 in a pure service function; assignment and transitions lock the ticket row and bump the version, field edits use one conditional `UPDATE`, and a message moves only `updated_at`. `tickets.edit` joins the capability matrix (ADR-029), ticket creation is throttled, and every write records an audit event. 513 tests at 98.19% coverage. Phase 3's exit criterion is met: the manual ticket workflow works end to end without AI.

- 2026-10-26: T2.7 ownership transfer. `POST /api/v1/workspaces/{id}/transfer-ownership/` promotes the target to `owner` and demotes the caller to `admin` in one transaction under the workspace lock, with the actor re-read under that lock (ADR-028). Owner-only, active target required, self-transfer refused. Phase 2's exit criterion is now met: a workspace can be created, populated by invitation, and handed over entirely through the API. 289 tests at 99.06% coverage.

- 2026-10-26: T2.5 and T2.6 implemented. `POST /api/v1/auth/register/` creates an account with no workspace and signs it in (ADR-027). Invitations ship as `apps/organizations/invitations.py`: hashed single-use token, seven-day expiry, revoke/resend, public preview, acceptance that reactivates a removed membership, and delivery recorded in `delivery_status`; migration `organizations.0002_invitation`. Added registration and invitation throttle scopes, email settings and `FRONTEND_BASE_URL` (console locally, locmem in tests), and 59 tests. 272 tests at 99.01% coverage.

- 2026-10-26: Self-registration specified. `POST /api/v1/auth/register/` creates an account with no workspace, signs it in, and is throttled; FR-001, the contract, frontend routes, plan and backlog were updated. D-10 is settled; implementation follows in this same change. Recorded ADR-027.

- 2026-10-26: Invitation flow specified. The `Invitation` entity, hashed single-use token, seven-day expiry, revoke/resend, and the invitee preview and accept endpoints are now defined in `03_DOMAIN_AND_DATA_MODEL.md` and `04_API_CONTRACT.md`, with T2.6 written into `08` and `15` and invitation controls added to `10_SECURITY.md`. D-09 is settled; nothing is implemented, so no invitation can be created through the API yet. Recorded ADR-026.

- 2026-10-26: Six Phase 3 decisions settled, no code changed. The requester is a contact snapshot on the ticket rather than an account (ADR-020); ticket capabilities and workspace-wide visibility are named (ADR-021); field edits use `version` with `If-Match` and commands take a row lock (ADR-022); the ticket list query has a fixed allowlist and deterministic pagination (ADR-023); teams are out of MVP, so there is no `team_id` (ADR-024); the MVP cut line declares analytics and the customer portal out, ownership transfer in as T2.7 (FR-006), and retention in as a documented policy with T9.6 (FR-054). Updated `01_PRD.md`, `03_DOMAIN_AND_DATA_MODEL.md`, `04_API_CONTRACT.md`, `07_FRONTEND_SPEC.md`, `08_IMPLEMENTATION_PLAN.md`, `10_SECURITY.md` (retention policy table), `15_AGENT_TASK_BACKLOG.md`, and `16_PHASE2_AUDIT.md`.

- 2026-10-26: Phase 2 audit. Added `16_PHASE2_AUDIT.md`: endpoint, entity, and requirement traceability plus sixteen open decisions. Phase 2's exit criterion is met as written (tenant isolation is proven for `Workspace` and `Membership`), but FR-005 is only half implemented — invitations have no domain entity, task, endpoint shape, or email provider, and there is no sign-up path, so neither joining a workspace nor invitation acceptance is reachable. `Team`, `analytics/overview/`, owner transfer, retention, and observability metrics are requirements no phase owns. No code changed; the audit proposes settling D-01 to D-16 before T3.1 and adding T2.5/T2.6.

- 2026-10-26: Slug race closed. Workspace creation now translates a unique-constraint violation into `WorkspaceSlugTaken`, which the API returns as a 400 `validation_error` on `slug` instead of a 500, and the losing request rolls back with no orphaned workspace or membership. Added concurrent-create and post-validation-collision tests. Recorded ADR-019.

- 2026-10-25: Concurrency hardening for membership changes. The workspace row is locked before the owner count is read and the actor's membership is re-read under that lock, so simultaneous demotions cannot leave a workspace ownerless. Added concurrent, stale-access, archived-mid-request, and removed-actor tests. Recorded ADR-018.

- 2026-10-25: Phase 2 gap closeout. Added the missing T2.3 and T2.4 backlog entries and HTTP-level refusal tests for archived workspaces (404 on read and write) and deactivated accounts (401, because session authentication stops resolving an inactive user before workspace authorization runs). 207 tests passing.

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
