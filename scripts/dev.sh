#!/usr/bin/env bash
#
# One command to bring the whole WBALC stack up (or inspect it).
#
#   ./scripts/dev.sh up                  engine + SvelteKit research workspace
#   ./scripts/dev.sh up --postgres       ... with Postgres instead of SQLite
#   ./scripts/dev.sh up --all            enable Postgres
#   ./scripts/dev.sh up --build          force a rebuild first
#   ./scripts/dev.sh logs [service]      follow logs
#   ./scripts/dev.sh ps                  status + health of each service
#   ./scripts/dev.sh smoke               run the frontend smoke suites from the host
#   ./scripts/dev.sh down [-v]           stop (and delete the data volumes)
#
# Anything after `--` is passed to `docker compose` unchanged, so
# `./scripts/dev.sh up -- --progress plain` works.
#
# Why a script instead of a one-liner: the failure modes here are specific and
# silent. A missing Docker daemon, a port already taken by a stale dev server, a
# `depends_on` pointing at a service that is not in the active profile, or a
# Postgres profile started without DATABASE_URL all produce a stack that *looks*
# up and then fails on the first request. Those are checked before starting.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

PROFILE_POSTGRES=0
FORCE_BUILD=0
COMMAND=""
COMPOSE_ARGS=()

if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
  YELLOW=$'\033[33m'; RESET=$'\033[0m'
else
  BOLD=''; DIM=''; RED=''; GREEN=''; YELLOW=''; RESET=''
fi

say() { printf '%s\n' "$*"; }
ok() { printf '%s✓%s %s\n' "$GREEN" "$RESET" "$*"; }
warn() { printf '%s!%s %s\n' "$YELLOW" "$RESET" "$*"; }
die() { printf '%s✗%s %s\n' "$RED" "$RESET" "$*" >&2; exit 1; }

usage() {
  # Print the header comment block only (everything up to the first non-comment).
  awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
  exit "${1:-0}"
}

# ---------------------------------------------------------------- arguments
while [ $# -gt 0 ]; do
  case "$1" in
    up|down|ps|logs|smoke|build|pull|restart|config) COMMAND="$1"; shift ;;
    --research) shift ;; # compatibility: the workspace is now always enabled
    --postgres) PROFILE_POSTGRES=1; shift ;;
    --all) PROFILE_POSTGRES=1; shift ;;
    --build) FORCE_BUILD=1; shift ;;
    -h|--help) usage 0 ;;
    --) shift; COMPOSE_ARGS+=("$@"); break ;;
    *) COMPOSE_ARGS+=("$1"); shift ;;
  esac
done

[ -n "$COMMAND" ] || usage 1

# ------------------------------------------------------------- preflight
need_docker() {
  command -v docker >/dev/null 2>&1 || die "docker is not installed. \
Install Docker Engine/Desktop, or run the services directly: \
\`../../.venv/bin/python -m uvicorn app.main:app --port 8000\` and \`npm run dev\`."
  if ! docker info >/dev/null 2>&1; then
    die "the docker CLI is present but the daemon is not reachable. \
Start Docker, or check 'docker context ls'. (Sandboxes without a daemon cannot run this stack.)"
  fi
  if docker compose version >/dev/null 2>&1; then
    COMPOSE=(docker compose)
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE=(docker-compose)
  else
    die "docker compose (v2 plugin) or docker-compose is required."
  fi
}

# A stale local dev server on 8000/3000 makes `up` fail with a confusing
# "bind: address already in use". Say which port and what is on it.
check_port() {
  local port="$1" label="$2"
  if command -v lsof >/dev/null 2>&1 && lsof -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then
    warn "port $port ($label) is already in use by pid $(lsof -iTCP:"$port" -sTCP:LISTEN -t | tr '\n' ' ')"
    warn "  stop it, or set ${3}=... in .env to publish elsewhere"
    return 1
  fi
  return 0
}

profiles_list() {
  local p=()
  [ "$PROFILE_POSTGRES" = 1 ] && p+=("postgres")
  local IFS=,
  printf '%s' "${p[*]:-}"
}

compose() {
  local profiles
  profiles="$(profiles_list)"
  if [ -n "$profiles" ]; then
    "${COMPOSE[@]}" --profile "$profiles" "$@"
  else
    "${COMPOSE[@]}" "$@"
  fi
}

