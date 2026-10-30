#!/usr/bin/env bash
# Roll back to the version that was running before the last deploy.
set -euo pipefail

PREVIOUS="$(cat .previous-version 2>/dev/null || true)"
if [ -z "${PREVIOUS}" ]; then
  echo "No previous version recorded. Use: ./scripts/deploy.sh <version>"
  exit 1
fi

echo "==> Rolling back to ${PREVIOUS}"
exec "$(dirname "$0")/deploy.sh" "${PREVIOUS}"