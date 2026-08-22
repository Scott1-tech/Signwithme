#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Contract Review Desk — back up everything that matters
#
#   ./backup.sh /Volumes/BackupDrive/contract-desk
#
# Copies the contracts, the record of who approved what, and the private
# key. Executed contracts have to be retained under 49 CFR 391.51, and one
# laptop is not a backup.
# ---------------------------------------------------------------------------
set -euo pipefail
cd "$(dirname "$0")"

DEST="${1:-}"
if [ -z "$DEST" ]; then
  echo "Usage: ./backup.sh /path/to/backup/folder" >&2
  echo "Ideally an encrypted external drive." >&2
  exit 1
fi

STAMP=$(date +%Y-%m-%d)
TARGET="$DEST/$STAMP"
mkdir -p "$TARGET"

copy() {
  [ -e "$1" ] || { echo "  skipped $1 (not there yet)"; return; }
  cp -R "$1" "$TARGET/"
  echo "  copied  $1"
}

echo
echo "Backing up to $TARGET"
copy backend/storage            # uploads, executed PDFs, signatures, templates
copy backend/contract_desk.db   # the queue, flags and approvals
copy backend/.env               # the key the SSN hashes depend on

echo
echo "Done. Keep this drive encrypted and somewhere else."
echo
