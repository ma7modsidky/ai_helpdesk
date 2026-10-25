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

## Changelog
Add dated entries as features or specs change. Keep this file concise; detailed implementation notes belong in pull requests.
