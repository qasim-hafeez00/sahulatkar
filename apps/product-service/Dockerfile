FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY packages/shared-python/ /tmp/shared-python/
RUN pip install --no-cache-dir /tmp/shared-python/

COPY apps/product-service/pyproject.toml apps/product-service/
RUN pip install --no-cache-dir -e apps/product-service/

COPY apps/product-service/src/ apps/product-service/src/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
