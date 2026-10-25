"""Production settings.

Fails fast rather than running insecurely: a missing secret, an enabled DEBUG
flag, or a missing required host configuration stops the process at startup.
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured

from config.env import env_bool, env_list, require

from .base import *  # noqa: F403

DEBUG = env_bool("DJANGO_DEBUG", default=False)
if DEBUG:
    raise ImproperlyConfigured("DJANGO_DEBUG must not be enabled outside development.")

SECRET_KEY = require("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must list at least one host.")

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

# A value we deliberately reject, not a credential of any kind.
_SECRET_PLACEHOLDER = "replace-me-with-a-long-random-string"  # noqa: S105
if SECRET_KEY == _SECRET_PLACEHOLDER:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY still holds the example placeholder value.")

if not DATABASES["default"]["PASSWORD"]:  # noqa: F405
    raise ImproperlyConfigured("POSTGRES_PASSWORD is required outside development.")

# HTTPS and transport hardening.
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# No credentialed cross-origin access: the SPA and API share one origin.
CORS_ALLOW_CREDENTIALS = False
