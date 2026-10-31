"""Shared settings for every environment.

Environment-specific modules (dev, test, prod) import from here and override only
what differs. Nothing in this module may contain a real credential.
"""

from __future__ import annotations

from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent.parent


# --- Security -------------------------------------------------------------
# Left empty here on purpose: dev supplies a local-only fallback and prod
# refuses to start without a real value.

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"


# --- Applications ---------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    # Installed for its tasks and middleware rather than its models: Celery discovers tasks
    # from `apps/<app>/tasks.py` in installed apps only, so `apps.common.tasks` is invisible
    # to the worker unless the app is registered (T5.1).
    "apps.common",
    "apps.accounts",
    "apps.organizations",
    "apps.tickets",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.RequestIdMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


# --- Authentication -------------------------------------------------------

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- API ------------------------------------------------------------------
# Session authentication only: no tokens are issued to the browser, so a leaked
# localStorage entry cannot be replayed. Object authorization is re-evaluated on
# every request, which makes membership revocation immediate.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_PAGINATION_CLASS": "apps.common.pagination.BoundedPageNumberPagination",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.common.errors.exception_handler",
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": "10/min",
        # Open sign-up is limited harder than login: an account costs a row.
        "auth_register": "10/hour",
        "invitation_create": "30/hour",
        "invitation_accept": "30/hour",
        # Ticket creation is the only ticket route that adds rows on demand, so
        # it is the only one that needs a client-level ceiling.
        "ticket_create": "120/hour",
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "ResolveAI Helpdesk API",
    "DESCRIPTION": (
        "Multi-tenant customer support API. All endpoints require an authenticated "
        "session except the CSRF bootstrap, registration, login, and the invitation "
        "preview endpoints. Errors always use "
        '{"error": {"code", "message", "request_id"}}.'
    ),
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
}


# --- Email ----------------------------------------------------------------
# Delivery is best effort; the invitation row is the source of truth. Development
# prints messages to the console and tests use the locmem backend, so a clean
# checkout needs no provider. Production supplies a real backend and credentials.

EMAIL_BACKEND = env_str(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = env_str("DJANGO_DEFAULT_FROM_EMAIL", default="no-reply@resolveai.local")
# A stalled SMTP connection must not hold a request open.
EMAIL_TIMEOUT = 10

# Used to build the accept link in invitation emails. The API returns the relative
# ``accept_path`` instead, so no deployment-specific URL leaks into responses.
FRONTEND_BASE_URL = env_str("FRONTEND_BASE_URL", default="http://localhost:5173")


# --- Background tasks -----------------------------------------------------
# RabbitMQ carries task messages and Celery executes them (ADR-004, ADR-032). The app itself
# is configured in `config/celery.py`; everything here is read through the CELERY_ namespace.

CELERY_BROKER_URL = env_str("CELERY_BROKER_URL", default="amqp://guest:guest@127.0.0.1:5672//")

CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
# No result backend: durable task state belongs in the database (T5.2). A second store of
# what a task did can only disagree with the first.
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
# `acks_late` acknowledges after execution, so a worker killed mid-task gets the message
# redelivered rather than losing it — every task therefore has to be safe to run twice.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Bounded retries: an unbounded loop turns one provider outage into a queue flood.
CELERY_TASK_MAX_RETRIES = 3
CELERY_TASK_DEFAULT_RETRY_DELAY = 30
# A hung task must not hold a worker slot indefinitely.
CELERY_TASK_SOFT_TIME_LIMIT = 120
CELERY_TASK_TIME_LIMIT = 180
# One message in flight per worker process, so a slow task cannot starve the queue, and a
# periodic child restart bounds the damage from any leak.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_WORKER_MAX_TASKS_PER_CHILD = 200
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
# The task base class (correlation IDs, one place for task-wide behaviour) is assigned in
# `config/celery.py`: Celery does not read `task_cls` from the settings namespace.
# No periodic task exists yet; T8.3 adds the SLA deadline sweep here.
CELERY_BEAT_SCHEDULE: dict[str, dict[str, object]] = {}
CELERY_TIMEZONE = "UTC"

# --- Cache ----------------------------------------------------------------
# Throttle counters live in the cache, and LocMem is per process: two API processes would
# each allow the full rate. Development and tests may run without Redis; production may not
# (prod.py refuses to start without a URL), and tests always use LocMem so a developer's
# local Redis cannot make the suite depend on it.

if CACHE_URL := env_str("DJANGO_CACHE_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": CACHE_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "resolveai-local",
        }
    }


# --- Database -------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", default="resolveai"),
        "USER": env_str("POSTGRES_USER", default="resolveai"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", default=""),
        "HOST": env_str("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env_str("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": 60,
    }
}


# --- Internationalisation -------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# --- Logging --------------------------------------------------------------
# Structured JSON by default so aggregation tools can parse it. Set
# DJANGO_LOG_FORMAT=console for readable local output. Request correlation IDs are
# supplied by apps.common.logging.RequestIdFilter via the request middleware.

LOG_FORMAT = env_str("DJANGO_LOG_FORMAT", default="json")
if LOG_FORMAT not in {"json", "console"}:
    raise ImproperlyConfigured("DJANGO_LOG_FORMAT must be 'json' or 'console'.")

LOG_LEVEL = (env_str("DJANGO_LOG_LEVEL", default="INFO") or "INFO").upper()
if LOG_LEVEL not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
    raise ImproperlyConfigured("DJANGO_LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR, or CRITICAL.")

LOGGING = {
    "version": 1,
    # Never silence Django's own loggers just because ours are configured.
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.common.logging.RequestIdFilter"},
    },
    "formatters": {
        "json": {"()": "apps.common.logging.JsonFormatter"},
        "console": {"()": "apps.common.logging.ConsoleFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": LOG_FORMAT,
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}


# --- Static files and defaults --------------------------------------------

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
