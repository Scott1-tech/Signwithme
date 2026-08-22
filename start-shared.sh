#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Contract Review Desk — start it so other devices can reach it
#
# Use this when the desk needs to be opened from another computer, a phone,
# or over Tailscale. Ordinary daily use does not need it: ./start.sh keeps
# everything on this machine, which is safer.
#
# An account is required. The app refuses to start this way without one,
# because these files hold driver Social Security numbers.
# ---------------------------------------------------------------------------
set -uo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
warn() { printf '\033[33m%s\033[0m\n' "$1"; }

if [ ! -d backend/.venv ] || [ ! -d frontend/.next ]; then
  printf '\n\033[31mThe app is not set up yet. Run ./setup.sh first.\033[0m\n\n'
  exit 1
fi

# Fail here with an explanation rather than letting the server refuse later.
if (cd backend && ./.venv/bin/python -m app.cli list-users 2>/dev/null | grep -q "No accounts"); then
  printf '\n\033[31mThis desk has no account yet.\033[0m\n\n'
  echo "  Sharing it without a login would put driver Social Security"
  echo "  numbers on the network. Create an account first:"
  echo
  echo "      cd backend && ./.venv/bin/python -m app.cli create-user"
  echo
  exit 1
fi

mkdir -p logs

STOPPING=0
stop_one() {
  local pid="$1"
  [ -n "$pid" ] || return 0
  kill "$pid" 2>/dev/null || return 0
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "$pid" 2>/dev/null || return 0
    sleep 0.5
  done
  kill -9 "$pid" 2>/dev/null
}
cleanup() {
  [ "$STOPPING" = "1" ] && return 0
  STOPPING=1
  say "Stopping"
  stop_one "${FRONT_PID:-}"
  stop_one "${BACK_PID:-}"
  wait 2>/dev/null
  echo "  Stopped."
}
trap cleanup EXIT INT TERM

say "Starting the contract desk for other devices"

( cd backend && HOST=0.0.0.0 exec ./.venv/bin/python -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 > ../logs/backend.log 2>&1 ) &
BACK_PID=$!

( cd frontend && exec ./node_modules/.bin/next start --hostname 0.0.0.0 \
    > ../logs/frontend.log 2>&1 ) &
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
  printf '\n\033[31m  It did not start. See logs/backend.log.\033[0m\n'
  exit 1
fi

# Show the addresses other devices can use.
ADDRESSES=$(
  { ipconfig getifaddr en0 2>/dev/null
    ipconfig getifaddr en1 2>/dev/null
    hostname -I 2>/dev/null | tr ' ' '\n'
    tailscale ip -4 2>/dev/null
  } | grep -E '^[0-9]+\.' | sort -u
)

echo
echo "  On this computer:  http://localhost:3000"
if [ -n "$ADDRESSES" ]; then
  echo "  From other devices:"
  while IFS= read -r ip; do
    [ -n "$ip" ] && echo "                     http://$ip:3000"
  done <<< "$ADDRESSES"
fi
echo
warn "  Reachable from the network. Everyone needs to sign in, and the"
warn "  connection is plain HTTP — keep this to a private network such as"
warn "  Tailscale or your own office, never a public one."
echo
echo "  Leave this window open. Press Ctrl+C here to stop."
echo

wait
