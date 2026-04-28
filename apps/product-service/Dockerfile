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
COPY apps/product-service/pyproject.toml /tmp/product-service/
COPY apps/product-service/src/ /tmp/product-service/src/
RUN pip install --no-cache-dir --prefix=/install /tmp/product-service/

# STAGE 2: Runtime
FROM python:3.12-slim AS runtime

WORKDIR /app

# Runtime dependencies including Playwright system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    # Playwright system dependencies (minimal set for chromium)
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxext6 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 libcairo2 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY apps/product-service/src/ /app/src/

# Security: Run as non-root user
# Note: Playwright might need some extra permissions for the browser, 
# but we start by running as appuser.
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

# Install Playwright browsers (in the user directory)
# We limit to chromium to save space
RUN playwright install chromium

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

EXPOSE 8000

ENV PYTHONPATH=/app
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
