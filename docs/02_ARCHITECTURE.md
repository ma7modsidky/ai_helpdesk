# 02 — Architecture and Technical Decisions

## 1. Architecture style

Use a **modular monolith** for the MVP. One Django deployment owns the business domain; Celery workers execute background jobs. Avoid microservices until there is measured operational or organizational need.

### Runtime components
- React + TypeScript single-page application (Vite, MUI, react-i18next) served as static assets, bilingual
  English/Arabic with light and dark themes. In local development and in the container deployment the
  SPA is served on the same origin as the API, so no CORS configuration exists (ADR-030).
- Django + Django REST Framework API.
- PostgreSQL as source of truth.
- Redis for cache, throttling support, and Celery result/broker-adjacent use only where explicitly configured.
- RabbitMQ as Celery broker.
- Celery worker and Celery Beat scheduler.
- LLM provider behind an application-owned adapter.
- Optional `pgvector` extension for embedding similarity search.
- Docker Compose for local development.
- GitHub Actions for CI.

## 2. Request and background flows

### Ticket creation
1. API authenticates user and resolves authorized workspace membership.
2. Serializer validates input.
3. Domain/service layer creates ticket and audit event inside a database transaction.
4. A durable background-work intent is recorded (transactional outbox recommended for reliability; a simpler `transaction.on_commit` dispatch may be used in early MVP with documented trade-offs).
5. Worker classifies ticket and drafts reply.
6. Results are schema-validated and stored.
7. Frontend polls ticket/AI status; WebSockets are optional and not required for MVP.

### Knowledge ingestion
1. Admin saves article.
2. Article version is persisted.
3. Async job chunks text and generates embeddings.
4. Chunks/embeddings are saved with workspace and article/version identifiers.
5. Retrieval filters by workspace and published status before ranking.
6. Source identifiers are returned with the generated draft.

### SLA monitoring
1. Beat triggers a periodic task.
2. Task queries candidate tickets using indexed deadline/status fields.
3. Domain service decides whether an escalation is due.
4. A unique constraint/idempotency key prevents duplicate escalation records.
5. Notification task is queued.
6. Failure is logged and retried without duplicating business state.

## 3. Module boundaries

- `accounts`: authentication-specific configuration and user profile.
- `organizations`: workspace, membership, invitations, teams.
- `tickets`: ticket lifecycle, messages, assignments, status transitions.
- `knowledge_base`: articles, versions, chunks, retrieval interface.
- `ai_assistant`: provider adapter, prompts, output schemas, orchestration, evaluation.
- `sla`: policies, deadline calculation, breach/escalation logic.
- `notifications`: email/in-app notification delivery.
- `audit`: audit event creation and access.
- `common`: shared primitives only; avoid turning it into a dumping ground.

Modules should expose service functions/use cases instead of importing each other's ORM internals indiscriminately.

### Frontend modules (mirror of the backend's boundaries)
- `app`: providers, router, error boundary, and the shell layout; the only module that wires features together.
- `features/<domain>`: one folder per product area (auth, invitations, workspaces, tickets, knowledge,
  sla), containing that area's queries, mutations, and screens.
- `lib/api`: the single HTTP client, error mapping, and query-client configuration.
- `theme` and `i18n`: tokens, colour schemes, direction handling, catalogs, and formatters.
- `components`: presentational building blocks with no product knowledge.

The frontend holds no authorization logic of its own: it renders affordances from the role data it holds
and mirrors server refusals. Any rule that must be true for security lives in the API.

## 4. Dependency rules

- Views/serializers handle HTTP concerns; they do not contain substantial business logic.
- Domain/services do not depend on React or HTTP request objects.
- AI provider implementation is behind an interface, allowing fake/mock providers in tests.
- Celery tasks are thin orchestration wrappers that call services.
- Frontend never calls the LLM provider directly or receives server secrets.
- The frontend never derives a permission, transition, or SLA rule; it sends a request and renders the
  answer, so the server stays the single source of truth (ADR-021, ADR-022).
- Cross-feature imports are forbidden on the frontend too: shared code moves down into `components` or
  `lib`, never sideways between features.
- All tenant-scoped queries must originate from an authorized workspace context.
- External calls have explicit timeouts and bounded retries.

## 5. Recommended decisions

- Use a custom user model from the beginning if the project needs one; configure it before initial migrations.
- Use UUID primary keys for externally exposed domain records.
- Use explicit membership roles and server-side object authorization.
- Store timestamps in UTC; display in user/workspace timezone.
- Use PostgreSQL constraints for invariants that must survive concurrent requests.
- Use a stable API error envelope and consistent pagination.
- Use `pgvector` only if semantic retrieval is in MVP; otherwise start with PostgreSQL full-text search and add embeddings later.
- Use an LLM adapter interface and a deterministic fake provider in automated tests.
- Keep ticket creation independent of provider latency and availability.

## 6. Cache policy

Cache only data with a clear invalidation strategy, such as dashboard aggregates or stable configuration. Do not cache authorization decisions in a way that can survive membership revocation. Use tenant-qualified cache keys and short TTLs. Measure hit rate and latency before adding complex caching.

## 7. Scalability path

Start with one API deployment and one worker pool. Scale workers separately by queue/task type when metrics justify it. Add separate queues for latency-sensitive notifications and slower AI/embedding work if useful. Track queue age, queue depth, task duration, retry count, provider latency, and error rate before tuning concurrency.
