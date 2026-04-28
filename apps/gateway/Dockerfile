# STAGE 1: Builder
FROM python:3.12-slim AS builder

WORKDIR /build

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install shared package
COPY packages/shared-python/ /tmp/shared-python/
RUN pip install --no-cache-dir --prefix=/install /tmp/shared-python/

# Install service dependencies (copy pyproject.toml + src so hatchling can resolve metadata)
COPY apps/gateway/pyproject.toml /tmp/gateway/
COPY apps/gateway/src/ /tmp/gateway/src/
RUN pip install --no-cache-dir --prefix=/install /tmp/gateway/

# STAGE 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && \
    rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY apps/gateway/src/ /app/src/

# Security: Run as non-root user
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENV PYTHONPATH=/app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
