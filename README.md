# AI-Powered Helpdesk SaaS — SDD Starter Pack

A specification-driven starter pack for building a portfolio-quality, multi-tenant customer support platform with Django, DRF, PostgreSQL, Redis, RabbitMQ, Celery, React/TypeScript, and an LLM provider.

## Product goal

Deliver a demonstrable workflow in which a customer submits a ticket, the system persists it, asynchronous AI classifies it and drafts a response grounded in approved knowledge-base content, an agent reviews and sends the response, and SLA monitoring can notify or escalate overdue work.

## How to use this pack

1. Read `01_PRD.md` and agree on the MVP scope.
2. Read `02_ARCHITECTURE.md` and `03_DOMAIN_AND_DATA_MODEL.md`.
3. Implement contracts from `04_API_CONTRACT.md`.
4. Follow the small, dependency-ordered tasks in `08_IMPLEMENTATION_PLAN.md`.
5. Use `09_AGENT_WORKFLOW.md` for every coding-agent task.
6. Treat `10_SECURITY.md`, `11_TEST_STRATEGY.md`, and `12_CI_CD.md` as release gates.
7. Update `14_DECISIONS_AND_CHANGELOG.md` when a material decision changes.

## Suggested repository structure

```text
ai-helpdesk/
├── docs/                         # copy this pack here
├── backend/
│   ├── config/
│   ├── apps/
│   │   ├── accounts/
│   │   ├── organizations/
│   │   ├── tickets/
│   │   ├── knowledge_base/
│   │   ├── ai_assistant/
│   │   ├── sla/
│   │   ├── notifications/
│   │   └── audit/
│   ├── manage.py
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   ├── features/
│   │   ├── components/
│   │   └── lib/
│   └── package.json
├── infra/
│   └── docker/
├── .github/workflows/
├── .env.example
├── compose.yaml
└── README.md
```

