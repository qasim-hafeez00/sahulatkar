from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from src.core.dependencies import get_current_user, get_db

router = APIRouter(prefix="/profile", tags=["profile"])


class NotificationPreferencesRequest(BaseModel):
    sms_installment_reminders: bool = True
    push_delivery_updates: bool = True
    email_receipts: bool = True
    sms_marketing: bool = False
    push_marketing: bool = False


@router.get("/notifications")
async def get_notification_preferences(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-09: Get user notification preferences."""
    try:
        q = text(
            """
            SELECT sms_installment_reminders, push_delivery_updates, email_receipts,
                   sms_marketing, push_marketing
            FROM notification_preferences
            WHERE user_id = :user_id
            """
        )
        row = (await db.execute(q, {"user_id": user.id})).mappings().one_or_none()
    except Exception:
        row = None

    if not row:
        return {
            "user_id": user.id,
            "sms_installment_reminders": True,
            "push_delivery_updates": True,
            "email_receipts": True,
            "sms_marketing": False,
            "push_marketing": False,
        }

    return {
        "user_id": user.id,
        "sms_installment_reminders": bool(row["sms_installment_reminders"]),
        "push_delivery_updates": bool(row["push_delivery_updates"]),
        "email_receipts": bool(row["email_receipts"]),
        "sms_marketing": bool(row["sms_marketing"]),
        "push_marketing": bool(row["push_marketing"]),
    }


@router.put("/notifications")
async def update_notification_preferences(
    payload: NotificationPreferencesRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-09: Update user notification preferences (upsert)."""
    try:
        existing = (
            await db.execute(
                text("SELECT id FROM notification_preferences WHERE user_id = :user_id"),
                {"user_id": user.id},
            )
        ).mappings().one_or_none()

        if existing:
            await db.execute(
                text(
                    """
                    UPDATE notification_preferences
                    SET sms_installment_reminders = :sms_ir,
                        push_delivery_updates = :push_du,
                        email_receipts = :email_r,
                        sms_marketing = :sms_m,
                        push_marketing = :push_m
                    WHERE user_id = :user_id
                    """
                ),
                {
                    "user_id": user.id,
                    "sms_ir": payload.sms_installment_reminders,
                    "push_du": payload.push_delivery_updates,
                    "email_r": payload.email_receipts,
                    "sms_m": payload.sms_marketing,
                    "push_m": payload.push_marketing,
                },
            )
        else:
            await db.execute(
                text(
                    """
                    INSERT INTO notification_preferences
                        (user_id, sms_installment_reminders, push_delivery_updates,
                         email_receipts, sms_marketing, push_marketing)
                    VALUES (:user_id, :sms_ir, :push_du, :email_r, :sms_m, :push_m)
                    """
                ),
                {
                    "user_id": user.id,
                    "sms_ir": payload.sms_installment_reminders,
                    "push_du": payload.push_delivery_updates,
                    "email_r": payload.email_receipts,
                    "sms_m": payload.sms_marketing,
                    "push_m": payload.push_marketing,
                },
            )
        await db.commit()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"NOTIFICATION_PREFERENCES_TABLE_UNAVAILABLE: {exc}",
        )

    return {
        "user_id": user.id,
        "sms_installment_reminders": payload.sms_installment_reminders,
        "push_delivery_updates": payload.push_delivery_updates,
        "email_receipts": payload.email_receipts,
        "sms_marketing": payload.sms_marketing,
        "push_marketing": payload.push_marketing,
        "updated": True,
    }


@router.get("/referrals")
async def get_referral_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """MISS-15: User referral stats."""
    try:
        q = text(
            """
            SELECT COUNT(*) AS referral_count
            FROM users
            WHERE referred_by = :user_id AND deleted_at IS NULL
            """
        )
        row = (await db.execute(q, {"user_id": user.id})).mappings().one_or_none()
        referral_count = int(row["referral_count"] or 0) if row else 0
    except Exception:
        referral_count = 0

    referral_code = getattr(user, "referral_code", None) or f"SK{user.id:06d}"
    return {
        "user_id": user.id,
        "referral_code": referral_code,
        "referral_count": referral_count,
        "reward_per_referral": "TBD",
    }
