"""Shared read path for admin-configurable SystemParameter values.

Previously, apps/gateway/src/api/v1/admin_system.py had full CRUD (with caching
and audit logging) for parameters like down_payment_pct, profit_rate_3m/4m/6m/12m,
max_active_orders, and wakalah/murabaha_validity_days -- but nothing outside that
router ever read SystemParameter back. Real values were hardcoded in
order_service.py and contract_generator.py, so an admin changing these via the
panel saw the change "saved" and audited with zero effect on live contracts.

This module extracts the admin GET endpoint's own load-effective-parameters
logic (DB rows layered over defaults, same Redis cache keyed by version) into a
reusable function so order_service.py/contract_generator.py read the exact same
values an admin would see in the panel, with correct types.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.admin import SystemParameter
from sk_shared.redis_client import RedisClient

from src.api.v1.admin_system import _DEFAULTS, _PARAM_CACHE_VERSION_KEY, _cache_key_for_version, _PARAM_CACHE_TTL


def _coerce(key: str, raw: Any) -> Any:
    """DB values are always stored as strings (see admin_system.py's PUT handler);
    coerce back to the type of the corresponding default so callers get an int/
    float/bool, not a string, exactly like the value they set in the admin UI."""
    if not isinstance(raw, str):
        return raw
    default = _DEFAULTS.get(key)
    try:
        if isinstance(default, bool):
            return raw.strip().lower() in ("1", "true", "yes", "on")
        if isinstance(default, int):
            return int(float(raw))
        if isinstance(default, float):
            return float(raw)
    except (TypeError, ValueError):
        return default
    return raw


async def get_effective_system_parameters(
    db: AsyncSession, redis: RedisClient | None = None
) -> dict[str, Any]:
    """Effective parameters: DB overrides layered on top of _DEFAULTS, each
    coerced to its default's type. Uses the same version-tagged Redis cache as
    GET /admin/system/parameters when a redis client is available; falls back
    to a direct DB read (still correct, just uncached) when it isn't."""
    if redis is not None:
        try:
            version_raw = await redis.get(_PARAM_CACHE_VERSION_KEY)
            cache_version = int(version_raw or 1)
            cached = await redis.get(_cache_key_for_version(cache_version))
            if cached:
                raw_params = json.loads(cached)
                return {k: _coerce(k, v) for k, v in raw_params.items()}
        except Exception:
            pass  # cache is a pure optimization here; fall through to a DB read

    rows = (
        await db.execute(select(SystemParameter).where(SystemParameter.deleted_at.is_(None)))
    ).scalars().all()
    db_params = {r.param_key: r.param_value for r in rows}
    merged = {**_DEFAULTS, **db_params}

    if redis is not None:
        try:
            version_raw = await redis.get(_PARAM_CACHE_VERSION_KEY)
            cache_version = int(version_raw or 1)
            await redis.set(_cache_key_for_version(cache_version), json.dumps(merged), _PARAM_CACHE_TTL)
        except Exception:
            pass

    return {k: _coerce(k, v) for k, v in merged.items()}


async def get_system_parameter(db: AsyncSession, key: str, redis: RedisClient | None = None) -> Any:
    """Convenience accessor for a single parameter, typed and defaulted."""
    params = await get_effective_system_parameters(db, redis)
    return params.get(key, _DEFAULTS.get(key))
