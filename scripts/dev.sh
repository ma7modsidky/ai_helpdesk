#!/usr/bin/env bash
# One command for the whole local stack: datastores, migrations, API, worker, and the SPA.
#
# It exists because the pieces have to agree with each other. The SPA proxies to port 8000, the
# worker has to load the same settings module as the API, and the API reads .env when its settings
# import. Started by hand in three shells it is easy to run a worker against a half-migrated
# database, or to forget the worker entirely and then wonder why a queued draft never finishes.
#
# Ctrl+C stops every process this script started. The containers keep running with their data;
# `docker compose down -v` removes that data too.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

API_PORT=8000
WEB_PORT=5173
# Vite binds `localhost` (see its printed Local URL), so the printed address matches it.
API_URL="http://127.0.0.1:${API_PORT}"
WEB_URL="http://localhost:${WEB_PORT}"

case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) WINDOWS="1" ;;
  *) WINDOWS="" ;;
esac

# The PID currently listening on a port, or nothing. `netstat` on Windows because Git Bash does not
# ship `lsof`, and `lsof` elsewhere because `netstat` there cannot name the owner.
listener_pid() {
  if [ -n "$WINDOWS" ]; then
    netstat -ano | awk -v pattern=":$1 " '$0 ~ pattern && /LISTENING/ {print $NF; exit}'
  else
    lsof -ti "tcp:$1" -sTCP:LISTEN 2>/dev/null | head -1
  fi
}

if ! command -v docker >/dev/null 2>&1; then
  echo "error: Docker is required for PostgreSQL, Redis and RabbitMQ." >&2
  exit 1
fi

if [ ! -f .env ]; then
  echo "==> .env is missing; copying .env.example (git-ignored, local values only)"
  cp .env.example .env
  echo "    Add GEMINI_API_KEY to .env for a real model; the fake provider needs nothing."
fi

# Refused up front rather than half-started: an occupied port means the API or Vite will die a few
# seconds after launch, and the shutdown below would then be closing somebody else's process.
for port in "$API_PORT" "$WEB_PORT"; do
  holder="$(listener_pid "$port")"
  if [ -n "$holder" ]; then
    echo "error: port ${port} is already in use (pid ${holder}); stop that process and rerun." >&2
    exit 1
  fi
done

echo "==> Datastores: PostgreSQL, Redis, RabbitMQ"
docker compose up -d postgres redis rabbitmq

echo "==> Waiting for PostgreSQL"
ready=""
for _ in $(seq 1 60); do
  if docker compose exec -T postgres pg_isready >/dev/null 2>&1; then
    ready="1"
    break
  fi
  sleep 1
done
if [ -z "$ready" ]; then
  echo "error: PostgreSQL did not become ready within 60 seconds." >&2
  exit 1
fi

echo "==> Backend dependencies"
(cd backend && uv sync)

echo "==> Migrations"
(cd backend && uv run python manage.py migrate --noinput)

if [ ! -d frontend/node_modules ]; then
  echo "==> Frontend dependencies"
  (cd frontend && pnpm install)
fi

# Celery's prefork pool needs fork(), which Windows does not have.
POOL=""
case "$(uname -s)" in
  MINGW* | MSYS* | CYGWIN*) POOL="--pool=solo" ;;
esac

PIDS=()
CELERY_PIDFILE="backend/.celery-dev.pid"
close_port() {
  local port="$1" pid=""
  for _ in 1 2 3; do
    pid="$(listener_pid "$port")"
    [ -z "$pid" ] && return 0
    if [ -n "$WINDOWS" ]; then
      taskkill //T //F //PID "$pid" >/dev/null 2>&1 || true
    else
      kill "$pid" 2>/dev/null || true
    fi
    sleep 1
  done
}

cleanup() {
  # Ignored, not restored: `trap - INT` brings back the default disposition, so a second Ctrl+C
  # while stopping would kill this shell before the ports are closed and leave the services up.
  trap '' INT TERM
  trap - EXIT
  echo ""
  echo "==> Stopping"
  # Ports first. Closing the listener is what makes the wrapper exit on its own, and starting here
  # means a wrapper that has already replaced its child cannot strand a bound port.
  #
  # Ownership is not in doubt: startup refused to run unless both ports were free, so whatever
  # listens on them now was started by this script. A wrapper (`uv run`, `pnpm`) can exit and leave
  # the python or node process it started holding the port, and Git Bash cannot signal that
  # process at all — it does not even appear in `ps` — so it has to be closed by port on Windows.
  close_port "$API_PORT"
  close_port "$WEB_PORT"
  # The worker holds no port, so it is invisible to the sweep above; Celery's pidfile is what
  # makes it stoppable. Without this it survives, keeps consuming the queue with whatever code
  # it loaded at start, and the next run's jobs are handled by a worker nobody can see.
  if [ -f "$CELERY_PIDFILE" ]; then
    worker_pid="$(cat "$CELERY_PIDFILE" 2>/dev/null || true)"
    if [ -n "$worker_pid" ]; then
      if [ -n "$WINDOWS" ]; then
        taskkill //T //F //PID "$worker_pid" >/dev/null 2>&1 || true
      else
        kill "$worker_pid" 2>/dev/null || true
      fi
    fi
    rm -f "$CELERY_PIDFILE"
  fi
  if [ ${#PIDS[@]} -gt 0 ]; then
    for pid in "${PIDS[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# A worker left behind by an interrupted run would keep taking work, so it is stopped before a
# new one starts; the pidfile is the only handle on it.
if [ -f "$CELERY_PIDFILE" ]; then
  stale_pid="$(cat "$CELERY_PIDFILE" 2>/dev/null || true)"
  if [ -n "$stale_pid" ]; then
    echo "==> Stopping the worker left by a previous run (pid ${stale_pid})"
    if [ -n "$WINDOWS" ]; then
      taskkill //T //F //PID "$stale_pid" >/dev/null 2>&1 || true
    else
      kill "$stale_pid" 2>/dev/null || true
    fi
    sleep 1
  fi
  rm -f "$CELERY_PIDFILE"
fi

# The worker first: a draft queued before it is up would wait in RabbitMQ, which looks like a
# hung panel rather than a late start.
(cd backend && exec uv run celery -A config worker --loglevel=info --pidfile=.celery-dev.pid $POOL) &
PIDS+=("$!")
# `--noreload` on purpose: the autoreloader is a second python process that owns the port, so
# stopping the wrapper would leave a child behind that the next run collides with. Restart this
# script after a backend change; the frontend still hot-reloads.
(cd backend && exec uv run python manage.py runserver 127.0.0.1:8000 --noreload) &
PIDS+=("$!")
(cd frontend && exec pnpm dev) &
PIDS+=("$!")

wait_for_port() {
  local port="$1" name="$2" pid=""
  for _ in $(seq 1 60); do
    pid="$(listener_pid "$port")"
    if [ -n "$pid" ]; then
      echo "==> ${name} listening on ${port}"
      return 0
    fi
    sleep 1
  done
  echo "error: ${name} did not open port ${port} within 60 seconds." >&2
  return 1
}

wait_for_port "$API_PORT" "API"
wait_for_port "$WEB_PORT" "Web"

echo ""
echo "API   ${API_URL}"
echo "Web   ${WEB_URL}   (start here; /api and /health are proxied to the API)"
echo "Docs  ${API_URL}/api/v1/schema/"
echo "Press Ctrl+C to stop everything."
echo ""

status=0
wait -n || status=$?
echo "==> A process exited (status ${status}); stopping the rest"
exit "$status"
