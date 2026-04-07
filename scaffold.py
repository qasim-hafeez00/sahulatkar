import os

services = ['gateway', 'product-service', 'credit-engine', 'payment-orchestrator', 'ledger-service', 'notification-service']

pyproject_tmpl = """[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "sk-{service}"
version = "0.1.0"
description = "{service} for SahulatKar"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.29.0",
    "sk-shared"
]
"""

main_tmpl = """from fastapi import FastAPI

app = FastAPI(title="{service} API", version="0.1.0")

@app.get("/health")
async def health_check():
    return {{"status": "ok", "service": "{service}"}}
"""

dockerfile_tmpl = """FROM python:3.12-slim AS base
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \\
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY packages/shared-python/ /tmp/shared-python/
RUN pip install --no-cache-dir /tmp/shared-python/

COPY apps/{service}/pyproject.toml apps/{service}/
RUN pip install --no-cache-dir -e apps/{service}/

COPY apps/{service}/src/ apps/{service}/src/

RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
"""

for s in services:
    base = os.path.join('c:\\users\\seraphindra\\Desktop\\sahulatkar', 'apps', s)
    with open(os.path.join(base, 'pyproject.toml'), 'w') as f:
        f.write(pyproject_tmpl.format(service=s))
    with open(os.path.join(base, 'src', 'main.py'), 'w') as f:
        f.write(main_tmpl.format(service=s))
    with open(os.path.join(base, 'Dockerfile'), 'w') as f:
        f.write(dockerfile_tmpl.format(service=s))

print('Scaffolded FastAPI microservices')
