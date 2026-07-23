"""Admin API & Developer Tools — Phase 4 thin module."""
from __future__ import annotations

import hashlib
import secrets
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/developer", tags=["Admin Developer Tools"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("/api-keys")
async def list_api_keys(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT k.id, k.merchant_id, k.partner_name, k.key_prefix, k.scopes,
                       k.is_active, k.expires_at, k.last_used_at, k.created_at, m.name AS merchant_name
                FROM api_keys k
                LEFT JOIN merchants m ON m.id = k.merchant_id
                ORDER BY k.created_at DESC
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "merchant_id": r["merchant_id"],
                "merchant_name": r["merchant_name"],
                "partner_name": r["partner_name"],
                "key_prefix": r["key_prefix"],
                "scopes": r["scopes"] or [],
                "is_active": r["is_active"],
                "expires_at": _iso(r["expires_at"]),
                "last_used_at": _iso(r["last_used_at"]),
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ]
    }


class CreateApiKeyRequest(BaseModel):
    partner_name: str = Field(..., min_length=1, max_length=100)
    merchant_id: Optional[int] = None
    scopes: list[str] = Field(default_factory=lambda: ["read"])


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    payload: CreateApiKeyRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw_key = f"sk_live_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:10]

    row = (
        await db.execute(
            text(
                """
                INSERT INTO api_keys (merchant_id, partner_name, key_hash, key_prefix, scopes)
                VALUES (:merchant_id, :partner_name, :key_hash, :key_prefix, :scopes)
                RETURNING id, created_at
                """
            ),
            {
                "merchant_id": payload.merchant_id,
                "partner_name": payload.partner_name,
                "key_hash": key_hash,
                "key_prefix": key_prefix,
                "scopes": payload.scopes,
            },
        )
    ).mappings().one()

    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_developer", action="api_key_created",
        target_id=row["id"], changes={"partner_name": payload.partner_name, "scopes": payload.scopes},
        severity="critical",
    )
    await db.commit()
    return {
        "id": row["id"],
        "api_key": raw_key,
        "key_prefix": key_prefix,
        "created_at": _iso(row["created_at"]),
        "note": "This is the only time the full key is shown. Store it securely.",
    }


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(
    key_id: int,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.execute(text("SELECT id FROM api_keys WHERE id = :id"), {"id": key_id})
    if existing.one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API_KEY_NOT_FOUND")

    await db.execute(text("UPDATE api_keys SET is_active = false WHERE id = :id"), {"id": key_id})
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_developer", action="api_key_revoked",
        target_id=key_id, changes={}, severity="critical",
    )
    await db.commit()
    return {"id": key_id, "status": "revoked"}


@router.get("/webhooks")
async def list_webhooks(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT w.id, w.merchant_id, w.endpoint_url, w.events, w.is_active, w.created_at, m.name AS merchant_name
                FROM webhooks w
                LEFT JOIN merchants m ON m.id = w.merchant_id
                ORDER BY w.created_at DESC
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "merchant_id": r["merchant_id"],
                "merchant_name": r["merchant_name"],
                "endpoint_url": r["endpoint_url"],
                "events": r["events"] or [],
                "is_active": r["is_active"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.get("/integration-logs")
async def list_integration_logs(
    service_name: Optional[str] = None,
    success_only: Optional[bool] = None,
    page: int = 1,
    limit: int = 50,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if service_name:
        where_clauses.append("service_name = :service_name")
        params["service_name"] = service_name
    if success_only is not None:
        where_clauses.append("is_success = :success_only")
        params["success_only"] = success_only
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, service_name, operation, endpoint, method, response_code,
                       latency_ms, is_success, error_code, created_at
                FROM integration_logs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": r["id"],
                "service_name": r["service_name"],
                "operation": r["operation"],
                "endpoint": r["endpoint"],
                "method": r["method"],
                "response_code": r["response_code"],
                "latency_ms": r["latency_ms"],
                "is_success": r["is_success"],
                "error_code": r["error_code"],
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ]
    }


@router.get("/summary")
async def developer_summary(
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    active_keys = int(await db.scalar(text("SELECT COUNT(*) FROM api_keys WHERE is_active = true")) or 0)
    active_webhooks = int(await db.scalar(text("SELECT COUNT(*) FROM webhooks WHERE is_active = true")) or 0)
    success_rate_row = (
        await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE is_success = true) AS success_count,
                    COUNT(*) AS total_count
                FROM integration_logs
                WHERE created_at >= NOW() - INTERVAL '24 hours'
                """
            )
        )
    ).mappings().one()
    total = int(success_rate_row["total_count"] or 0)
    success_rate = round((int(success_rate_row["success_count"] or 0) / total * 100), 1) if total else None

    return {
        "active_api_keys": active_keys,
        "active_webhooks": active_webhooks,
        "integration_calls_24h": total,
        "integration_success_rate_24h": success_rate,
    }
