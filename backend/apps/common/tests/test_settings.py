"""Production settings must refuse to start insecurely.

Each case runs in a subprocess so the production module is imported in a clean
environment instead of mutating the running test settings.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]

_PROBE = (
    "import json;"
    "import config.settings.prod as prod;"
    "print(json.dumps({'debug': prod.DEBUG,"
    "'session_cookie_secure': prod.SESSION_COOKIE_SECURE,"
    "'hsts_seconds': prod.SECURE_HSTS_SECONDS,"
    "'ssl_redirect': prod.SECURE_SSL_REDIRECT}))"
)

_SAFE_PROD_ENV = {
    "DJANGO_SECRET_KEY": "prod-secret-value-used-only-in-tests",
    "DJANGO_ALLOWED_HOSTS": "helpdesk.example.com",
    "POSTGRES_PASSWORD": "prod-db-password-used-only-in-tests",
    "DJANGO_CACHE_URL": "redis://127.0.0.1:6379/1",
    "CELERY_BROKER_URL": "amqp://guest:guest@127.0.0.1:5672//",
}


def _run_prod_probe(overrides: dict[str, str | None]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "POSTGRES_", "CELERY_"))
    }
    env.update({key: value for key, value in _SAFE_PROD_ENV.items()})
    for key, value in overrides.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    env["PYTHONPATH"] = str(BACKEND_DIR)

    return subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_prod_settings_apply_transport_hardening() -> None:
    result = _run_prod_probe({})

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload == {
        "debug": False,
        "session_cookie_secure": True,
        "hsts_seconds": 31536000,
        "ssl_redirect": True,
    }


def test_prod_refuses_missing_secret_key() -> None:
    result = _run_prod_probe({"DJANGO_SECRET_KEY": None})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr
    assert "prod-db-password-used-only-in-tests" not in result.stderr


def test_prod_refuses_placeholder_secret_key() -> None:
    result = _run_prod_probe({"DJANGO_SECRET_KEY": "replace-me-with-a-long-random-string"})

    assert result.returncode != 0
    assert "DJANGO_SECRET_KEY" in result.stderr


def test_prod_refuses_enabled_debug() -> None:
    result = _run_prod_probe({"DJANGO_DEBUG": "true"})

    assert result.returncode != 0
    assert "DJANGO_DEBUG" in result.stderr


def test_prod_refuses_empty_allowed_hosts() -> None:
    result = _run_prod_probe({"DJANGO_ALLOWED_HOSTS": ""})

    assert result.returncode != 0
    assert "DJANGO_ALLOWED_HOSTS" in result.stderr


def test_prod_refuses_missing_database_password() -> None:
    result = _run_prod_probe({"POSTGRES_PASSWORD": None})

    assert result.returncode != 0
    assert "POSTGRES_PASSWORD" in result.stderr


def test_prod_refuses_missing_cache_url() -> None:
    result = _run_prod_probe({"DJANGO_CACHE_URL": None})

    assert result.returncode != 0
    assert "DJANGO_CACHE_URL" in result.stderr


def test_prod_refuses_missing_broker_url() -> None:
    result = _run_prod_probe({"CELERY_BROKER_URL": None})

    assert result.returncode != 0
    assert "CELERY_BROKER_URL" in result.stderr


@pytest.mark.parametrize("secret", ["prod-secret-value-used-only-in-tests"])
def test_prod_error_output_never_contains_the_secret(secret: str) -> None:
    result = _run_prod_probe({"DJANGO_DEBUG": "true"})

    assert result.returncode != 0
    assert secret not in result.stderr
    assert secret not in result.stdout
