#!/usr/bin/env python
"""Command-line entry point for the ResolveAI Helpdesk backend."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - environment misconfiguration
        raise ImportError(
            "Could not import Django. Activate the project environment (uv sync) and try again."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
