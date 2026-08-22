#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Contract Review Desk — first-time setup (macOS and Linux)
#
# Run this once. It installs everything the app needs and creates a private
# key for hashing Social Security numbers. Running it again is safe: it will
# not touch the key it already made.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1m%s\033[0m\n' "$1"; }
fail() { printf '\n\033[31m%s\033[0m\n\n' "$1" >&2; exit 1; }

say "Contract Review Desk — setup"

# --- 1. Check what is installed --------------------------------------------
PY=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    version=$("$candidate" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
    if [ "$version" -ge 311 ]; then PY="$candidate"; break; fi
  fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer is not installed. Get it from https://www.python.org/downloads/ then run this again."

command -v node >/dev/null 2>&1 || fail "Node.js is not installed. Get the LTS version from https://nodejs.org then run this again."

echo "  Python: $($PY --version)"
echo "  Node:   $(node --version)"

# --- 2. Backend -------------------------------------------------------------
say "Installing the backend (this takes a minute)"
cd backend
[ -d .venv ] || "$PY" -m venv .venv
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
echo "  Done."

# --- 3. The private key -----------------------------------------------------
# Never regenerate: changing it makes every existing record unmatchable.
if [ -f .env ]; then
  say "Keeping the existing settings file"
  echo "  backend/.env already exists, so your key is untouched."
else
  say "Creating your private key"
  SALT=$(./.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')
  cp .env.example .env
  "$PY" - "$SALT" <<'PYEOF'
import sys, pathlib
salt = sys.argv[1]
path = pathlib.Path(".env")
text = path.read_text()
text = text.replace("SSN_SALT=change-me-before-first-real-contract", f"SSN_SALT={salt}")
path.write_text(text)
PYEOF
  echo "  Written to backend/.env — back this file up. Without it, stored"
  echo "  records can no longer be matched."
fi
cd ..

# --- 4. Frontend ------------------------------------------------------------
say "Installing the screens (this takes a few minutes the first time)"
cd frontend
npm install --no-audit --no-fund --silent
npm run build
cd ..

# --- 5. An account, if this desk will be reached from elsewhere ------------
say "Who will use this?"
cd backend
if ./.venv/bin/python -m app.cli list-users 2>/dev/null | grep -q "No accounts"; then
  echo "  With no account the desk runs without a login, on this machine"
  echo "  only. That is the right setting if nobody else needs to open it."
  echo
  printf "  Create an account so it can be opened from elsewhere? [y/N] "
  read -r answer </dev/tty || answer="n"
  if [ "${answer:-n}" = "y" ] || [ "${answer:-n}" = "Y" ]; then
    echo
    ./.venv/bin/python -m app.cli create-user || true
  else
    echo "  Skipped. Add one later with:"
    echo "      cd backend && ./.venv/bin/python -m app.cli create-user"
  fi
else
  echo "  Accounts already exist. Manage them with:"
  echo "      cd backend && ./.venv/bin/python -m app.cli list-users"
fi
cd ..

say "Setup finished."
echo
echo "  Start the app by running:  ./start.sh"
echo "  To open it from another device:  ./start-shared.sh"
echo