## Local development (current status: backend through T3.5, frontend through T4.12, no AI yet)

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker with Compose, and — for the
frontend — Node 22+ with [pnpm](https://pnpm.io/).

```bash
cp .env.example .env          # then replace every placeholder value
docker compose up -d postgres redis rabbitmq

cd backend
uv sync                       # installs Django, psycopg, pytest, ruff from uv.lock
uv run python manage.py migrate
uv run python manage.py runserver
```

- Configuration comes from environment variables; `.env` (git-ignored) is read by the
  development and test settings only, and real environment variables always win.
  Production settings refuse to start with `DEBUG` enabled, a missing or placeholder
  `DJANGO_SECRET_KEY`, empty `DJANGO_ALLOWED_HOSTS`, or a missing database password.
  `DJANGO_CSRF_TRUSTED_ORIGINS` lists origins allowed to send CSRF-protected requests when
  the SPA is served from a different origin than the API; it stays empty for the same-origin
  deployment described above. Production also requires `DJANGO_CACHE_URL` (Redis) and
  `CELERY_BROKER_URL`: LocMem throttling is per process, so without a shared cache each API
  worker would allow every client the full rate, and a task queued to a default local
  broker is accepted by nobody.
- `DJANGO_SETTINGS_MODULE` defaults to `config.settings.dev` for `manage.py` and to
  `config.settings.prod` for WSGI/ASGI entry points.
- Host ports for the local datastores are configurable (`POSTGRES_PORT`, `REDIS_PORT`,
  `RABBITMQ_PORT`, `RABBITMQ_MANAGEMENT_PORT`) in case they clash with other projects.
  `POSTGRES_PORT` is also the port Django connects to.
- Logs are structured JSON (`DJANGO_LOG_FORMAT=console` for readable local output) and every
  line carries a `request_id`. Each response echoes the ID in `X-Request-ID`: a client value is
  accepted only if it matches `[A-Za-z0-9._-]{1,64}`, otherwise one is generated. Log lines
  contain the method, path (never the query string), status, and duration — no bodies or headers.
- API (T1.3, T2.5): session authentication under `/api/v1/auth/` — `GET /auth/csrf/` for a token,
  `POST /auth/register/` for open sign-up (it creates the account, signs it in, and creates no
  workspace), `POST /auth/login/` with JSON and `X-CSRFToken`, `POST /auth/logout/`, `GET /auth/me/`. The
  OpenAPI document is at `GET /api/v1/schema/`. Every state-changing request must send
  `Content-Type: application/json`; errors always return
  `{"error": {"code", "message", "request_id"}}`.
- Workspaces (T2.3): `GET/POST /api/v1/workspaces/` lists the caller's workspaces or creates one
  (the caller becomes its owner); `GET /workspaces/{id}/members/` lists active members;
  `PATCH /workspaces/{id}/members/{membership_id}/` changes a role or revokes access. Checks are
  server-side: non-members see 404, insufficient roles see 403, and the last active owner cannot be
  demoted or removed (409). `POST /workspaces/{id}/transfer-ownership/` hands ownership to an active
  member and demotes the caller to admin in one transaction (T2.7).
- Invitations (T2.6): `POST /workspaces/{id}/invitations/` (owner or admin) issues a single-use
  invitation and returns `/invite/<token>` exactly once, alongside `GET` (list), `POST .../resend/`
  (rotates the token) and `DELETE` (revoke). `POST /invitations/preview/` is public and
  `POST /invitations/accept/` joins the signed-in account whose email matches the invitation. Tokens
  are stored hashed, expire after seven days, and email is sent through the configured backend —
  the console locally, locmem in tests.
- Tickets (T3.1–T3.5): `GET/POST /api/v1/workspaces/{id}/tickets/` lists (filters `status`,
  `priority`, `assignee=me|unassigned|<uuid>`, `search`, allowlisted `ordering`, paginated) or creates
  a ticket. `GET`/`PATCH .../tickets/{ticket_id}/` read one ticket or edit its fields, the latter
  requiring `If-Match: "<version>"` and returning `409` with `error.details.version` when the version
  is stale. `POST .../assign/`, `POST .../transition/` and `GET`/`POST .../messages/` cover assignment,
  validated status transitions (agents may resolve, managers and above may reopen, `closed` is
  terminal), and public replies versus internal notes. Every write appends a `TicketEvent` audit row;
  creation is throttled at 120 per hour per client.
- Background tasks (T5.1): Celery is configured in `config/celery.py` and reads its
  settings from the `CELERY_` namespace, so a deployment has one configuration surface.
  RabbitMQ is the broker (`CELERY_BROKER_URL`), and there is deliberately **no result
  backend** — durable task state belongs in the database (T5.2), so nothing depends on a
  result a worker restart would lose. Defaults: `acks_late` with
  `reject_on_worker_lost` (a killed worker redelivers instead of dropping, so every task
  must be safe to run twice), three retries at 30 seconds by default, and 120/180 second
  soft/hard time limits. `apps.common.tasking.enqueue` publishes only after the surrounding
  transaction commits, and every task log line carries a `task_id` (`CorrelatedTask`), which
  is the task-side counterpart of `request_id`. Run the processes without a container:

  ```bash
  cd backend
  uv run celery -A config worker --loglevel=info   # --pool=solo on Windows
  uv run celery -A config beat --loglevel=info     # the schedule is empty until T8.3
  ```

  `apps.common.tasks.ping` is the smoke task: queue it and the worker log line carries both
  the message and a `task_id`. `apps.common.tasks.simulate_work` is the slow/failing one used to
  exercise retries and the status report. The automated tests run tasks eagerly, so CI needs no
  broker.
- Background-work state (T5.2–T5.4): every unit of work has a `TaskRecord` row, unique on
  `(task_name, idempotency_key)`. The dispatcher derives the key from the work itself
  (`ticket:<id>:classify:v<version>`), so a repeated request, a Celery redelivery, and two workers
  racing converge on one row and one execution; a worker claims the row only from `pending` or
  `failed`, so finished work is skipped and a retry is allowed. `last_error` records the exception
  class, never its message. Each run logs `task_name`, `task_outcome`, and `task_duration_ms` as
  fields, and `uv run python manage.py task_status` reports counts, the oldest pending unit, and
  running work that stopped progressing (`--fail-on-stuck` exits non-zero for a monitor).
- AI provider (T6.1): every model call goes through
  `apps.ai_assistant.providers.AIProvider`, which takes a prompt and returns text plus
  `provider`, `model`, and `latency_ms`. `AI_PROVIDER` selects the adapter (default `fake`),
  `AI_MODEL` names the model, and `AI_REQUEST_TIMEOUT_SECONDS` bounds a call. Only the
  deterministic fake ships today: the same prompt produces the same text with no network and no
  key, so tests and the offline demo are reproducible. Failures are modelled by type —
  `AIProviderTimeout`, `AIProviderUnavailable`, and `AIProviderRateLimited` are retryable;
  `AIResponseInvalid` is not, because the same prompt fails the same way. Adapter messages never
  quote the prompt, which contains ticket text. Adding a vendor is one class implementing
  `AIProvider` plus one entry in `_PROVIDERS`; its credential is read from the environment by
  that adapter and stays in the backend process.
- Health checks: `GET /health/live/` reports the process is up (200). `GET /health/ready/`
  reports required dependency readiness (200, or 503 with `{"status": "unavailable"}` and no
  internal detail when PostgreSQL is unreachable).

Quality checks (run from `backend/`):

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .                # strict; django-stubs and DRF stubs supply the types
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
uv run pytest --cov            # branch coverage over app code, fails below the floor
```

Continuous integration: `.github/workflows/backend-ci.yml` runs those same backend gates on every
pull request and on pushes to `main` — dependencies installed from `uv.lock`, ruff lint and format
check, mypy type checking, Django system checks, migration consistency, and the full test suite
against a PostgreSQL 16 service. CI uses throwaway credentials and no repository secrets.

Tests run with branch coverage over `apps/` plus `config/env.py` and `config/urls.py`, excluding
migrations, tests, settings modules, and the WSGI/ASGI entry points. The floor is 90% against a
measured 98%, configured in `pyproject.toml`, and the `coverage.xml` report is uploaded as a
workflow artifact (diagnostic only — the failing gate is the test step's exit code).

Supply-chain gates in the same job:

- `uv audit --locked` scans the locked dependency set against OSV and fails on any known
  vulnerability. Fix findings or record an explicit, justified `--ignore` in the workflow.
- `gitleaks` (pinned version, sha256-verified download) scans the full commit history for committed
  secrets. It fails the build when a leak is found; rotate the credential, don't just delete the line.

Frontend (`frontend/`, T4.1–T4.10): the SPA is served on the same origin as the API, so `pnpm dev`
proxies `/api` and `/health` to the backend (VITE_PROXY_TARGET, default `http://127.0.0.1:8000`) and no
CORS configuration is needed. Screens implemented so far: sign in, sign up, invitation acceptance,
the workspace picker with workspace creation, the workspace shell with its ticket inbox and ticket
detail, and the member and invitation list.

```bash
cd frontend
pnpm install
pnpm dev        # http://localhost:5173, with the API proxied
pnpm gate       # format check, lint, type check, coverage floors, production build
```

`pnpm gate` is the same set of checks the pull-request pipeline runs. The unit and component tests
(vitest, Testing Library, jsdom, axe-core) live beside the source they cover, and the `en`/`ar`
catalogs are checked for parity as part of the default run.

Two T4.11 rules are enforced rather than reviewed: `eslint-rules/no-hardcoded-copy.js` fails lint on
JSX text or a text attribute (`aria-label`, `placeholder`, `title`, …) written as a literal instead of
passed through `t(...)`, and `scripts/check-bundle-budget.mjs` fails the build when gzipped JavaScript
exceeds 300 kB, CSS 20 kB, or a single chunk 200 kB, printing the measured sizes either way.

End-to-end journey (T4.12): `frontend/e2e/` drives a real browser against a real API on the same
origin, once per direction, and needs a running backend with a migrated database:

```bash
# once, from the repository root
docker compose up -d postgres
cd backend && uv run python manage.py migrate

# the suite registers an account per direction on every run, plus the seed account, so it runs
# against the settings module that raises those client throttles (throttling itself is asserted
# by the backend tests, not here)
cd backend && DJANGO_SETTINGS_MODULE=config.settings.e2e uv run python manage.py runserver 127.0.0.1:8000

# in a second shell: Playwright starts the Vite dev server itself, and the browser reaches the
# API through the same-origin proxy
cd frontend && pnpm e2e          # both journeys plus the seeded-backend spec
pnpm e2e:report                  # the HTML report from the last run
```

Traces, screenshots, and an error-context snapshot are kept for anything that fails, under
`frontend/test-results/`. `.github/workflows/frontend-ci.yml` runs the same suite in the pipeline
against a throwaway PostgreSQL service, so a failing journey blocks the pull request.

### The journey as a manual demo

The automated journey is also the script for showing the product to somebody — same steps, same
order, in a browser. Run the backend as above and `pnpm dev` in `frontend/`, then:

1. Open <http://127.0.0.1:5173/register> and create an account. The picker explains that an
   invitation is the other way into an existing workspace, which this account does not have.
2. Create a workspace. You land in its empty ticket queue as its owner.
3. Open **Members**, invite a second person, and copy the `/invite/...` link the dialog shows once.
4. In a second browser profile or a private window, open that link and create the invited account
   with the same address. The invitation is accepted and the second person lands in the same queue.
5. Back in the first window, create a ticket: it starts open and unassigned.
6. Assign it to the second person, reply publicly, and resolve it.
7. Reload the second window: the ticket, the assignment, and the reply are all there, because every
   one of those decisions was made and stored by the API.
8. Switch the language toggle to Arabic at any point — the layout mirrors, the copy changes, and
   nothing asks you to reload.

Do it once in English and once in Arabic: the outcome has to be identical and only the direction,
the words, and the numerals' locale may differ.

## Definition of MVP done

- A user can register/sign in and create or join a workspace through a controlled flow.
- Tenant data isolation is enforced server-side and covered by cross-tenant negative tests.
- Workspace members can create, list, assign, comment on, and change status of tickets according to role permissions.
- Ticket creation persists successfully even when the LLM provider is unavailable.
- AI classification and suggested replies run asynchronously, persist status/results, and can be retried safely.
- Knowledge-base retrieval is tenant-scoped and includes source references for generated answers.
- SLA deadlines and escalation policies are deterministic, configurable, and tested.
- CI runs formatting/linting, type checks, tests, migrations checks, and dependency/security checks.
- Docker-based local setup and environment configuration are documented.
- A seeded demo workflow is reproducible from a clean checkout.

## Scope discipline

Do not add microservices, Kubernetes, a complex workflow-builder UI, automatic customer-facing AI replies, billing, or multiple LLM providers to the MVP. Add them only after the core workflow is stable and measured.
