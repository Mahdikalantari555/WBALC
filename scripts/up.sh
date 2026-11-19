#!/usr/bin/env bash
#
# Run the whole stack natively — no Docker required.
#
#   ./scripts/up.sh                  engine :8000 + SvelteKit workspace :3000
#   ./scripts/up.sh --dev            vite dev server instead of a production build
#   ./scripts/up.sh status           what is running, on which pid/port
#   ./scripts/up.sh down             stop everything this script started
#
# This is the sibling of ./scripts/dev.sh (Docker). It exists because the
# repository is often exercised in environments without a Docker daemon — CI
# sandboxes, locked-down laptops — and because a native run gives you the
# FastAPI reloader and Vite HMR, which the container images deliberately omit.
#
# What it does, in order, and why each step is not optional:
#   1. creates/reuses .venv and installs the requirements (idempotent)
#   2. starts uvicorn on :8000 and waits for /health — the UIs proxy server-side,
#      so a UI without an engine shows an error page rather than a broken layout
#   3. builds SvelteKit unless --dev and starts it with RSAL_API_URL pointing at the engine
#   4. writes pid files under .run/ and a log per service, so `down` is precise
#      and a failure is diagnosable after the terminal is gone
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
ROOT="$PWD"
RUN_DIR="$ROOT/.run"
LOG_DIR="$RUN_DIR/logs"

FRONTEND=1
DEV_MODE=0
COMMAND="up"
LOG_SERVICE="engine"

API_PORT="${API_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

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
  awk 'NR==1{next} /^#/{sub(/^# ?/,""); print; next} {exit}' "${BASH_SOURCE[0]}"
  exit "${1:-0}"
}

while [ $# -gt 0 ]; do
  case "$1" in
    up|down|status) COMMAND="$1"; shift ;;
    logs)
      COMMAND=logs; shift
      case "${1:-}" in engine|frontend|frontend-build) LOG_SERVICE="$1"; shift ;; esac
      ;;
    --research) shift ;; # compatibility: the workspace is now always enabled
    --no-frontend) FRONTEND=0; shift ;;
    --dev) DEV_MODE=1; shift ;;
    -h|--help) usage 0 ;;
    *) die "unknown argument: $1 (try --help)" ;;
  esac
done

healthy() {
  local url="$1" response
  response="$(curl -fsS -m 2 "$url" 2>/dev/null)" || return 1
  case "$url" in
    */api/health)
      # The adapter returns HTTP 200 even when the engine is unreachable.
      grep -Eq '"adapter":[[:space:]]*true' <<<"$response" && grep -Eq '"engine":[[:space:]]*true' <<<"$response"
      ;;
    *) grep -Eq '"status":[[:space:]]*"ok"' <<<"$response" ;;
  esac
}

