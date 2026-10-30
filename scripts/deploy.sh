#!/usr/bin/env bash
# Deploy a specific version. Usage: ./scripts/deploy.sh 1.1.0
set -euo pipefail

VERSION="${1:?Usage: ./scripts/deploy.sh <version>}"
IMAGE="ghcr.io/zakeer3551/apex-ops-api:${VERSION}"

# Remember what is running now, so we can roll back to it
CURRENT="$(grep '^API_IMAGE_TAG=' .env | cut -d= -f2)"

echo "==> Pulling ${IMAGE}"
docker pull "${IMAGE}"

echo "==> Deploying ${VERSION} (currently running: ${CURRENT})"
grep -v '^API_IMAGE_TAG=' .env > .env.tmp
echo "API_IMAGE_TAG=${VERSION}" >> .env.tmp
mv .env.tmp .env
echo "${CURRENT}" > .previous-version

docker compose up -d api

echo "==> Waiting for /ready (max 30s)"
for i in $(seq 1 15); do
  if curl -fs http://localhost:8000/ready > /dev/null; then
    echo "==> SUCCESS. Running: $(curl -s http://localhost:8000/version)"
    exit 0
  fi
  sleep 2
done

echo "==> FAILED: ${VERSION} is not ready. Roll back with: ./scripts/rollback.sh"
exit 1