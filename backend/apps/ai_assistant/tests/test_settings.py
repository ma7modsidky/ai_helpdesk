"""AI settings must fail fast rather than silently bounding a request at zero seconds.

Runs in a subprocess so the settings module is imported in a clean environment instead of
mutating the running test settings.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[3]


def _import_base(overrides: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("DJANGO_", "POSTGRES_", "CELERY_", "AI_"))
    }
    env.update(overrides)
    env["PYTHONPATH"] = str(BACKEND_DIR)

    return subprocess.run(
        [sys.executable, "-c", "import config.settings.base"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.mark.parametrize("value", ["0", "-5"])
def test_a_non_positive_ai_timeout_is_rejected(value: str) -> None:
    result = _import_base({"AI_REQUEST_TIMEOUT_SECONDS": value})

    assert result.returncode != 0
    assert "AI_REQUEST_TIMEOUT_SECONDS" in result.stderr


def test_a_valid_ai_timeout_is_accepted() -> None:
    result = _import_base({"AI_REQUEST_TIMEOUT_SECONDS": "15", "AI_PROVIDER": "fake"})

    assert result.returncode == 0, result.stderr
