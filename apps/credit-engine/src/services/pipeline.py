import time
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.layers import (
    XGBoostScorer,
    run_alt_data_signal,
    run_hard_blocks,
    run_identity_signal,
    run_order_overlay,
    run_portfolio_concentration,
    run_velocity_checks,
)
from sk_shared.constants import RedisNS
from sk_shared.models.credit import BlacklistedEntity, CreditApplication, CreditLimitHistory, RiskAssessment
from sk_shared.redis_client import RedisClient


class CreditPipelineService:
    def __init__(self, db_session: AsyncSession, redis_client: RedisClient):
        self.db = db_session
        self.redis = redis_client
        self.scorer = XGBoostScorer()

    async def evaluate_credit(
        self,
        user_id: str,
        order_amount: float,
        product_category: str = "general",
        is_first_order: bool = False,
    ) -> dict[str, Any]:
        start_time = time.time()

        is_hard_blocked, reason, hard_block_flags = await run_hard_blocks(
            db=self.db,
            redis_client=self.redis,
            user_uuid=user_id,
            product_category=product_category,
        )
        if is_hard_blocked:
            return self._build_rejection(reason or "Hard block triggered", start_time, hard_block_flags)

        is_velocity_blocked, velocity_reason, velocity_flags = await run_velocity_checks(self.redis, user_id)
        if is_velocity_blocked:
            return self._build_rejection(velocity_reason or "Velocity block triggered", start_time, velocity_flags)

        identity_score, identity_flags = await run_identity_signal(self.db, user_id)
        alt_data = await run_alt_data_signal(user_id)

        ml_result = self.scorer.score(
            {
                "identity_score": identity_score,
                "alt_data_score": alt_data["wallet_activity_score"],
            }
        )

        if ml_result.score < settings.auto_decline_below:
            return self._build_rejection("Credit score below acceptable threshold", start_time, ["score_below_threshold"])

        limit, down_payment, is_prod_blocked, prod_reason, overlay_flags = run_order_overlay(
            base_limit=ml_result.base_limit,
            base_down_payment=ml_result.down_payment_pct,
            category=product_category,
        )
        if is_prod_blocked:
            return self._build_rejection(prod_reason or "Prohibited category", start_time, overlay_flags)

        is_portfolio_blocked, portfolio_reason, portfolio_flags = await run_portfolio_concentration(
            db=self.db,
            user_id=user_id,
            requested_amount=order_amount,
            maximum_limit=settings.maximum_limit,
        )
        if is_portfolio_blocked:
            return self._build_rejection(portfolio_reason or "Portfolio concentration exceeded", start_time, portfolio_flags)

        if is_first_order:
            if ml_result.band == "A":
                limit = min(limit, settings.cold_start_max_band_a)
            elif ml_result.band == "B":
                limit = min(limit, settings.cold_start_max_band_b)
            elif ml_result.band == "C":
                limit = min(limit, settings.cold_start_max_band_c)
            elif ml_result.band == "D":
                limit = min(limit, settings.cold_start_max_band_d)

        if limit > settings.maximum_limit:
            limit = settings.maximum_limit

        if order_amount > limit:
            return self._build_rejection(
                f"Order amount {order_amount} exceeds approved limit {limit}",
                start_time,
                ["limit_below_order_amount"],
            )

        all_flags = hard_block_flags + velocity_flags + identity_flags + overlay_flags + portfolio_flags
        return {
            "approved": True,
            "risk_band": ml_result.band,
            "approved_limit": float(limit),
            "down_payment_pct": float(down_payment),
            "rejection_reason": None,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": {
                "top_factors": [
                    f"Identity score {identity_score}",
                    f"Model score {round(ml_result.score, 2)}",
                    "No active hard-block flags",
                ],
                "flags": all_flags,
                "layer_scores": {
                    "identity_score": identity_score,
                    "alt_data_score": alt_data["wallet_activity_score"],
                    "ml_score": round(ml_result.score, 2),
                },
                "model_version": ml_result.model_version,
            },
        }

    async def create_credit_application(
        self,
        user_id: str,
        requested_limit: float,
        application_type: str,
        decision: dict[str, Any],
    ) -> CreditApplication:
        user_uuid = UUID(user_id)
        app = CreditApplication(
            user_id=user_uuid,
            application_type=application_type,
            requested_limit=requested_limit,
            credit_score=decision.get("explanation", {}).get("layer_scores", {}).get("ml_score"),
            status="approved" if decision["approved"] else "rejected",
            approved_limit=decision.get("approved_limit"),
            rejection_reason=decision.get("rejection_reason"),
            decided_by="system",
            user_data_snapshot={"source": "credit_apply"},
        )
        self.db.add(app)

        assessment = RiskAssessment(
            user_id=user_uuid,
            credit_app_id=app.uuid,
            assessment_type="credit_apply",
            total_score=decision.get("explanation", {}).get("layer_scores", {}).get("ml_score"),
            identity_score=decision.get("explanation", {}).get("layer_scores", {}).get("identity_score"),
            risk_band=decision.get("risk_band"),
            recommended_limit=decision.get("approved_limit"),
            down_payment_pct=decision.get("down_payment_pct"),
            flags=decision.get("explanation", {}).get("flags", []),
            explanation=decision.get("explanation"),
            model_version=decision.get("explanation", {}).get("model_version", "xgb-mock-v1"),
            processing_time_ms=decision.get("processing_time_ms"),
        )
        self.db.add(assessment)
        await self.db.commit()
        await self.db.refresh(app)
        return app

    async def get_credit_status(self, user_id: str) -> dict[str, Any]:
        user_uuid = UUID(user_id)
        limit_stmt = select(func.coalesce(func.max(CreditApplication.approved_limit), 0)).where(
            CreditApplication.user_id == user_uuid,
            CreditApplication.status == "approved",
        )
        current_limit = float((await self.db.execute(limit_stmt)).scalar_one())

        assessments_stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_uuid)
            .order_by(RiskAssessment.created_at.desc())
            .limit(10)
        )
        assessments = (await self.db.execute(assessments_stmt)).scalars().all()

        assessment_items = [
            {
                "assessed_at": item.created_at,
                "risk_band": item.risk_band,
                "approved_limit": float(item.recommended_limit) if item.recommended_limit is not None else None,
                "score": float(item.total_score) if item.total_score is not None else None,
            }
            for item in assessments
        ]

        utilized = 0.0
        available = max(current_limit - utilized, 0.0)
        return {
            "user_id": user_id,
            "current_limit": current_limit,
            "utilized_amount": utilized,
            "available_limit": available,
            "assessments": assessment_items,
        }

    async def admin_override_limit(
        self,
        user_id: str,
        new_limit: float,
        reason_code: str,
        admin_id: str,
    ) -> dict[str, Any]:
        user_uuid = UUID(user_id)
        current_stmt = select(func.coalesce(func.max(CreditApplication.approved_limit), 0)).where(
            CreditApplication.user_id == user_uuid,
            CreditApplication.status == "approved",
        )
        old_limit = float((await self.db.execute(current_stmt)).scalar_one())

        history = CreditLimitHistory(
            user_id=user_uuid,
            old_limit=old_limit,
            new_limit=new_limit,
            reason_code=reason_code,
            changed_by_type="admin",
            changed_by_id=admin_id,
        )
        self.db.add(history)

        override_application = CreditApplication(
            user_id=user_uuid,
            application_type="manual_override",
            requested_limit=new_limit,
            status="approved",
            approved_limit=new_limit,
            decided_by="admin",
            user_data_snapshot={"reason_code": reason_code},
        )
        self.db.add(override_application)
        await self.db.commit()

        return {
            "status": "success",
            "user_id": user_id,
            "new_limit": new_limit,
            "reason_code": reason_code,
        }

    async def blacklist_entity(
        self,
        entity_type: str,
        entity_value: str,
        reason_code: str,
        severity: str,
        blacklisted_by: str,
    ) -> dict[str, Any]:
        row = BlacklistedEntity(
            entity_type=entity_type,
            entity_value=entity_value,
            reason_code=reason_code,
            severity=severity,
            blacklisted_by=blacklisted_by,
            is_active=True,
        )
        self.db.add(row)
        await self.db.commit()

        if entity_type == "user":
            await self.redis.set(f"{RedisNS.CREDIT_BLACKLIST}:user:{entity_value}", "1", ttl=3600)

        return {
            "status": "success",
            "entity_type": entity_type,
            "entity_value": entity_value,
            "reason_code": reason_code,
            "severity": severity,
            "active": True,
        }

    async def get_risk_alerts(self, limit: int = 20) -> dict[str, Any]:
        stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.risk_band.in_(["E", "F"]))
            .order_by(RiskAssessment.created_at.desc())
            .limit(limit)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        alerts = [
            {
                "assessment_id": str(item.uuid),
                "user_id": str(item.user_id),
                "risk_band": item.risk_band,
                "score": float(item.total_score) if item.total_score is not None else None,
                "flags": item.flags or [],
                "created_at": item.created_at,
            }
            for item in rows
        ]
        return {"alerts": alerts}

    async def get_credit_explanation(self, assessment_id: str) -> dict[str, Any]:
        assessment_uuid = UUID(assessment_id)
        stmt = select(RiskAssessment).where(RiskAssessment.uuid == assessment_uuid)
        item = (await self.db.execute(stmt)).scalar_one_or_none()
        if not item:
            return {
                "assessment_id": assessment_id,
                "found": False,
                "explanation": None,
                "flags": [],
                "model_version": None,
            }

        return {
            "assessment_id": assessment_id,
            "found": True,
            "explanation": item.explanation,
            "flags": item.flags or [],
            "model_version": item.model_version,
        }

    def _build_rejection(self, reason: str, start_time: float, flags: list[str]) -> dict[str, Any]:
        return {
            "approved": False,
            "risk_band": "F",
            "approved_limit": 0.0,
            "down_payment_pct": 0.0,
            "rejection_reason": reason,
            "processing_time_ms": int((time.time() - start_time) * 1000),
            "explanation": {
                "top_factors": [reason],
                "flags": flags,
                "layer_scores": {"identity_score": 0.0, "alt_data_score": 0.0, "ml_score": 0.0},
                "model_version": "xgb-mock-v1",
            },
        }


# Backward-compatible alias used by existing imports/routes.
CreditPipeline = CreditPipelineService
