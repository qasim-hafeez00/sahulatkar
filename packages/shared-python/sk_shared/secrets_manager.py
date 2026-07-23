"""Generic AWS Secrets Manager loader for pydantic-settings ``Settings`` classes.

Implements, as a single reusable helper, the loading half of the pattern
documented in ``docs/SECRETS_MANAGER_MIGRATION.md`` (see its "Step 3: Update
Ledger Config" section) -- generalized so every backend service can call the
*same* function instead of each service hand-rolling its own
``load_settings_from_secrets_manager``. The doc's own example is scoped to
ledger-service and hardcodes the ``ledger/prod/*`` secret namespace; this
module parameterizes that by service name, environment, and each service's
own (real, current) list of credential fields.

Usage (mirrors ``docs/SECRETS_MANAGER_MIGRATION.md``'s ``get_settings()``)::

    import os
    from sk_shared.secrets_manager import load_secrets_manager_overrides, SecretsManagerLoadError

    class Settings(BaseSettings):
        DATABASE_URL: str = "postgresql+asyncpg://..."
        REDIS_URL: str = "redis://localhost:6379/0"
        ...

    _SECRETS_MANAGER_FIELD_MAP = {
        "database-url": "DATABASE_URL",
        "redis-url": "REDIS_URL",
    }

    def get_settings() -> Settings:
        # Local dev / tests never set AWS_REGION, so this branch is dead
        # code for them -- zero behavior change without AWS infrastructure.
        if os.getenv("AWS_REGION"):
            try:
                overrides = load_secrets_manager_overrides(
                    service_prefix="my-service",
                    environment=os.getenv("ENVIRONMENT", "prod"),
                    secret_field_map=_SECRETS_MANAGER_FIELD_MAP,
                    region=os.getenv("AWS_REGION"),
                )
                return Settings(**overrides)
            except SecretsManagerLoadError as exc:
                logger.warning("Falling back to env vars/.env: %s", exc)
        return Settings()

    settings = get_settings()

Design notes / deliberate departures from the doc's literal example code:

- **Synchronous, not ``async def`` + ``asyncio.run()``.** boto3's
  Secrets Manager client is blocking I/O regardless; wrapping it in
  ``async def`` and driving it with ``asyncio.run()`` (as the doc's example
  does) adds no real concurrency benefit and would raise ``RuntimeError:
  asyncio.run() cannot be called from a running event loop`` if
  ``get_settings()`` is ever imported from inside an already-running loop.
  A plain function avoids that failure mode entirely.
- **Returns ``{settings_field_name: value}``, not ``{ENV_VAR_NAME: value}``.**
  The doc's own example builds a dict keyed by *env var* names (e.g.
  ``"DATABASE_URL"``) but its ledger ``Settings`` class uses *lowercase*
  field names (``database_url``) -- passing ``Settings(**{"DATABASE_URL": ...})``
  would silently fail to populate ``database_url`` (pydantic matches
  constructor kwargs to field names, not to case-insensitive env var
  aliases -- that case-insensitive matching only applies to the env-var
  *source*, not to values passed directly as ``__init__`` kwargs). Callers
  here supply the exact field name as the ``secret_field_map`` value, so the
  same dict works for both UPPER_SNAKE (gateway, product-service,
  payment-orchestrator, notification-service) and lower_snake
  (ledger-service) ``Settings`` classes.
- **boto3 is imported lazily**, inside :func:`_get_secretsmanager_client`,
  not at module import time -- mirroring the existing lazy-``import aioboto3``
  convention in ``apps/ledger-service/src/core/audit_storage.py``. Since this
  whole path is only reachable when ``AWS_REGION`` is set, no local/test run
  ever imports boto3 through this module.
- **All-or-nothing per call**, matching the doc: if any secret named in
  ``secret_field_map`` is missing, :class:`SecretsManagerLoadError` is raised
  and *none* of the partially-fetched overrides are used by the caller (the
  caller's ``except`` falls through to ``Settings()`` -- plain env vars/.env
  -- for every field, not just the missing one). This preserves the doc's
  intended rollback story: a broken/partial Secrets Manager setup must not
  produce a half-secrets/half-defaults hybrid config.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Mapping

logger = logging.getLogger(__name__)

__all__ = [
    "SecretsManagerLoadError",
    "load_secrets_manager_overrides",
]


class SecretsManagerLoadError(ValueError):
    """Raised when one or more required secrets can't be loaded from AWS Secrets Manager.

    Subclasses ``ValueError`` on purpose: ``docs/SECRETS_MANAGER_MIGRATION.md``
    documents callers doing ``except ValueError`` around the load-and-fall-back
    step, so this stays a drop-in match for that documented pattern.
    """


@lru_cache(maxsize=None)
def _get_secretsmanager_client(region: str):
    """Return a cached boto3 Secrets Manager client for ``region``.

    Cached per-region (rather than a single global client, as the doc's
    example does) since a single process could in principle load secrets for
    more than one region; in practice every service only ever calls this
    with one region, so this degenerates to the same one-client-per-process
    behavior the doc describes.
    """
    import boto3  # Lazy: only services that set AWS_REGION need boto3 installed/imported.

    return boto3.client("secretsmanager", region_name=region)


def load_secrets_manager_overrides(
    service_prefix: str,
    environment: str,
    secret_field_map: Mapping[str, str],
    region: str,
) -> dict[str, Any]:
    """Fetch a flat dict of ``Settings`` field overrides from AWS Secrets Manager.

    Secrets are expected to live at ``<service_prefix>/<environment>/<secret_key>``
    (dash-case), e.g. ``gateway/prod/database-url`` or
    ``ledger-service/staging/internal-api-token`` -- one flat namespace per
    service per environment, matching the IAM policy scoping documented in
    ``docs/SECRETS_MANAGER_MIGRATION.md`` (Step 4) and implemented in
    ``infra/terraform/modules/iam``.

    Args:
        service_prefix: Secrets Manager namespace for this service, e.g.
            ``"gateway"``, ``"product-service"``, ``"payment-orchestrator"``,
            ``"ledger-service"``, ``"notification-service"``.
        environment: deployment environment segment, e.g. ``"prod"`` /
            ``"staging"``.
        secret_field_map: ``{secret_key: settings_field_name}``, e.g.
            ``{"database-url": "DATABASE_URL"}``. ``settings_field_name`` must
            be the exact attribute name on the caller's pydantic-settings
            ``Settings`` class (case matters -- see module docstring), since
            the returned dict is meant to be splatted straight into
            ``Settings(**overrides)``.
        region: AWS region to query.

    Returns:
        ``{settings_field_name: value}``, ready to pass as
        ``Settings(**overrides)``. If a secret's ``SecretString`` parses as a
        JSON *object*, that object's own keys/values are merged into the
        result instead of using ``settings_field_name`` -- this lets one
        Secrets Manager entry back several ``Settings`` fields at once (the
        JSON object's keys must themselves already match target field names
        for this to have any effect). Otherwise the raw string is used as-is.

    Raises:
        SecretsManagerLoadError: if any secret named in ``secret_field_map``
            is missing (``ResourceNotFoundException``) or any other AWS API
            error occurs. Callers should catch this (it is a ``ValueError``)
            and fall back to plain env vars/.env, exactly as
            ``get_settings()`` does in the migration doc.
    """
    if not secret_field_map:
        return {}

    client = _get_secretsmanager_client(region)

    loaded: dict[str, Any] = {}
    missing: list[str] = []

    for secret_key, field_name in secret_field_map.items():
        secret_name = f"{service_prefix}/{environment}/{secret_key}"
        try:
            response = client.get_secret_value(SecretId=secret_name)
        except client.exceptions.ResourceNotFoundException:
            missing.append(secret_name)
            continue
        except Exception as exc:  # noqa: BLE001 - re-raised below as SecretsManagerLoadError
            raise SecretsManagerLoadError(
                f"Failed to load secret {secret_name!r} from AWS Secrets Manager: {exc}"
            ) from exc

        raw_value = response.get("SecretString", "")
        try:
            parsed = json.loads(raw_value)
        except (json.JSONDecodeError, TypeError):
            loaded[field_name] = raw_value
        else:
            if isinstance(parsed, dict):
                loaded.update(parsed)
            else:
                loaded[field_name] = raw_value

    if missing:
        raise SecretsManagerLoadError(
            f"Missing secrets in AWS Secrets Manager for '{service_prefix}/{environment}': "
            + ", ".join(missing)
        )

    return loaded
