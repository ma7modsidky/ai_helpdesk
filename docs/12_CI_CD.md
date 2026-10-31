# 12 — CI/CD and Deployment Specification

## Pull request pipeline

Run on every pull request:
1. Backend dependency install from lock file.
2. Backend formatting/lint/type checks.
3. Django system checks.
4. Migration consistency check (`makemigrations --check --dry-run`) and applying the migrations to the CI database.
5. Backend tests against PostgreSQL.
6. Frontend dependency install from the pnpm lockfile (`--frozen-lockfile`, so a drift between
   `package.json` and the lockfile is a failure rather than a silent resolution).
7. Frontend Prettier format check, lint (including the no-hardcoded-copy rule), type check, component
   and internationalization tests, and the production build with its bundle-budget check.
8. Frontend end-to-end journey against a seeded backend, parameterised over both languages (T4.12),
   with traces retained on failure.
9. Dependency and secret scans, including the frontend lockfile.
10. Build Docker images.
11. Publish test/coverage artifacts, the coverage report, and the frontend build artifact.

Steps 1–5 and the backend halves of 9–11 run in `.github/workflows/backend-ci.yml`. Steps 6–8 run in
`.github/workflows/frontend-ci.yml`, as two jobs: the frontend gates (format, lint, types, tests,
build, bundle budget) and the end-to-end job, which starts a throwaway PostgreSQL service, applies the migrations,
serves the API, installs Chromium, and runs the journey. Playwright starts the Vite dev server itself
and the browser reaches the API through the same-origin proxy, exactly as it does locally.

Do not use production secrets in pull-request CI. Forked PRs must not receive privileged credentials.
The end-to-end job needs a database and a seeded workspace, so it uses throwaway credentials and
synthetic data created inside the job — never a shared environment. It serves the API with
`config.settings.e2e`: the suite registers an account per direction on every run (and attempts the
seed account on every run), and client throttles are per client, so the development rates would fail a
second run inside the same hour for reasons the journey does not assert. Throttling stays covered by
the backend tests, which drive each scope to its ceiling; the end-to-end module only raises it, and is
never a deployment configuration.

## Main branch / release pipeline

- Require successful CI and code review.
- Build immutable container images tagged with commit SHA, including the frontend image that serves the
  static build and proxies the API on one origin.
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
- Keep previous image available, including the previous frontend bundle: the static artifact and the API
  are versioned together by commit SHA, so a rollback returns both.
- Frontend cache headers are documented so a rollback is not defeated by an aggressively cached index.
- Avoid destructive schema changes in the same release as code that depends on them.
- Document migration reversibility or forward-fix strategy.
- Verify worker and web code compatibility during rolling deploys.
