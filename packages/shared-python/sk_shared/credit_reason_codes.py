"""The complete, authoritative set of flag/reason codes credit-engine's decision pipeline can
emit, as a single str-enum. Before this, `apps/credit-engine/src/engines/*.py` each defined
its own ad-hoc string literals with no shared source of truth — any consumer (gateway, a
mobile client) string-matching a flag like "high_debt_to_income" was exposed to silent
typo/rename drift, since nothing would catch it if an engine's literal changed.

Because this is a `str, Enum`, every member IS its string value (`FlagCode.VELOCITY_CLEAR ==
"velocity_clear"` is True) — existing `"some_flag" in result.flags`-style checks, JSON
serialization, and DB storage of `flags: list[str]` columns all continue to work unchanged
whether the list holds raw strings or FlagCode members.

Lives in sk_shared (not credit-engine) so gateway or any other service can import it directly
for authoritative string matching instead of hardcoding its own copy of these strings.
"""
from __future__ import annotations

from enum import Enum


class FlagCode(str, Enum):
    # ── Eligibility (hard blocks) ──────────────────────────────────────────
    PROHIBITED_CATEGORY = "prohibited_category"
    BLACKLIST_CACHE_HIT = "blacklist_cache_hit"
    BLACKLIST_DB_HIT = "blacklist_db_hit"
    BLACKLIST_RISK_TABLE_HIT = "blacklist_risk_table_hit"
    INVALID_USER_ID = "invalid_user_id"
    USER_NOT_FOUND = "user_not_found"
    USER_BLOCKED = "user_blocked"
    KYC_NOT_APPROVED = "kyc_not_approved"
    KYC_MISSING = "kyc_missing"
    HARD_BLOCKS_CLEAR = "hard_blocks_clear"

    # ── Fraud / velocity ────────────────────────────────────────────────────
    VELOCITY_24H_BREACH = "velocity_24h_breach"
    VELOCITY_1H_BREACH = "velocity_1h_breach"
    VELOCITY_CLEAR = "velocity_clear"
    KNOWN_FRAUD_DEVICE = "known_fraud_device"
    DEVICE_RISK_SIGNAL = "device_risk_signal"
    TOR_EXIT_NODE = "tor_exit_node"
    PROXY_DETECTED = "proxy_detected"
    VPN_DETECTED = "vpn_detected"
    SYNTHETIC_IDENTITY_SIGNAL = "synthetic_identity_signal"
    FRAUD_SCORE_BLOCKED = "fraud_score_blocked"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"

    # ── Identity / trust ────────────────────────────────────────────────────
    DEVICE_TRUSTED = "device_trusted"
    DEVICE_TRUST_UNVERIFIED = "device_trust_unverified"
    IP_TRUSTED = "ip_trusted"
    IP_TRUST_UNVERIFIED = "ip_trust_unverified"
    IDENTITY_STRONG = "identity_strong"
    IDENTITY_WEAK = "identity_weak"

    # ── Affordability ───────────────────────────────────────────────────────
    BANK_DATA_UNAVAILABLE = "bank_data_unavailable"
    SALARY_VERIFIED = "salary_verified"
    HIGH_DEBT_TO_INCOME = "high_debt_to_income"
    INCOME_BELOW_MINIMUM = "income_below_minimum"

    # ── Limit / scoring / portfolio ─────────────────────────────────────────
    HIGH_RISK_CATEGORY = "high_risk_category"
    PORTFOLIO_LIMIT_EXCEEDED = "portfolio_limit_exceeded"
    HIGH_UTILIZATION = "high_utilization"
    SCORE_BELOW_THRESHOLD = "score_below_threshold"
    LIMIT_BELOW_ORDER_AMOUNT = "limit_below_order_amount"
    COLD_START_DATA_SPARSE = "cold_start_data_sparse"
    REPAYMENT_HISTORY_VERIFIED = "repayment_history_verified"
