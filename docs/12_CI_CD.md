# 12 — CI/CD and Deployment Specification

## Pull request pipeline

Run on every pull request:
1. Backend dependency install from lock file.
2. Backend formatting/lint/type checks.
3. Django system checks.
4. Migration consistency check (`makemigrations --check --dry-run`).
5. Backend tests against PostgreSQL.
6. Frontend dependency install from lock file.
7. Frontend lint/type checks/tests/build.
8. Dependency and secret scans.
9. Build Docker images.
10. Publish test/coverage artifacts.

Do not use production secrets in pull-request CI. Forked PRs must not receive privileged credentials.

## Main branch / release pipeline

- Require successful CI and code review.
- Build immutable container images tagged with commit SHA.
- Deploy to staging.
- Run migrations as a controlled release step, not concurrently from every web/worker replica.
- Run smoke tests.
- Promote to production with a documented rollback path.
- Keep backward-compatible migrations when possible: expand schema, deploy compatible code, backfill, then contract in a later release.

## Environment separation

- Local, CI, staging, production use separate configuration and credentials.
- `DEBUG` off in staging/production.
- Explicit `ALLOWED_HOSTS`, CORS origins, CSRF trusted origins, cookie security, and HTTPS settings.
- Separate database/broker credentials per environment.
- Backups and restore procedure documented for any persistent production data.

## Runtime observability
- Structured application logs with request IDs and task IDs.
- Health and readiness endpoints.
- Error tracking with sensitive fields redacted.
- Metrics: request latency/error rate, database connection/slow-query signals, queue depth/oldest message, task retries/failures/duration, AI latency/failure/cost estimates, SLA breaches.
- Alert on sustained worker failure or queue backlog, not just process liveness.

## Rollback
- Keep previous image available.
- Avoid destructive schema changes in the same release as code that depends on them.
- Document migration reversibility or forward-fix strategy.
- Verify worker and web code compatibility during rolling deploys.
