"""Typed environment-variable access with fail-fast validation.

Errors name the offending variable but never echo its value, so a misconfigured
deployment cannot leak a secret through a traceback or a log line.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def load_dotenv(path: Path) -> None:
    """Populate ``os.environ`` from a simple KEY=VALUE file.

    Development and test convenience only: real environment variables always win,
    a missing file is a no-op, and nothing is logged. Production never calls this.
    """
    if not path.is_file():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()

        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key:
            continue

        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]

        os.environ.setdefault(key, value)


def env_str(name: str, *, default: str | None = None, required: bool = False) -> str | None:
    """Return a stripped string value. Empty values count as missing."""
    raw = os.environ.get(name)
    value = raw.strip() if raw is not None else ""

    if value:
        return value

    if default is not None:
        return default

    if required:
        raise ImproperlyConfigured(f"Required environment variable '{name}' is not set.")

    return None


def require(name: str) -> str:
    """Return a mandatory string value or raise."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"Required environment variable '{name}' is not set.")
    return value


def env_bool(name: str, *, default: bool = False) -> bool:
    """Return a boolean parsed from an allowlisted set of spellings."""
    value = env_str(name)
    if value is None:
        return default

    normalized = value.lower()
    if normalized in _TRUE_VALUES:
        return True
    if normalized in _FALSE_VALUES:
        return False

    accepted = ", ".join(sorted(_TRUE_VALUES | _FALSE_VALUES))
    raise ImproperlyConfigured(f"Environment variable '{name}' must be one of: {accepted}.")


def env_int(name: str, *, default: int | None = None) -> int | None:
    """Return an integer value or raise without echoing the raw text."""
    value = env_str(name)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Environment variable '{name}' must be an integer.") from exc


def env_list(name: str, *, default: Iterable[str] = ()) -> list[str]:
    """Return a comma-separated list with blanks dropped."""
    value = env_str(name)
    if value is None:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]
