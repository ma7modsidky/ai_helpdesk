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

## Changelog
Add dated entries as features or specs change. Keep this file concise; detailed implementation notes belong in pull requests.

- 2026-10-25: Phase 1 closeout. Backfilled the T1.2 and T1.3 backlog entries, corrected the documented coverage scope in the README, added `DJANGO_CSRF_TRUSTED_ORIGINS` to `.env.example`, made CI apply migrations to its database explicitly, and replaced an inert `CORS_ALLOW_CREDENTIALS` setting with a note explaining why no CORS configuration exists.

- 2026-10-25: Type checking. Added mypy in strict mode with django-stubs and DRF stubs, annotations across models, serializers, views, admin, middleware, and the test suite, and a CI `mypy .` step. Recorded ADR-014.

- 2026-10-25: T1.4 test infrastructure. Added `factory_boy` fixtures writing through the model managers, branch coverage over application code with a 90% floor against a measured 97%, a `coverage.xml` artefact in CI, and the backlog entry that defines the task. Recorded ADR-013.

- 2026-10-25: T1.3 API foundation. DRF mounted at `/api/v1/` with URL path versioning, session authentication, a uniform error envelope carrying the request ID, bounded pagination, login throttling, and an OpenAPI 3 document at `/api/v1/schema/`. Added `GET/POST /auth/csrf|login|logout|me` and documented them in `04_API_CONTRACT.md`. 104 tests passing. Recorded ADR-012.

- 2026-10-25: Supply-chain gates in CI. Added `uv audit --locked` and a pinned, checksum-verified gitleaks history scan to `backend-ci.yml`. Upgraded pytest 8.4.2 to 9.1.1 because the audit gate flagged CVE-2025-71176 in the pinned version; suite re-run green. Recorded ADR-011.
- 2026-10-25: T0.4 CI skeleton. `.github/workflows/backend-ci.yml` installs from `uv.lock` and runs ruff lint/format, Django checks, migration consistency, and pytest against a PostgreSQL 16 service. Frontend jobs and container builds are deferred until those targets exist.
- 2026-10-25: T1.2 logging. Structured JSON logging with request correlation IDs, `X-Request-ID` handling, and request completion lines; 76 tests passing. Recorded ADR-010.
- 2026-10-25: T1.1 backend foundation. Django 5.2 project with layered settings, custom `accounts.User` (UUID primary key, email login), `/health/live/` and `/health/ready/`, datastore-only Compose services, `.env.example` placeholders, and 43 passing tests. Recorded ADR-006 to ADR-009.
