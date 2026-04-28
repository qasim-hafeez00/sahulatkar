#!/usr/bin/env bash
# Cross-platform developer startup script (Linux / macOS / WSL).
# For Windows PowerShell, use start_all.ps1 instead.
set -euo pipefail

COMPOSE="docker compose -f infra/docker/docker-compose.yml"

echo "[sahulatkar] Starting infrastructure..."
$COMPOSE up -d postgres redis pgbouncer pgadmin

echo "[sahulatkar] Waiting for Postgres to be ready..."
until $COMPOSE exec -T postgres pg_isready -U sk_app; do
  sleep 1
done

echo "[sahulatkar] Running database migrations..."
$COMPOSE run --rm gateway alembic -c /app/db/alembic.ini upgrade head

echo "[sahulatkar] Starting application services..."
$COMPOSE up -d gateway product-service credit-engine payment-orchestrator ledger-service notification-service

echo "[sahulatkar] All services started. Run 'make logs' to tail output."
