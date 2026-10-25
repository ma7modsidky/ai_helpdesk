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

## Local development (current status: T1.4 test infrastructure)

Prerequisites: Python 3.11+, [uv](https://docs.astral.sh/uv/), Docker with Compose.

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
  deployment described above.
- `DJANGO_SETTINGS_MODULE` defaults to `config.settings.dev` for `manage.py` and to
  `config.settings.prod` for WSGI/ASGI entry points.
- Host ports for the local datastores are configurable (`POSTGRES_PORT`, `REDIS_PORT`,
  `RABBITMQ_PORT`, `RABBITMQ_MANAGEMENT_PORT`) in case they clash with other projects.
  `POSTGRES_PORT` is also the port Django connects to.
- Logs are structured JSON (`DJANGO_LOG_FORMAT=console` for readable local output) and every
  line carries a `request_id`. Each response echoes the ID in `X-Request-ID`: a client value is
  accepted only if it matches `[A-Za-z0-9._-]{1,64}`, otherwise one is generated. Log lines
  contain the method, path (never the query string), status, and duration — no bodies or headers.
- API (T1.3): session authentication under `/api/v1/auth/` — `GET /auth/csrf/` for a token,
  `POST /auth/login/` with JSON and `X-CSRFToken`, `POST /auth/logout/`, `GET /auth/me/`. The
  OpenAPI document is at `GET /api/v1/schema/`. Every state-changing request must send
  `Content-Type: application/json`; errors always return
  `{"error": {"code", "message", "request_id"}}`.
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
measured 97%, configured in `pyproject.toml`, and the `coverage.xml` report is uploaded as a
workflow artifact (diagnostic only — the failing gate is the test step's exit code).

Supply-chain gates in the same job:

- `uv audit --locked` scans the locked dependency set against OSV and fails on any known
  vulnerability. Fix findings or record an explicit, justified `--ignore` in the workflow.
- `gitleaks` (pinned version, sha256-verified download) scans the full commit history for committed
  secrets. It fails the build when a leak is found; rotate the credential, don't just delete the line.

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
