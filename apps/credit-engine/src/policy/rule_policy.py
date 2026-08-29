from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.constants import RedisNS, RedisTTL
from sk_shared.models.credit import CreditPolicyVersion
from sk_shared.redis_client import RedisClient

logger = logging.getLogger(__name__)


class ScoreBin(BaseModel):
    """One WOE-style band of a points scorecard: any raw signal in [min_score, max_score)
    contributes exactly `points` to the total, no interpolation. Real scorecards derive these
    cut points and point values from the weight-of-evidence of each band against observed
    default outcomes; until repayment outcome data exists (see the plan's model-weights
    research), these are hand-set monotonic defaults, not fitted ones."""

    min_score: float
    max_score: float
    points: float


class RulePolicy(BaseModel):
    """Every tunable the decision engines read, as one versioned object.

    Previously these were hardcoded dicts duplicated across layer1_hard_blocks.py and
    layer6_order_overlay.py (PROHIBITED_CATEGORIES existed in both, independently editable
    and prone to drift). Now there is exactly one source: the active row in
    `credit_policy_versions`, loaded and Redis-cached by RulePolicyLoader. These field
    defaults are the bootstrap policy used until an admin activates a real versioned row —
    they intentionally match the previous hardcoded behavior exactly, so introducing
    RulePolicy is a refactor, not a behavior change.
    """

    version_label: str = "bootstrap-default"

    prohibited_categories: set[str] = Field(default_factory=lambda: {
        "alcohol",
        "tobacco",
        "gambling",
        "adult content",
        "weapons",
        "interest-bearing instruments",
        "non-halal food",
    })

    category_multipliers: dict[str, float] = Field(default_factory=lambda: {
        "smartphones": 0.60,
        "gold jewelry": 0.40,
        "laptops": 0.65,
        "cameras": 0.70,
        "clothing": 1.0,
        "footwear": 1.0,
        "home appliances": 1.0,
        "general": 1.0,
    })
    default_category_multiplier: float = 1.0
    high_risk_multiplier_threshold: float = 0.7
    high_risk_down_payment_bump_pct: float = 5.0
    max_down_payment_pct: float = 60.0

    # Phase 4 decision outcomes: when the financed portion of an order exceeds the approved
    # limit, offer an alternative instead of a flat reject. If raising the down payment (up to
    # max_suggested_down_payment_pct — deliberately stricter than max_down_payment_pct, which
    # bounds the category overlay: asking a customer for a much larger upfront payment just to
    # unlock the loan defeats the point of BNPL) would bring the financed amount within the
    # limit, offer increase_down_payment. Otherwise, if the limit still covers at least this
    # fraction of the order, offer partial_approval at the reduced amount.
    max_suggested_down_payment_pct: float = 45.0
    partial_approval_min_coverage_ratio: float = 0.5

    velocity_24h_window_seconds: int = 24 * 3600
    velocity_24h_threshold: int = 3
    velocity_1h_window_seconds: int = 3600
    velocity_1h_threshold: int = 1

    score_band_cutoffs: dict[str, float] = Field(default_factory=lambda: {
        "A": 800.0, "B": 700.0, "C": 600.0, "D": 500.0,
    })
    band_base_limits: dict[str, float] = Field(default_factory=lambda: {
        "A": 25000.0, "B": 15000.0, "C": 8000.0, "D": 5000.0,
    })
    band_down_payment_pct: dict[str, float] = Field(default_factory=lambda: {
        "A": 25.0, "B": 25.0, "C": 30.0, "D": 35.0,
    })
    cold_start_caps: dict[str, float] = Field(default_factory=lambda: {
        "A": 8000.0, "B": 5000.0, "C": 3000.0, "D": 2000.0,
    })

    # Cold-start graduation via real repayment history (Phase 6 bugfix): data_sparse's
    # device-trust/IP-trust/bank-data exit condition depends on a JazzCash/Easypaisa wallet
    # integration and a device-fingerprinting/IP-intelligence vendor that don't exist in
    # production (see wallet.py / identity.py / fraud.py) — so that exit can structurally never
    # fire for a real applicant, and every repeat customer gets capped forever. A customer with
    # a genuine track record of fully-repaid, on-time BNPL loans is real signal the platform
    # already has (LimitEngine.has_repayment_track_record queries it directly) and can graduate
    # on independently of the missing device/wallet signals.
    #
    # 3 is deliberately more than a single completed loan (could be a fluke, or a merchant
    # testing their own account with a small purchase) or even two, while still being reachable
    # within a normal customer relationship given SahulatKar's short (weeks-to-months)
    # installment plans. Configurable like every other threshold here so risk/admin can tighten
    # or loosen it without a code deploy — but the "zero tolerance" half of the rule (ANY
    # missed/late installment anywhere in the user's history disqualifies them, regardless of
    # this count) is NOT configurable here; it's intentionally hardcoded in
    # has_repayment_track_record so a policy misconfiguration can never relax it.
    graduation_min_repaid_loans: int = 3

    # WOE-style points scorecard (Phase 3): each 0-100 input signal is binned, and the bin's
    # points are summed — not multiplied through a continuous weight — so the contribution of
    # a signal can be tuned per-band (e.g. "reward strong identity trust disproportionately")
    # instead of forcing one linear slope across the whole range. This is still hand-set, not
    # fitted on outcomes; see ScoringEngine's docstring for the swap point to a trained model.
    identity_score_bins: list[ScoreBin] = Field(default_factory=lambda: [
        ScoreBin(min_score=0, max_score=40, points=0),
        ScoreBin(min_score=40, max_score=60, points=200),
        ScoreBin(min_score=60, max_score=75, points=450),
        ScoreBin(min_score=75, max_score=90, points=650),
        ScoreBin(min_score=90, max_score=100.01, points=750),
    ])
    alt_data_score_bins: list[ScoreBin] = Field(default_factory=lambda: [
        ScoreBin(min_score=0, max_score=40, points=0),
        ScoreBin(min_score=40, max_score=60, points=40),
        ScoreBin(min_score=60, max_score=75, points=90),
        ScoreBin(min_score=75, max_score=90, points=120),
        ScoreBin(min_score=90, max_score=100.01, points=150),
    ])
    max_raw_score: float = 900.0

    # Fraud risk scoring (Phase 2): device fingerprint / IP reputation / synthetic-identity
    # signals are summed into one composite score. Below fraud_review_threshold the
    # application proceeds untouched; between the two thresholds it's approved-pending but
    # flagged for manual_review_queue; at/above fraud_block_threshold it's a hard reject.
    device_known_fraud_points: float = 60.0
    device_risk_flag_points: dict[str, float] = Field(default_factory=lambda: {
        "rooted": 25.0,
        "jailbroken": 25.0,
        "emulator": 35.0,
        "vpn": 10.0,
        "gps_spoofed": 20.0,
    })
    ip_tor_points: float = 50.0
    ip_proxy_points: float = 20.0
    ip_vpn_points: float = 10.0
    ip_threat_score_weight: float = 40.0  # IpIntelligence.threat_score is 0-1, scaled to points
    synthetic_identity_weight: float = 100.0  # SyntheticIdentityIndicator.confidence_score is 0-1, scaled to points
    fraud_review_threshold: float = 40.0
    fraud_block_threshold: float = 80.0


