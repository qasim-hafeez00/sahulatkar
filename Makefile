# SahulatKar — developer convenience targets
# Works on Linux, macOS, and WSL.  Windows users: use start_all.ps1 or WSL.

COMPOSE := docker compose -f infra/docker/docker-compose.yml
PYTHON   := python3

.PHONY: help up down restart migrate logs ps test lint build-shared

help:
	@echo "Available targets:"
	@echo "  up            Start all services (docker compose up -d)"
	@echo "  down          Stop all services"
	@echo "  restart       Restart all services"
	@echo "  migrate       Run Alembic migrations (alembic upgrade head)"
	@echo "  migrate-down  Roll back last migration (alembic downgrade -1)"
	@echo "  logs          Tail logs for all services"
	@echo "  ps            Show running containers"
	@echo "  test          Run pytest for all services"
	@echo "  lint          Run ruff + mypy across all Python services"
	@echo "  build-shared  Reinstall shared package in editable mode"

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

migrate:
	$(COMPOSE) run --rm gateway alembic -c /app/db/alembic.ini upgrade head

migrate-down:
	$(COMPOSE) run --rm gateway alembic -c /app/db/alembic.ini downgrade -1

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

test:
	@for svc in gateway product-service credit-engine payment-orchestrator ledger-service notification-service; do \
		echo "=== Testing $$svc ==="; \
		$(PYTHON) -m pytest apps/$$svc/tests/ -q --tb=short || exit 1; \
	done

lint:
	@for path in apps/gateway apps/product-service apps/credit-engine apps/payment-orchestrator apps/ledger-service apps/notification-service packages/shared-python; do \
		echo "=== Linting $$path ==="; \
		ruff check $$path || exit 1; \
		mypy $$path --ignore-missing-imports || exit 1; \
	done

build-shared:
	pip install -e packages/shared-python