# Postgres only works if the API is told to use it. `db` in the profile with no
# DATABASE_URL silently leaves the engine on SQLite — which looks like data loss
# the next time the volume is recreated.
check_postgres_env() {
  [ "$PROFILE_POSTGRES" = 1 ] || return 0
  if ! grep -qE '^DATABASE_URL=postgres' .env 2>/dev/null; then
    local user pass db
    user="$(grep -E '^POSTGRES_USER=' .env 2>/dev/null | cut -d= -f2 || true)"
    pass="$(grep -E '^POSTGRES_PASSWORD=' .env 2>/dev/null | cut -d= -f2 || true)"
    db="$(grep -E '^POSTGRES_DB=' .env 2>/dev/null | cut -d= -f2 || true)"
    die "--postgres needs DATABASE_URL in .env, otherwise the engine keeps using SQLite:
  add this line to .env (values match the db service defaults):
  DATABASE_URL=postgresql+asyncpg://${user:-rsal}:${pass:-rsal}@db:5432/${db:-rsal}"
  fi
  ok "DATABASE_URL points at the postgres service"
}

urls() {
  local api front
  api="${API_PORT:-8000}"
  front="${FRONTEND_PORT:-3000}"
  say ""
  say "  ${BOLD}engine${RESET}            http://localhost:${api}/docs   ${DIM}(OpenAPI)${RESET}"
  say "  ${BOLD}workspace${RESET}         http://localhost:${front}"
  say ""
}

# ------------------------------------------------------------------- verbs
cmd_up() {
  need_docker
  local conflicts=0
  check_port "${API_PORT:-8000}" "engine API" API_PORT || conflicts=1
  check_port "${FRONTEND_PORT:-3000}" "SvelteKit workspace" FRONTEND_PORT || conflicts=1
  [ "$conflicts" = 0 ] || die "resolve the port conflicts above (or change the *_PORT vars), then retry"
  check_postgres_env

  local build=()
  [ "$FORCE_BUILD" = 1 ] && build=(--build)
  say "${DIM}$ compose $(profiles_list | sed 's/^/--profile /') up -d ${build[*]}${RESET}"
  compose up -d --remove-orphans "${build[@]}" "${COMPOSE_ARGS[@]:-}"

  say ""
  say "${DIM}waiting for the workspace adapter and engine…${RESET}"
  local tries=0 response
  local health="http://localhost:${FRONTEND_PORT:-3000}/api/health"
  while :; do
    response="$(curl -fsS -m 2 "$health" 2>/dev/null || true)"
    if grep -Eq '"adapter":[[:space:]]*true' <<<"$response" && grep -Eq '"engine":[[:space:]]*true' <<<"$response"; then
      ok "workspace adapter and engine are healthy"
      break
    fi
    tries=$((tries + 1))
    if [ "$tries" -ge 60 ]; then
      compose ps
      die "workspace is not ready: check ./scripts/dev.sh logs frontend and ./scripts/dev.sh logs api"
    fi
    sleep 1
  done

  compose ps
  urls
  say "${DIM}stop with: ./scripts/dev.sh down${RESET}"
}

cmd_down() {
  need_docker
  # Volumes are only removed when asked: they hold uploads, checkpoints and the
  # SQLite database.
  if printf '%s' "${COMPOSE_ARGS[*]:-}" | grep -q -- '-v'; then
    warn "removing data volumes (uploads, checkpoints, exports and the SQLite DB)"
  fi
  compose down "${COMPOSE_ARGS[@]:-}"
}

cmd_ps() {
  need_docker
  compose ps
  say ""
  for svc in $(compose config --services 2>/dev/null); do
    local state
    state="$(compose ps --format '{{.State}} {{.Health}}' "$svc" 2>/dev/null | head -1 || true)"
    [ -n "$state" ] && printf '  %-20s %s\n' "$svc" "$state"
  done
}

cmd_logs() {
  need_docker
  compose logs -f --tail=120 "${COMPOSE_ARGS[@]:-}"
}

cmd_build() {
  need_docker
  compose build "${COMPOSE_ARGS[@]:-}"
}

cmd_pull() {
  need_docker
  compose pull "${COMPOSE_ARGS[@]:-}"
}

cmd_config() {
  need_docker
  compose config
}

# The smoke suites talk to running services from the host, not from inside a
# container: they assert on what a browser would see through the adapter.
cmd_smoke() {
  local py=".venv/bin/python"
  [ -x "$py" ] || die "no .venv found; create one: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt"
  local api="${API_PORT:-8000}" front="${FRONTEND_PORT:-3000}"
  curl -fsS "http://localhost:${api}/health" >/dev/null || die "engine not reachable on :${api} — is the stack up?"

  say "${BOLD}research workspace smoke${RESET} (:${front})"
  "$py" scripts/research_frontend_smoke.py --base "http://localhost:${front}" \
    --backend "http://localhost:${api}" || die "research smoke failed"
}

case "$COMMAND" in
  up) cmd_up ;;
  down) cmd_down ;;
  ps) cmd_ps ;;
  logs) cmd_logs ;;
  build) cmd_build ;;
  pull) cmd_pull ;;
  config) cmd_config ;;
  smoke) cmd_smoke ;;
  restart) need_docker; compose restart "${COMPOSE_ARGS[@]:-}"; cmd_ps ;;
  *) usage 1 ;;
esac
