"""End-to-end settings.

The Playwright journey drives a real browser against a real API, and every run registers
one account per locale — plus the seed account, which is attempted whether or not it
already exists. Client throttles are per process and per client, so the development rates
make a second run inside the same hour fail with `429` for reasons that have nothing to do
with what the suite asserts. Throttling itself stays covered: the backend tests drive
`auth_register`, `auth_login`, `invitation_create`, `invitation_accept` and `ticket_create`
to their ceiling directly (ADR-012, ADR-026, ADR-027), so the ceiling here is only raised, never
removed. This is not a deployment configuration either: `DEBUG` stays on and the secret key
stays the local fallback, which is why it must not be pointed at a shared environment.
"""

from __future__ import annotations

# `dev` is imported for its side effect as much as its settings: it loads the repository
# `.env` before `base` reads the environment, and importing `base` first here would read
# the database settings before that file was loaded.
from .dev import *  # noqa: F403
from .dev import REST_FRAMEWORK

# Ten thousand requests per client is far beyond what a run performs, so a rerun never
# depends on when the previous one happened.
_E2E_UNTHROTTLED = "10000/hour"

REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10000/min",
        "auth_register": _E2E_UNTHROTTLED,
        "invitation_create": _E2E_UNTHROTTLED,
        "invitation_accept": _E2E_UNTHROTTLED,
        "ticket_create": _E2E_UNTHROTTLED,
        "ai_generation": _E2E_UNTHROTTLED,
    },
}