class RulePolicyLoader:
    """Loads the active RulePolicy, Redis-cached so the hot decision path doesn't hit
    Postgres on every request.

    Cache TTL (RedisTTL.CREDIT_POLICY) bounds how stale a policy can be after an admin
    activates a new version — acceptable for rule weights, unlike e.g. a blacklist hit which
    is invalidated eagerly elsewhere.
    """

    def __init__(self, db: AsyncSession, redis_client: RedisClient) -> None:
        self.db = db
        self.redis = redis_client
        self._cache_key = f"{RedisNS.CREDIT_POLICY}:active"

    async def load(self) -> RulePolicy:
        cached = await self.redis.get_json(self._cache_key)
        if cached is not None:
            try:
                return RulePolicy.model_validate(cached)
            except Exception:
                logger.exception("rule_policy_cache_corrupt, falling back to db")

        policy = await self._load_from_db()
        await self.redis.set_json(self._cache_key, policy.model_dump(mode="json"), ttl=RedisTTL.CREDIT_POLICY)
        return policy

    async def _load_from_db(self) -> RulePolicy:
        stmt = (
            select(CreditPolicyVersion)
            .where(CreditPolicyVersion.status == "active")
            .order_by(CreditPolicyVersion.activated_at.desc())
            .limit(1)
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return RulePolicy()

        try:
            merged: dict[str, Any] = {**row.config, "version_label": row.version_label}
            return RulePolicy.model_validate(merged)
        except Exception:
            logger.exception(
                "rule_policy_config_invalid, version_label=%s, falling back to bootstrap default",
                row.version_label,
            )
            return RulePolicy()
