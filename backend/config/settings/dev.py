"""Local development settings."""

from __future__ import annotations

from pathlib import Path

from config.env import env_bool, load_dotenv

# Load the repository-level .env (if present) before base settings read the
# environment. Real environment variables take precedence.
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPOSITORY_ROOT / ".env")

from .base import *  # noqa: E402,F403
from .base import ALLOWED_HOSTS as _BASE_ALLOWED_HOSTS  # noqa: E402
from .base import SECRET_KEY as _BASE_SECRET_KEY  # noqa: E402

DEBUG = env_bool("DJANGO_DEBUG", default=True)

# Local-only fallback so a fresh clone can run without a prepared .env.
# prod.py refuses to start without a real key.
SECRET_KEY = _BASE_SECRET_KEY or "insecure-development-only-key-do-not-use-in-deployment"  # noqa: S105

ALLOWED_HOSTS = _BASE_ALLOWED_HOSTS or ["localhost", "127.0.0.1", "testserver"]
