"""Automated-test settings.

Database connection details come from the environment (or the repository .env
for local runs). The password hasher is fast purely to keep the suite quick;
production hashing configuration is untouched.
"""

from __future__ import annotations

from pathlib import Path

from config.env import load_dotenv

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(REPOSITORY_ROOT / ".env")

from .base import *  # noqa: E402,F403

DEBUG = False

SECRET_KEY = "test-only-secret-key-not-used-in-deployment"  # noqa: S105
ALLOWED_HOSTS = ["testserver", "localhost", "127.0.0.1"]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
