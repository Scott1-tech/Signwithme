#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Contract Review Desk — start the app (macOS and Linux)
#
# Starts both halves, waits for them, and opens the browser. Press Ctrl+C
# in this window to stop.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")"

say() { printf '\n\033[1m%s\033[0m\n' "$1"; }

if [ ! -d backend/.venv ] || [ ! -d frontend/.next ]; then
  printf '\n\033[31mThe app is not set up yet. Run ./setup.sh first.\033[0m\n\n'
  exit 1
fi

mkdir -p logs

stop_one() {
  # Ask nicely, then insist. Leftover servers hold the ports and make the
  # next start fail with nothing useful on screen.
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill "$pid" 2>/dev/null || return 0
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.5
  done
  kill -9 "$pid" 2>/dev/null
}

STOPPING=0
cleanup() {
  # The trap fires for both the signal and the exit that follows it.
  [ "$STOPPING" = "1" ] && return 0
  STOPPING=1
  say "Stopping"
  stop_one "${FRONT_PID:-}"
  stop_one "${BACK_PID:-}"
  wait 2>/dev/null
  echo "  Stopped."
}
trap cleanup EXIT INT TERM

say "Starting the contract desk"

# `exec` matters: it replaces the subshell with the server itself, so the
# pid recorded here is the server. Without it the pid is a wrapper, killing
# it leaves the real process running, and the ports stay busy.
#
# 127.0.0.1 only: driver Social Security numbers are in these files and
# must not be reachable from the network.
( cd backend && exec ./.venv/bin/python -m uvicorn app.main:app \
    --host 127.0.0.1 --port 8000 > ../logs/backend.log 2>&1 ) &
BACK_PID=$!

( cd frontend && exec ./node_modules/.bin/next start > ../logs/frontend.log 2>&1 ) &
FRONT_PID=$!

printf '  Waiting for the app'
for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
    printf ' ready\n'
    break
  fi
  printf '.'
  sleep 1
done

if ! curl -sf http://127.0.0.1:3000/api/health >/dev/null 2>&1; then
  printf '\n\033[31m  It did not start. See logs/backend.log and logs/frontend.log.\033[0m\n'
  exit 1
fi

URL="http://localhost:3000"
if command -v open >/dev/null 2>&1; then open "$URL"
elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1
fi

echo
echo "  The contract desk is running at $URL"
echo "  Leave this window open. Press Ctrl+C here to stop."
echo

wait