pid_alive() {
  local pidfile="$1"
  [ -f "$pidfile" ] || return 1
  local pid
  pid="$(cat "$pidfile" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

wait_for() { # url, seconds, label
  local url="$1" limit="$2" label="$3" waited=0
  until healthy "$url"; do
    waited=$((waited + 1))
    if [ "$waited" -ge "$limit" ]; then
      warn "$label did not answer $url within ${limit}s"
      return 1
    fi
    sleep 1
  done
  ok "$label is up: $url"
}

ensure_venv() {
  if [ ! -x "$ROOT/.venv/bin/python" ]; then
    say "${DIM}creating .venv${RESET}"
    python3 -m venv "$ROOT/.venv"
  fi
  # Cheap idempotent check: import the app's two heaviest runtime deps.
  if ! "$ROOT/.venv/bin/python" -c "import fastapi, rasterio, sklearn, lightgbm" >/dev/null 2>&1; then
    say "${DIM}installing python requirements (first run only)${RESET}"
    "$ROOT/.venv/bin/pip" install -q -r "$ROOT/requirements.txt"
  fi
}

ensure_node() {
  local dir="$1" fingerprint stamp
  command -v npm >/dev/null 2>&1 || die "Node.js and npm are required for the workspace"
  fingerprint="$(cd "$dir" && node -e 'const fs=require("node:fs"), h=require("node:crypto").createHash("sha256"); for(const file of ["package.json","package-lock.json"]) h.update(fs.readFileSync(file)); console.log(h.update(process.version).digest("hex"))')"
  stamp="$dir/node_modules/.wbalc-deps"
  if [ ! -f "$stamp" ] || [ "$(cat "$stamp")" != "$fingerprint" ]; then
    say "${DIM}synchronizing locked dependencies in frontend/${RESET}"
    ( cd "$dir" && npm ci --include=dev --no-audit --no-fund ) || die "frontend dependency installation failed"
    printf '%s\n' "$fingerprint" >"$stamp"
  fi
}

start_bg() { # name, workdir, command…
  local name="$1" dir="$2"; shift 2
  local pidfile="$RUN_DIR/$name.pid" log="$LOG_DIR/$name.log"
  if pid_alive "$pidfile"; then
    warn "$name already running (pid $(cat "$pidfile"))"
    return 0
  fi
  mkdir -p "$LOG_DIR"
  # `cd` first, then replace the subshell with the server itself, so `$!` is the
  # pid of the process that will actually hold the port. (Recording the pid of a
  # wrapper shell made `down` kill the wrong thing and leave orphans behind.)
  (
    cd "$dir" || exit 1
    exec setsid "$@" >"$log" 2>&1 &
    echo $! >"$pidfile"
  )
  sleep 1
  if pid_alive "$pidfile"; then
    ok "$name started (pid $(cat "$pidfile"), log .run/logs/$name.log)"
  else
    warn "$name exited immediately — last lines:"
    tail -n 15 "$log" 2>/dev/null | sed 's/^/    /'
    return 1
  fi
}

cmd_up() {
  mkdir -p "$RUN_DIR" "$LOG_DIR"

  # ---------------------------------------------------------------- engine
  if healthy "http://localhost:$API_PORT/health"; then
    ok "engine already answering on :$API_PORT (reusing it)"
  else
    ensure_venv
    say "${DIM}starting engine on :$API_PORT${RESET}"
    if [ "$DEV_MODE" = 1 ]; then
      start_bg engine "$ROOT" "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT" --reload
    else
      start_bg engine "$ROOT" "$ROOT/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$API_PORT"
    fi
    wait_for "http://localhost:$API_PORT/health" 45 "engine" || die "engine failed to start: see .run/logs/engine.log"
  fi

  # ------------------------------------------------------ research workspace
  if [ "$FRONTEND" = 1 ]; then
    if healthy "http://localhost:$FRONTEND_PORT/api/health"; then
      ok "research workspace already answering on :$FRONTEND_PORT (reusing it)"
    else
      local dir="$ROOT/frontend"
      ensure_node "$dir"
      if [ "$DEV_MODE" = 1 ]; then
        start_bg frontend "$dir" env RSAL_API_URL="http://localhost:$API_PORT" PORT="$FRONTEND_PORT" \
          npm run dev -- --port "$FRONTEND_PORT" --strictPort
      else
        say "${DIM}building research workspace${RESET}"
        ( cd "$dir" && npm run build >"$LOG_DIR/frontend-build.log" 2>&1 ) \
          || die "research workspace build failed: see .run/logs/frontend-build.log"
        start_bg frontend "$dir" env RSAL_API_URL="http://localhost:$API_PORT" PORT="$FRONTEND_PORT" \
          HOST=0.0.0.0 ORIGIN="${ORIGIN:-http://localhost:$FRONTEND_PORT}" \
          BODY_SIZE_LIMIT="${BODY_SIZE_LIMIT:-545259520}" node build
      fi
      wait_for "http://localhost:$FRONTEND_PORT/api/health" 60 "research workspace" || die "workspace failed to start: see .run/logs/frontend.log"
    fi
  fi

  say ""
  say "  ${BOLD}engine${RESET}     http://localhost:$API_PORT/docs"
  [ "$FRONTEND" = 1 ] && say "  ${BOLD}research${RESET}   http://localhost:$FRONTEND_PORT"
  say ""
  say "${DIM}logs:  ./scripts/up.sh logs [engine|frontend]${RESET}"
  say "${DIM}stop:  ./scripts/up.sh down${RESET}"
}

cmd_down() {
  local found=0
  for pidfile in "$RUN_DIR"/*.pid; do
    [ -e "$pidfile" ] || continue
    local name pid
    name="$(basename "$pidfile" .pid)"
    pid="$(cat "$pidfile" 2>/dev/null || true)"
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
      local pgid
      pgid="$(ps -o pgid= "$pid" 2>/dev/null | tr -d ' ' || true)"
      # `setsid` gave each service its own group, so this reaches children
      # (`node`, `vite`) without touching this shell.
      if [ -n "$pgid" ] && [ "$pgid" != "$$" ]; then
        kill -TERM "-$pgid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
      else
        kill -TERM "$pid" 2>/dev/null || true
      fi
      # Give it a moment, then make sure it is really gone.
      local waited=0
      while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt 10 ]; do
        sleep 1
        waited=$((waited + 1))
      done
      if kill -0 "$pid" 2>/dev/null; then
        kill -KILL "-$pgid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
      fi
      ok "stopped $name (pid $pid)"
      found=1
    else
      warn "$name was not running"
    fi
    rm -f "$pidfile"
  done
  [ "$found" = 1 ] || warn "nothing to stop (no live pid files in .run/)"
  # A uvicorn started by hand is not ours to kill; say so rather than leaving a
  # silent port conflict for the next `up`.
  if curl -fsS -m 1 "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    warn "something is still serving :$API_PORT — it was not started by this script"
  fi
}

cmd_status() {
  say ""
  if curl -fsS -m 2 "http://localhost:$API_PORT/health" >/dev/null 2>&1; then
    ok "engine    :$API_PORT  $(curl -fsS -m 2 "http://localhost:$API_PORT/health")"
  else
    warn "engine    :$API_PORT  down"
  fi
  if healthy "http://localhost:$FRONTEND_PORT/api/health"; then
    ok "workspace :$FRONTEND_PORT  up"
  else
    warn "workspace :$FRONTEND_PORT  down"
  fi
  say ""
  if [ -d "$RUN_DIR" ] && ls "$RUN_DIR"/*.pid >/dev/null 2>&1; then
    for pidfile in "$RUN_DIR"/*.pid; do
      printf '  %-10s pid %s\n' "$(basename "$pidfile" .pid)" "$(cat "$pidfile")"
    done
  else
    say "  ${DIM}no pid files under .run/ (nothing started by up.sh)${RESET}"
  fi
}

cmd_logs() {
  local name="${1:-engine}"
  local log="$LOG_DIR/$name.log"
  [ -f "$log" ] || die "no log for '$name' (available: $(ls "$LOG_DIR" 2>/dev/null | sed 's/\.log$//' | tr '\n' ' '))"
  tail -n 200 -f "$log"
}

case "$COMMAND" in
  up) cmd_up ;;
  down) cmd_down ;;
  status) cmd_status ;;
  logs) cmd_logs "$LOG_SERVICE" ;;
  *) usage 1 ;;
esac
