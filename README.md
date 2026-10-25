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
