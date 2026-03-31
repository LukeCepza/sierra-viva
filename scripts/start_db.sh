#!/usr/bin/env bash
set -euo pipefail

COMPOSE_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Stopping old sierraviva-db container (if running)..."
docker stop sierraviva-db 2>/dev/null && docker rm sierraviva-db 2>/dev/null || true

echo "==> Starting database with docker compose..."
docker compose -f "$COMPOSE_DIR/docker-compose.yml" up -d

echo "==> Waiting for PostgreSQL to become healthy..."
SECONDS=0
TIMEOUT=60
while true; do
    STATUS=$(docker inspect --format='{{.State.Health.Status}}' sierraviva-db 2>/dev/null || echo "unknown")
    if [ "$STATUS" = "healthy" ]; then
        echo "==> PostgreSQL is healthy! (took ${SECONDS}s)"
        break
    fi
    if [ "$SECONDS" -ge "$TIMEOUT" ]; then
        echo "==> ERROR: Timed out after ${TIMEOUT}s waiting for healthy status (current: $STATUS)"
        exit 1
    fi
    sleep 2
done

echo ""
echo "==> Container status:"
docker compose -f "$COMPOSE_DIR/docker-compose.yml" ps
