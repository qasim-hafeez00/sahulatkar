"""
Session-scoped fixtures that bring up the FULL SahulatKar docker-compose
stack (all 6 real microservices + real Postgres + real Redis + the mock
merchant fixture), wait for it to be genuinely ready, run migrations, hand
tests base URLs to talk to it over real HTTP, and tear it down afterwards.

No per-service mocking happens anywhere in this file or in
test_order_lifecycle.py -- every HTTP call in the test suite goes over the
network to a real container, exactly as `docker compose up` would run this
stack in any other environment.

Run manually with:
    docker compose -f infra/docker/docker-compose.yml \
                    -f infra/docker/docker-compose.e2e.yml \
                    up -d --build
    pytest tests/e2e/ -v

...or just run `pytest tests/e2e/` directly -- this fixture does the same
`up`/migrate/health-wait dance itself and tears the stack down at the end of
the session. See tests/e2e/README.md for details and troubleshooting.
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.yml"
E2E_COMPOSE = REPO_ROOT / "infra" / "docker" / "docker-compose.e2e.yml"

# BUG FIX (found bringing this stack up while building this test suite):
# docker-compose.yml's product-service-{scraping,checkout,vcn-verifier,
# price-staleness}-worker / -dlq-monitor / -execution-reaper services all
# hardcode `image: docker-product-service` rather than building their own
# image, intentionally reusing product-service's build (see the long comment
# above product-service-scraping-worker in that file). That image tag is only
# correct when the Compose *project* name is exactly "docker" -- Compose's
# default tag for a built service with no explicit `image:` is
# "<project>-<service>", which is "docker-product-service" only if the
# project name is "docker". Nothing in the repo enforces or documents running
# compose from inside infra/docker (which is what makes the project name
# default to "docker"), and this file's own container_name: fields (sk-*) are
# fixed regardless of project name anyway, so there is no safe way to use a
# different, disposable project name without colliding with those fixed
# names. Pinning PROJECT to "docker" here matches the convention the base
# compose file already assumes, and docker-compose.e2e.yml now also pins
# product-service's own image tag explicitly so this no longer depends on an
# undocumented cwd assumption either way.
PROJECT = "docker"

# Services with a real, independently buildable Dockerfile. Build these
# explicitly with `docker compose build <names>` -- NOT `up --build`, which
# would also try (and fail) to build the worker services below: they inherit
# an anonymous `build: {context: ../../}` from docker-compose.yml's
# x-python-service anchor with no dockerfile path, which only resolves when
# nothing ever asks compose to build them directly. Live-verified: `up -d
# --build` fails immediately with "open Dockerfile: no such file or
# directory" for product-service-vcn-verifier (and would for every other
# worker sharing that anchor) the moment --build is passed for the whole
# stack, from repo root.
_BUILDABLE_SERVICES = [
    "gateway",
    "product-service",
    "credit-engine",
    "payment-orchestrator",
    "ledger-service",
    "notification-service",
    "e2e-mock-merchant",
]

# Full set of services this test suite needs running. Deliberately excludes
# web-customer / web-admin / pgadmin / product-service-dlq-monitor /
# product-service-price-staleness-worker / product-service-execution-reaper
# -- none of them sit on the order-lifecycle path this suite exercises, and
# skipping their builds saves real wall-clock time (web-customer/web-admin
# build a full Next.js image).
_RUN_SERVICES = _BUILDABLE_SERVICES + [
    "postgres",
    "redis",
    "pgbouncer",
    "product-service-scraping-worker",
    "product-service-checkout-worker",
    "product-service-vcn-verifier",
]

# Host-mapped ports (see docker-compose.yml's `ports:` for each service and
# docker-compose.e2e.yml for e2e-mock-merchant's 8099:8080 mapping).
SERVICE_PORTS = {
    "gateway": 8000,
    "product-service": 8001,
    "credit-engine": 8002,
    "payment-orchestrator": 8003,
    "ledger-service": 8004,
    "notification-service": 8005,
    "e2e-mock-merchant": 8099,
}

_HEALTH_PATH = {
    # All 6 real microservices + the mock merchant expose a plain GET /health
    # at the root (verified against each service's src/main.py).
    name: "/health" for name in SERVICE_PORTS
}

_BUILD_TIMEOUT_SECONDS = 1800  # product-service ships Playwright/Chromium; first build can take many minutes.
_UP_TIMEOUT_SECONDS = 180
_MIGRATE_TIMEOUT_SECONDS = 180
_POSTGRES_HEALTHY_TIMEOUT_SECONDS = 90
_SERVICE_HEALTH_TIMEOUT_SECONDS = 150


def _compose_argv(*args: str) -> list[str]:
    return [
        "docker", "compose",
        "-p", PROJECT,
        "-f", str(BASE_COMPOSE),
        "-f", str(E2E_COMPOSE),
        *args,
    ]


def _run(argv: list[str], timeout: float | None = None, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(
        argv, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed (exit {result.returncode}): {' '.join(argv)}\n"
            f"--- stdout (tail) ---\n{result.stdout[-4000:]}\n"
            f"--- stderr (tail) ---\n{result.stderr[-4000:]}"
        )
    return result


def _dump_logs_and_status() -> None:
    """Best-effort diagnostics dump for a failed bring-up, so a CI/dev run
    that fails never leaves the operator guessing."""
    print("\n\n===== E2E STACK FAILURE: dumping `docker compose ps` and logs =====\n")
    try:
        ps = _run(_compose_argv("ps", "-a"), timeout=30, check=False)
        print(ps.stdout)
        print(ps.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"(failed to run `compose ps`: {exc})")
    try:
        logs = _run(_compose_argv("logs", "--tail=200"), timeout=60, check=False)
        print(logs.stdout[-25000:])
        print(logs.stderr[-5000:])
    except Exception as exc:  # noqa: BLE001
        print(f"(failed to dump `compose logs`: {exc})")
    print("\n===== end diagnostics =====\n")


def _wait_for_postgres_healthy() -> None:
    deadline = time.monotonic() + _POSTGRES_HEALTHY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        result = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", "sk-postgres"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == "healthy":
            return
        time.sleep(2)
    raise RuntimeError(
        f"Postgres (container sk-postgres) did not become healthy within "
        f"{_POSTGRES_HEALTHY_TIMEOUT_SECONDS}s."
    )


def _run_migrations() -> None:
    # BUG FIX (found running this exact command while building this suite --
    # also reproducible via the Makefile's own `make migrate` target, which
    # runs the identical `docker compose run --rm gateway alembic ... upgrade
    # head`, so this is a real local-dev bug, not an E2E-only one). Two
    # independent issues stacked here, both live-verified by hand:
    #
    # 1. Wrong role/route: gateway's normal DATABASE_URL (docker-compose.yml)
    #    points at `pgbouncer:6432` as the `sk_app` role, which is correct
    #    for normal request traffic but wrong for migrations two ways over:
    #      a) `sk_app` lacks DDL privileges on the public schema at all
    #         (`permission denied for schema public` on `CREATE TABLE
    #         alembic_version`) -- `sk_migrations` (see infra/docker/
    #         postgres/init.sql) is the role actually granted schema
    #         ownership, specifically for this.
    #      b) pgbouncer here runs PGBOUNCER_POOL_MODE=transaction, under
    #         which asyncpg's prepared-statement cache can collide across
    #         backend connections pgbouncer transparently swaps a single
    #         logical connection between --
    #         `asyncpg.exceptions.DuplicatePreparedStatementError: prepared
    #         statement "__asyncpg_stmt_1__" already exists` (a well-known,
    #         documented asyncpg/pgbouncer incompatibility explained in the
    #         error's own hint text). DDL should never run through a
    #         transaction-pooled connection regardless of asyncpg specifics,
    #         so this goes straight to `postgres:5432` as `sk_migrations`,
    #         bypassing pgbouncer entirely, for this one-off run only --
    #         nothing else in the stack is affected.
    # 2. `docker compose run --rm gateway alembic -c /app/db/alembic.ini
    #    upgrade head` invoked directly (exec form, no shell) reproducibly
    #    fails with `FAILED: No 'script_location' key found in
    #    configuration.` even though the exact same alembic.ini parses fine
    #    in isolation (verified directly via `alembic.config.Config(...)
    #    .get_main_option('script_location')` in a one-off `python -c`
    #    inside the same image). The identical command wrapped in
    #    `sh -c "..."` does not hit this at all and proceeds straight to
    #    real DB connection errors. Root cause not fully isolated (a
    #    Compose/exec-form argv-handling quirk on this host, not anything in
    #    this repo's alembic.ini or env.py) -- wrapping in `sh -c` is a
    #    correct, harmless workaround either way.
    direct_db_url = "postgresql+asyncpg://sk_migrations:localdev123@postgres:5432/sahulatkar"
    _run(
        _compose_argv(
            "run", "--rm", "-e", f"DATABASE_URL={direct_db_url}", "gateway",
            "sh", "-c", "alembic -c /app/db/alembic.ini upgrade head",
        ),
        timeout=_MIGRATE_TIMEOUT_SECONDS,
    )


def _wait_for_all_health() -> None:
    deadline = time.monotonic() + _SERVICE_HEALTH_TIMEOUT_SECONDS
    pending = dict(SERVICE_PORTS)
    with httpx.Client(timeout=5.0) as client:
        while pending and time.monotonic() < deadline:
            for name in list(pending):
                port = pending[name]
                try:
                    resp = client.get(f"http://localhost:{port}{_HEALTH_PATH[name]}")
                    if resp.status_code == 200:
                        pending.pop(name)
                except httpx.HTTPError:
                    pass
            if pending:
                time.sleep(2)
    if pending:
        raise RuntimeError(
            f"These services never returned a healthy /health within "
            f"{_SERVICE_HEALTH_TIMEOUT_SECONDS}s: {sorted(pending)}"
        )


@pytest.fixture(scope="session")
def docker_stack():
    """Brings the full real stack up once for the whole test session and
    tears it down (`down -v`) at the end. Fails fast with a clear message
    (and dumps compose logs) if Docker isn't running or the stack never
    becomes healthy -- never hangs indefinitely."""
    info = subprocess.run(["docker", "info"], capture_output=True, text=True)
    if info.returncode != 0:
        pytest.fail(
            "Docker does not appear to be running (`docker info` failed). "
            "Start Docker Desktop and retry.\n" + info.stderr
        )

    print(f"\n[e2e] Building {len(_BUILDABLE_SERVICES)} service images "
          f"(product-service ships Playwright/Chromium -- first build can take several minutes)...")
    _run(_compose_argv("build", *_BUILDABLE_SERVICES), timeout=_BUILD_TIMEOUT_SECONDS)

    print(f"[e2e] Starting {len(_RUN_SERVICES)} containers...")
    _run(_compose_argv("up", "-d", *_RUN_SERVICES), timeout=_UP_TIMEOUT_SECONDS)

    try:
        print("[e2e] Waiting for Postgres to report healthy...")
        _wait_for_postgres_healthy()

        print("[e2e] Running Alembic migrations...")
        _run_migrations()

        print("[e2e] Waiting for all services' /health to return 200...")
        _wait_for_all_health()

        print("[e2e] Stack is up and healthy.")
        yield {"ports": dict(SERVICE_PORTS)}
    except Exception:
        _dump_logs_and_status()
        raise
    finally:
        print("[e2e] Tearing down stack (`down -v`)...")
        _run(_compose_argv("down", "-v"), timeout=120, check=False)


@pytest.fixture(scope="session")
def base_urls(docker_stack) -> dict[str, str]:
    return {name: f"http://localhost:{port}" for name, port in docker_stack["ports"].items()}


@pytest_asyncio.fixture(autouse=True)
async def _reset_gateway_rate_limits(docker_stack):
    """Flushes Gateway's sliding-window rate-limit keys (`sk:rate_limit:*`
    in Redis logical DB 0 -- see core/rate_limit.py) before every test.

    Real finding from running this suite as it grew past a single test: with
    more than a handful of test functions all hitting Gateway from the same
    test-runner IP within a single pytest session, the REAL production rate
    limiter (100 req/min global per IP, 10 req/min on /auth/verify-otp and
    /auth/login specifically -- both hardcoded literals in
    apps/gateway/src/core/rate_limit.py, not env-configurable) starts
    rejecting requests partway through the run with 429s, which then surface
    as confusing, seemingly-nondeterministic failures in whichever test
    happens to be running when a window fills (a stalled offer poll, an
    unexpected KYC status, a 500 on an unrelated endpoint downstream of a
    failed auth call). The middleware's only bypass is `ENVIRONMENT ==
    "test"`, which this stack deliberately does NOT run as (it runs
    ENVIRONMENT=local specifically so the hardcoded "123456" registration
    OTP and dev_otp echoing behave exactly as documented for a new frontend
    team -- see auth.py -- and test_order_lifecycle.py asserts on the literal
    "123456" value). Rather than weakening a real security control or
    breaking that assertion, this fixture just clears the counters between
    tests -- the same category of direct-infra test-orchestration access
    test_order_lifecycle.py's own docstring already sanctions.
    """
    import redis.asyncio as aioredis

    client = aioredis.from_url("redis://:localdev123@localhost:6379/0")
    try:
        async for key in client.scan_iter(match="sk:rate_limit:*"):
            await client.delete(key)
    finally:
        await client.aclose()
    yield
