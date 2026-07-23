"""Admin Marketing & Growth — Phase 4 thin module."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.audit import record_audit_event
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/marketing", tags=["Admin Marketing"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("/campaigns")
async def list_campaigns(
    status_filter: Optional[str] = None,
    current_admin: AdminUser = Depends(RequirePermission("read_marketing")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_sql = "WHERE status = :status_filter" if status_filter else ""
    params: dict = {"status_filter": status_filter} if status_filter else {}
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, name, channel, budget, spend, start_date, end_date, status
                FROM marketing_campaigns
                {where_sql}
                ORDER BY created_at DESC
                """
            ),
            params,
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["name"],
                "channel": r["channel"],
                "budget": float(r["budget"]) if r["budget"] is not None else None,
                "spend": float(r["spend"] or 0),
                "start_date": _iso(r["start_date"]),
                "end_date": _iso(r["end_date"]),
                "status": r["status"],
            }
            for r in rows
        ]
    }


class CampaignRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    channel: Literal["meta_ads", "google", "sms_blast", "influencer", "email", "tiktok"]
    budget: Optional[float] = Field(default=None, ge=0)
    start_date: date
    end_date: Optional[date] = None
    target_segment: Optional[str] = None


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(
            text(
                """
                INSERT INTO marketing_campaigns (name, channel, budget, start_date, end_date, target_segment, created_by)
                VALUES (:name, :channel, :budget, :start_date, :end_date, :target_segment, :created_by)
                RETURNING id, created_at
                """
            ),
            {**payload.model_dump(), "created_by": current_admin.id},
        )
    ).mappings().one()
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_marketing", action="campaign_created",
        target_id=row["id"], changes={"name": payload.name, "channel": payload.channel},
    )
    await db.commit()
    return {"id": row["id"], "status": "draft", "created_at": _iso(row["created_at"])}


@router.get("/promo-codes")
async def list_promo_codes(
    active_only: bool = False,
    current_admin: AdminUser = Depends(RequirePermission("read_marketing")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    where_sql = "WHERE is_active = true" if active_only else ""
    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, code, promo_type, discount_value, discount_pct, usage_limit_total,
                       times_used, valid_from, valid_until, is_active
                FROM promotional_codes
                {where_sql}
                ORDER BY created_at DESC
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "code": r["code"],
                "promo_type": r["promo_type"],
                "discount_value": float(r["discount_value"]) if r["discount_value"] is not None else None,
                "discount_pct": float(r["discount_pct"]) if r["discount_pct"] is not None else None,
                "usage_limit_total": r["usage_limit_total"],
                "times_used": r["times_used"],
                "valid_from": _iso(r["valid_from"]),
                "valid_until": _iso(r["valid_until"]),
                "is_active": r["is_active"],
            }
            for r in rows
        ]
    }


class PromoCodeRequest(BaseModel):
    code: str = Field(..., min_length=3, max_length=30)
    promo_type: Literal["fee_waiver", "credit_bonus", "cashback_pct", "cashback_flat", "free_delivery"]
    discount_value: Optional[float] = Field(default=None, ge=0)
    discount_pct: Optional[float] = Field(default=None, ge=0, le=100)
    usage_limit_total: Optional[int] = Field(default=None, gt=0)
    valid_from: date
    valid_until: date


@router.post("/promo-codes", status_code=status.HTTP_201_CREATED)
async def create_promo_code(
    payload: PromoCodeRequest,
    request: Request,
    current_admin: AdminUser = Depends(RequirePermission("manage_system")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    existing = await db.scalar(text("SELECT id FROM promotional_codes WHERE code = :code"), {"code": payload.code})
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="PROMO_CODE_EXISTS")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO promotional_codes (
                    code, promo_type, discount_value, discount_pct, usage_limit_total,
                    valid_from, valid_until, created_by
                ) VALUES (
                    :code, :promo_type, :discount_value, :discount_pct, :usage_limit_total,
                    :valid_from, :valid_until, :created_by
                )
                RETURNING id, created_at
                """
            ),
            {**payload.model_dump(), "created_by": current_admin.id},
        )
    ).mappings().one()
    await record_audit_event(
        db=db, request=request, admin_user_id=current_admin.id,
        module="admin_marketing", action="promo_code_created",
        target_id=row["id"], changes={"code": payload.code},
    )
    await db.commit()
    return {"id": row["id"], "code": payload.code, "created_at": _iso(row["created_at"])}


@router.get("/referrals/summary")
async def referrals_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_marketing")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(text("SELECT status, COUNT(*) AS cnt FROM referrals GROUP BY status"))
    ).mappings().all()
    total_paid = await db.scalar(
        text("SELECT COALESCE(SUM(referrer_reward_amount + referred_reward_amount), 0) FROM referrals WHERE status = 'completed'")
    )
    return {
        "by_status": {r["status"]: int(r["cnt"]) for r in rows},
        "total_rewards_paid": float(total_paid or 0),
    }


@router.get("/ab-tests")
async def list_ab_tests(
    current_admin: AdminUser = Depends(RequirePermission("read_marketing")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT id, experiment_name, status, start_date, end_date, variants, winner_variant
                FROM ab_test_experiments
                ORDER BY created_at DESC
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "name": r["experiment_name"],
                "status": r["status"],
                "start_date": _iso(r["start_date"]),
                "end_date": _iso(r["end_date"]),
                "variants": r["variants"],
                "winner_variant": r["winner_variant"],
            }
            for r in rows
        ]
    }
