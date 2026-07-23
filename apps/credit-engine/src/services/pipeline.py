import logging
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.core import http_client
from src.engines import (
    AffordabilityEngine,
    DecisionEngine,
    EligibilityEngine,
    FraudEngine,
    IdentityEngine,
    LimitEngine,
    ScoringEngine,
)
from src.core.metrics import credit_decisions_total, credit_fraud_score, credit_manual_review_total
from src.engines.affordability import AffordabilityResult
from src.engines.identity import IdentityResult
from src.engines.limit import LimitResult
from src.engines.scoring import ScoreResult
from src.events.publisher import CreditEventPublisher
from src.policy.rule_policy import RulePolicy, RulePolicyLoader
from sk_shared.constants import RedisNS
from sk_shared.credit_reason_codes import FlagCode
from sk_shared.models.admin import RiskBlacklist
from sk_shared.models.auth import User
from sk_shared.models.credit import (
    BlacklistedEntity,
    CreditApplication,
    CreditFeatureSnapshot,
    CreditLimitHistory,
    RiskAssessment,
)
from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)


@dataclass
class _CoreAssessment:
    identity: IdentityResult
    affordability: AffordabilityResult
    scoring: ScoreResult
    overlay: LimitResult


class CreditPipelineService:
    """Orchestrates the engine pipeline: EligibilityEngine -> FraudEngine -> IdentityEngine +
    AffordabilityEngine -> ScoringEngine -> LimitEngine -> DecisionEngine. Each engine is a
    small, independently testable unit reading from one shared, versioned RulePolicy instead
    of the hardcoded/duplicated constants the old src/layers/* modules had."""

    def __init__(self, db_session: AsyncSession, redis_client: RedisClient):
        self.db = db_session
        self.redis = redis_client
        self.events = CreditEventPublisher(redis_client)
        self.policy_loader = RulePolicyLoader(db_session, redis_client)
        self.identity_engine = IdentityEngine()
        self.affordability_engine = AffordabilityEngine()
        self.decision_engine = DecisionEngine()

    async def _score_applicant(
        self,
        user_id: str,
        product_category: str,
        scoring_engine: ScoringEngine,
        limit_engine: LimitEngine,
        device_fingerprint_hash: str | None = None,
        ip_address: str | None = None,
    ) -> _CoreAssessment:
        """Identity + affordability + scoring + category overlay — the assessment core shared
        by evaluate_credit (which additionally runs fraud/velocity and portfolio checks
        neither prequalify nor recalculate_limit want) and prequalify (a soft check with no
        fraud/portfolio gate). Pulling this out closes a real drift risk: prequalify used to
        independently reimplement these four calls, so a future change to how they're wired
        together in evaluate_credit could silently stop being mirrored here."""
        identity = await self.identity_engine.evaluate(self.db, user_id, device_fingerprint_hash, ip_address)
        affordability = await self.affordability_engine.evaluate(self.db, user_id)
        scoring = scoring_engine.score(identity.score, affordability.wallet_activity_score)
        overlay = limit_engine.apply_category_overlay(scoring.base_limit, scoring.down_payment_pct, product_category)
        return _CoreAssessment(identity=identity, affordability=affordability, scoring=scoring, overlay=overlay)

    async def _get_user_int_id(self, user_uuid: str) -> Optional[int]:
        """Gateway's `users` table (and the credit-result callback, and
        CreditLimitHistory.user_id) is keyed by the integer `users.id`, while credit-engine's
        own CreditApplication/RiskAssessment rows are keyed by `users.uuid` — this resolves
        between the two. Returns None if the uuid doesn't parse or match a row, so callers can
        degrade to "skip the gateway sync" rather than crash a decision that otherwise succeeded.
        """
        try:
            uuid_obj = UUID(user_uuid)
        except ValueError:
            return None
        user = (await self.db.execute(select(User).where(User.uuid == uuid_obj))).scalar_one_or_none()
        return user.id if user else None

    async def evaluate_credit(
        self,
        user_id: str,
        order_amount: float,
        product_category: str = "general",
        is_first_order: bool = False,
        device_fingerprint_hash: str | None = None,
        ip_address: str | None = None,
    ) -> dict[str, Any]:
        start_time = time.time()
        await self._safe_publish(self.events.publish_evaluation_requested(
            user_id=user_id, order_amount=order_amount, product_category=product_category,
        ))

        policy = await self.policy_loader.load()
        eligibility_engine = EligibilityEngine(policy)
        fraud_engine = FraudEngine(policy)
        scoring_engine = ScoringEngine(policy)
        limit_engine = LimitEngine(policy, settings.maximum_limit)

        # Captured incrementally as the pipeline progresses and attached to whatever decision
        # is ultimately returned (approval or rejection) — this is the raw input feature
        # vector CreditFeatureSnapshot persists per decision (see create_credit_application),
        # so a dispute months from now can be reconstructed from what the engines actually saw
        # rather than re-derived against today's (possibly different) policy/data.
        features: dict[str, Any] = {
            "policy_version": policy.version_label,
            "order_amount": order_amount,
            "product_category": product_category,
            "is_first_order": is_first_order,
            "device_fingerprint_provided": device_fingerprint_hash is not None,
            "ip_address_provided": ip_address is not None,
        }

        eligibility = await eligibility_engine.evaluate(self.db, self.redis, user_id, product_category)
        features["eligibility"] = {"passed": eligibility.passed, "flags": eligibility.flags}
        if not eligibility.passed:
            return await self._reject(
                user_id, eligibility.reason or "Hard block triggered", start_time, eligibility.flags, policy, features,
            )

        fraud = await fraud_engine.evaluate(self.db, self.redis, user_id, device_fingerprint_hash, ip_address)
        credit_fraud_score.observe(fraud.fraud_score)
        if fraud.manual_review:
            credit_manual_review_total.inc()
        features["fraud"] = {
            "score": fraud.fraud_score, "manual_review": fraud.manual_review,
            "alert_type": fraud.alert_type, "severity": fraud.severity, "flags": fraud.flags,
        }
        if fraud.manual_review or fraud.blocked:
            await self._safe_publish(self.events.publish_fraud_detected(
                user_id=user_id,
                alert_type=fraud.alert_type or "velocity_breach",
                severity=fraud.severity or "medium",
                flags=fraud.flags,
            ))
        if fraud.blocked:
            return await self._reject(
                user_id, fraud.reason or "Velocity block triggered", start_time, fraud.flags, policy, features,
            )
        if fraud.manual_review:
            await self._safe_publish(self.events.publish_manual_review_required(
                user_id=user_id, assessment_id=None, reason=fraud.reason or "Elevated fraud risk score",
            ))

        core = await self._score_applicant(
            user_id, product_category, scoring_engine, limit_engine, device_fingerprint_hash, ip_address,
        )
        identity, affordability, scoring, overlay = core.identity, core.affordability, core.scoring, core.overlay
        features["identity"] = {"score": identity.score, "flags": identity.flags}
        features["affordability"] = {
            "wallet_activity_score": affordability.wallet_activity_score,
            "income_signal": affordability.income_signal,
            "provider": affordability.provider,
            "income_estimate": affordability.income_estimate,
            "debt_to_income_ratio": affordability.debt_to_income_ratio,
            "flags": affordability.flags,
        }
        features["scoring"] = {
            "score": scoring.score, "band": scoring.band,
            "identity_contribution": scoring.identity_contribution,
            "alt_data_contribution": scoring.alt_data_contribution,
            "model_version": scoring.model_version,
        }
        if scoring.score < settings.auto_decline_below:
            return await self._reject(
                user_id, "Credit score below acceptable threshold", start_time, [FlagCode.SCORE_BELOW_THRESHOLD], policy, features,
            )

        if overlay.blocked:
            return await self._reject(
                user_id, overlay.reason or "Prohibited category", start_time, overlay.flags, policy, features,
            )

        portfolio = await limit_engine.check_portfolio_concentration(self.db, user_id, order_amount)
        if portfolio.blocked:
            return await self._reject(
                user_id, portfolio.reason or "Portfolio concentration exceeded", start_time, portfolio.flags, policy, features,
            )

        # A score built with no corroborating device/IP/bank-statement evidence at all is
        # less reliable than one backed by real signal — cap exposure the same way a genuine
        # first order does, regardless of the caller-supplied is_first_order flag. Driven off
        # IdentityEngine's verification flags rather than the raw hash/IP params: an IP
        # address is essentially always present at the HTTP layer (there's always a TCP peer),
        # so "was a value passed" is a useless sparse-signal — "did it actually resolve to a
        # known-clean row" is what identity.flags already captures.
        data_sparse = (
            "device_trust_unverified" in identity.flags
            and "ip_trust_unverified" in identity.flags
            and "bank_data_unavailable" in affordability.flags
        )
        limit = limit_engine.apply_cold_start_cap(overlay.limit, scoring.band, is_first_order, data_sparse=data_sparse)
        limit = limit_engine.clamp_to_maximum(limit)
        features["limit"] = {
            "base_limit": scoring.base_limit, "overlay_limit": overlay.limit,
            "data_sparse": data_sparse, "final_limit": limit, "down_payment_pct": overlay.down_payment_pct,
        }

        all_flags = (
            eligibility.flags + fraud.flags + identity.flags + affordability.flags + overlay.flags + portfolio.flags
        )
        if data_sparse:
            all_flags = all_flags + [FlagCode.COLD_START_DATA_SPARSE]

        # Credit is only drawn against the financed portion of the order — the down payment
        # is paid upfront by the customer, not extended as credit — so the limit check
        # compares against that, not the full order amount.
        financed_amount = order_amount * (1 - overlay.down_payment_pct / 100.0)

        if financed_amount <= limit:
            result = self.decision_engine.build_approval(
                identity=identity,
                affordability=affordability,
                scoring=scoring,
                limit=limit,
                down_payment_pct=overlay.down_payment_pct,
                flags=all_flags,
                start_time=start_time,
            )
            await self._safe_publish(self.events.publish_approved(
                user_id=user_id,
                assessment_id=None,
                risk_band=scoring.band,
                approved_limit=float(limit),
                down_payment_pct=float(overlay.down_payment_pct),
            ))
            return self._finalize(result, policy, features)

        required_down_payment_pct = 100.0 * (1 - limit / order_amount) if order_amount > 0 else 100.0
        if limit > 0 and required_down_payment_pct <= policy.max_suggested_down_payment_pct:
            result = self.decision_engine.build_increase_down_payment(
                scoring=scoring,
                limit=limit,
                requested_amount=order_amount,
                suggested_down_payment_pct=required_down_payment_pct,
                flags=all_flags,
                start_time=start_time,
            )
            return self._finalize(result, policy, features)

        if limit >= order_amount * policy.partial_approval_min_coverage_ratio:
            result = self.decision_engine.build_partial_approval(
                identity=identity,
                affordability=affordability,
                scoring=scoring,
                limit=limit,
                down_payment_pct=overlay.down_payment_pct,
                requested_amount=order_amount,
                flags=all_flags,
                start_time=start_time,
            )
            await self._safe_publish(self.events.publish_approved(
                user_id=user_id,
                assessment_id=None,
                risk_band=scoring.band,
                approved_limit=float(limit),
                down_payment_pct=float(overlay.down_payment_pct),
            ))
            return self._finalize(result, policy, features)

        return await self._reject(
            user_id,
            f"Order amount {order_amount} exceeds approved limit {limit}",
            start_time,
            all_flags + [FlagCode.LIMIT_BELOW_ORDER_AMOUNT],
            policy,
            features,
        )

    @staticmethod
    def _finalize(result: dict[str, Any], policy: RulePolicy, features: dict[str, Any]) -> dict[str, Any]:
        """Stamps the policy version that actually produced this decision onto its explanation
        (so a future config change can never retroactively change what a historical decision
        is shown to have been based on) and carries the raw feature vector through to
        create_credit_application, which persists it as a CreditFeatureSnapshot. `_feature_snapshot`
        is intentionally not part of any response schema — routes pop it before returning."""
        if isinstance(result.get("explanation"), dict):
            result["explanation"]["policy_version"] = policy.version_label
        result["_feature_snapshot"] = features
        credit_decisions_total.labels(outcome=result.get("outcome", "unknown"), risk_band=result.get("risk_band") or "none").inc()
        return result

    async def _reject(
        self,
        user_id: str,
        reason: str,
        start_time: float,
        flags: list[str],
        policy: RulePolicy | None = None,
        features: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.decision_engine.build_rejection(reason, flags, start_time)
        await self._safe_publish(self.events.publish_rejected(
            user_id=user_id, assessment_id=None, reason=reason, flags=flags,
        ))
        if policy is not None:
            return self._finalize(result, policy, features or {})
        return result

    async def _safe_publish(self, coro) -> None:
        """Event delivery is best-effort — a Redis hiccup must never fail a credit decision
        that has already been correctly computed."""
        try:
            await coro
        except Exception:
            logger.exception("credit_event_publish_failed")

    async def create_credit_application(
        self,
        user_id: str,
        requested_limit: float,
        application_type: str,
        decision: dict[str, Any],
    ) -> CreditApplication:
        # Popped (not just read) so it never leaks into a caller that forwards `decision`
        # straight into an API response — see routes.py's /credit/apply, which builds its
        # response from selected fields rather than the raw dict, but other callers may not.
        feature_snapshot = decision.pop("_feature_snapshot", None)

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
            model_version=decision.get("explanation", {}).get("model_version", "scorecard-v1"),
            processing_time_ms=decision.get("processing_time_ms"),
        )
        self.db.add(assessment)

        if feature_snapshot is not None:
            # Flush so assessment.uuid (a Python-side default, only guaranteed populated once
            # flushed) is available to link the snapshot to its assessment.
            await self.db.flush()
            self.db.add(CreditFeatureSnapshot(
                user_id=user_uuid,
                assessment_id=assessment.uuid,
                features=feature_snapshot,
                score_breakdown=decision.get("explanation"),
                policy_version=feature_snapshot.get("policy_version"),
                model_version=decision.get("explanation", {}).get("model_version"),
            ))

        await self.db.commit()
        await self.db.refresh(app)
        await self.db.refresh(assessment)

        if decision["approved"]:
            # Sync the decision into Gateway's `users` table (GAP-01's credit-result callback,
            # previously never called from here — see src/core/http_client.py). Runs on any
            # `approved=True` outcome, which includes partial_approval (a real approval, just
            # below what was requested) but not increase_down_payment (a counter-offer, not an
            # approval) or a hard reject — so a decline never zeroes out an existing good limit
            # gateway already has for this user.
            approved_limit = float(app.approved_limit or 0.0)
            gateway_user_id = await self._get_user_int_id(user_id)
            if gateway_user_id is not None:
                await http_client.push_credit_result(
                    user_id=gateway_user_id,
                    risk_band=decision.get("risk_band") or "F",
                    credit_limit=approved_limit,
                    available_credit=approved_limit,
                    recommended_limit=approved_limit,
                    decision="approved",
                    assessment_id=assessment.id,
                )
            else:
                logger.error("credit_result_push_skipped: no users row for uuid=%s", user_id)

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

    async def get_credit_history(self, user_id: str, limit: int = 20) -> dict[str, Any]:
        """Every CreditApplication decision for this user, not just the last 10
        RiskAssessment rows get_credit_status shows — includes rejections and their reasons,
        which get_credit_status's approved-limit-only view omits entirely."""
        user_uuid = UUID(user_id)
        stmt = (
            select(CreditApplication)
            .where(CreditApplication.user_id == user_uuid)
            .order_by(CreditApplication.created_at.desc())
            .limit(limit)
        )
        applications = (await self.db.execute(stmt)).scalars().all()
        return {
            "user_id": user_id,
            "applications": [
                {
                    "application_id": str(app.uuid),
                    "application_type": app.application_type,
                    "status": app.status,
                    "requested_limit": float(app.requested_limit) if app.requested_limit is not None else None,
                    "approved_limit": float(app.approved_limit) if app.approved_limit is not None else None,
                    "rejection_reason": app.rejection_reason,
                    "decided_by": app.decided_by,
                    "created_at": app.created_at,
                }
                for app in applications
            ],
        }

    async def get_live_score(self, user_id: str) -> dict[str, Any]:
        """Current identity + affordability score/band with no eligibility gate, no fraud
        check, no application record — a "check your score" read, not a lending decision."""
        policy = await self.policy_loader.load()
        scoring_engine = ScoringEngine(policy)

        identity = await self.identity_engine.evaluate(self.db, user_id)
        affordability = await self.affordability_engine.evaluate(self.db, user_id)
        scoring = scoring_engine.score(identity.score, affordability.wallet_activity_score)

        return {
            "user_id": user_id,
            "risk_band": scoring.band,
            "score": scoring.score,
            "identity_score": identity.score,
            "alt_data_score": affordability.wallet_activity_score,
            "model_version": scoring.model_version,
        }

    async def prequalify(self, user_id: str, product_category: str = "general") -> dict[str, Any]:
        """Soft check: eligibility + score + category overlay, with no fraud/velocity check,
        no portfolio check, no application record, and no fraud_alerts/manual_review_queue
        writes. Gives a merchant checkout flow an indicative limit before the customer commits
        to a real application, without it counting as a hard pull."""
        start_time = time.time()
        policy = await self.policy_loader.load()
        eligibility_engine = EligibilityEngine(policy)
        scoring_engine = ScoringEngine(policy)
        limit_engine = LimitEngine(policy, settings.maximum_limit)

        eligibility = await eligibility_engine.evaluate(self.db, self.redis, user_id, product_category)
        if not eligibility.passed:
            return {
                "eligible": False,
                "reason": eligibility.reason,
                "indicative_limit": 0.0,
                "down_payment_pct": None,
                "risk_band": None,
                "processing_time_ms": int((time.time() - start_time) * 1000),
            }

        core = await self._score_applicant(user_id, product_category, scoring_engine, limit_engine)
        scoring, overlay = core.scoring, core.overlay

        eligible = not overlay.blocked and scoring.score >= settings.auto_decline_below
        indicative_limit = 0.0 if overlay.blocked else limit_engine.clamp_to_maximum(overlay.limit)
        return {
            "eligible": eligible,
            "reason": overlay.reason if overlay.blocked else (None if eligible else "Credit score below acceptable threshold"),
            "indicative_limit": float(indicative_limit),
            "down_payment_pct": float(overlay.down_payment_pct) if not overlay.blocked else None,
            "risk_band": scoring.band,
            "processing_time_ms": int((time.time() - start_time) * 1000),
        }

    async def recalculate_limit(self, user_id: str) -> dict[str, Any]:
        """Re-runs identity + affordability + scoring against the user's current data and
        reports how that compares to their standing limit. Read-only by design — it proposes,
        it doesn't apply; raising a live limit is still an explicit admin_override_limit call
        (or, once wired, an auto-apply job gated on settings.credit_increase_after_n_payments,
        which this method does not yet consult)."""
        policy = await self.policy_loader.load()
        scoring_engine = ScoringEngine(policy)
        limit_engine = LimitEngine(policy, settings.maximum_limit)

        identity = await self.identity_engine.evaluate(self.db, user_id)
        affordability = await self.affordability_engine.evaluate(self.db, user_id)
        scoring = scoring_engine.score(identity.score, affordability.wallet_activity_score)
        recalculated_limit = limit_engine.clamp_to_maximum(scoring.base_limit)

        current = await self.get_credit_status(user_id)
        current_limit = current["current_limit"]

        return {
            "user_id": user_id,
            "current_limit": current_limit,
            "recalculated_limit": float(recalculated_limit),
            "risk_band": scoring.band,
            "limit_increased": recalculated_limit > current_limit,
            "delta": float(recalculated_limit - current_limit),
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

        # CreditLimitHistory.user_id is the integer `users.id` PK (see migration
        # 041_production_hardening), not the `users.uuid` every other credit-engine table uses
        # keys off — passing user_uuid straight in violated the column's own type and made
        # every admin override write fail (previously undetected: the test for this path was
        # xfail'd rather than fixed).
        user_row = (await self.db.execute(select(User).where(User.uuid == user_uuid))).scalar_one_or_none()
        if user_row is None:
            return {
                "status": "error",
                "user_id": user_id,
                "new_limit": new_limit,
                "reason_code": reason_code,
                "error": "USER_NOT_FOUND",
            }
        gateway_user_id = user_row.id
        current_risk_band = user_row.risk_band or "pending_assessment"

        history = CreditLimitHistory(
            user_id=gateway_user_id,
            old_limit=old_limit,
            new_limit=new_limit,
            reason_code=reason_code,
            changed_by_type="admin",
            changed_by_id=admin_id,
            previous_limit=old_limit,
            available_before=old_limit,
            available_after=new_limit,
            reason=f"admin_override:{reason_code}",
            changed_by=admin_id,
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

        await http_client.push_credit_result(
            user_id=gateway_user_id,
            risk_band=current_risk_band,
            credit_limit=new_limit,
            available_credit=new_limit,
            recommended_limit=new_limit,
            decision="approved",
        )
        await self._safe_publish(self.events.publish_limit_changed(
            user_id=user_id, old_limit=old_limit, new_limit=new_limit,
            reason_code=reason_code, changed_by_type="admin",
        ))

        return {
            "status": "success",
            "user_id": user_id,
            "new_limit": new_limit,
            "reason_code": reason_code,
            # Not part of CreditOverrideResponse (FastAPI's response_model drops unknown
            # fields) — carried through so the route handler can attach it to the audit
            # trail's target_id without re-deriving the uuid->int lookup itself.
            "customer_user_id": gateway_user_id,
            "old_limit": old_limit,
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

        # Dual-write onto RiskBlacklist too — that's the table gateway's admin UI
        # (/admin/risk/blacklist) actually reads and writes, and the two tables never synced.
        existing_risk_row = (
            await self.db.execute(
                select(RiskBlacklist).where(
                    RiskBlacklist.entry_type == entity_type,
                    RiskBlacklist.value == entity_value,
                    RiskBlacklist.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing_risk_row is None:
            gateway_user_id = await self._get_user_int_id(entity_value) if entity_type == "user" else None
            self.db.add(RiskBlacklist(
                entry_type=entity_type,
                value=entity_value,
                reason=f"{reason_code} ({severity})",
                user_id=gateway_user_id,
            ))

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
            "id": row.id,
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
            "id": item.id,
        }


# Backward-compatible alias used by existing imports/routes.
CreditPipeline = CreditPipelineService
