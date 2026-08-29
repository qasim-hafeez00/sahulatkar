# STAGE 1: Builder
FROM python:3.14-slim AS builder

WORKDIR /build

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install shared package
COPY packages/shared-python/ /tmp/shared-python/
RUN pip install --no-cache-dir --prefix=/install /tmp/shared-python/

# Install service runtime dependencies (src is COPY'd at runtime, not installed as a package)
COPY apps/gateway/pyproject.toml /tmp/gateway.toml
RUN python3 -c "import tomllib,subprocess,sys; cfg=tomllib.load(open('/tmp/gateway.toml','rb')); deps=[d for d in cfg['project']['dependencies'] if not d.startswith('sk-')]; subprocess.run([sys.executable,'-m','pip','install','--no-cache-dir','--prefix=/install']+deps,check=True)"

# STAGE 2: Runtime
FROM python:3.14-slim AS runtime

WORKDIR /app

# Runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY apps/gateway/src/ /app/src/

# BUG FIX (found running the E2E test's migration step against a real built
# image): this Dockerfile never copied db/ in at all, so
# `alembic -c /app/db/alembic.ini upgrade head` -- the exact command
# documented by both the Makefile's `migrate` target and
# infra/k8s/base/migration-job.yaml -- has never actually worked against a
# built gateway image; it failed with "No 'script_location' key found in
# configuration" because alembic silently treats the missing ini path as an
# empty config rather than erroring on a missing file. db/migrations/
# alembic.ini's own `script_location = db/migrations` is a path relative to
# the process's cwd (WORKDIR /app here), so alembic.ini itself needs to live
# at /app/db/alembic.ini (matching the documented -c path) while env.py/
# script.py.mako/versions/ live one level down at /app/db/migrations/ --
# copying db/migrations/ twice (once flattened to db/, once nested under
# db/migrations/) gets both paths right with no change to alembic.ini itself.
COPY db/migrations/ /app/db/migrations/
COPY db/migrations/alembic.ini /app/db/alembic.ini

# Security: Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)"

EXPOSE 8000

ENV PYTHONPATH=/app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
