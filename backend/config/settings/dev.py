"""Local development settings."""

from __future__ import annotations

from pathlib import Path

from config.env import env_bool, load_dotenv

# Load the repository-level .env (if present) before base settings read the
# environment. Real environment variables take precedence.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPOSITORY_ROOT / ".env")

from .base import *  # noqa: E402,F403

DEBUG = env_bool("DJANGO_DEBUG", default=True)

if not SECRET_KEY:  # noqa: F405
    # Local-only fallback so a fresh clone can run without a prepared .env.
    # prod.py refuses to start without a real key.
    SECRET_KEY = "insecure-development-only-key-do-not-use-in-deployment"  # noqa: S105

ALLOWED_HOSTS = ALLOWED_HOSTS or ["localhost", "127.0.0.1", "testserver"]  # noqa: F405
