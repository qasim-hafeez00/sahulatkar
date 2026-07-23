from typing import List


class RBACService:
    # Canonical 8-role permission matrix (Module 12 — Team & Access).
    #
    # Consolidated from an earlier 13-role matrix: credit_risk_analyst and
    # fraud_analyst folded into risk_officer (all three were risk-domain
    # roles with overlapping permission sets); kyc_reviewer folded into
    # compliance_officer (KYC review is a compliance function); support
    # folded into cs_agent (identical permission sets — same role, two
    # names). "admin" is kept as a defensive fallback for admin_users rows
    # with no role assigned, not one of the 8 selectable roles.
    _ROLE_MAP: dict[str, list[str]] = {
        "super_admin": ["all_actions", "manage_admins"],
        "operations_manager": [
            "manage_users", "update_user", "manage_orders", "read_order",
            "manage_payments", "read_reports", "read_user",
            "read_partners", "manage_partners", "read_support", "manage_support",
        ],
        "risk_officer": [
            "manage_risk", "read_blacklist", "read_risk", "read_user_financials",
            "read_reports", "read_user", "manage_system", "update_user",
        ],
        "compliance_officer": [
            "read_compliance", "manage_kyc_queue", "read_audit", "read_user",
        ],
        "finance_analyst": [
            "read_financials", "read_reconciliation", "read_reports", "manage_payments",
            "manage_financials",
        ],
        "cs_agent": [
            "read_user", "read_order", "read_support", "manage_support",
        ],
        "analyst": [
            "read_reports", "read_risk", "read_user_financials",
            "read_financials", "read_analytics",
        ],
        "marketing_manager": [
            "read_marketing", "read_analytics", "read_reports", "read_partners",
        ],
        "admin": [
            "read_user", "read_order", "read_reports",
        ],
    }

    # The 8 canonical, assignable roles (excludes "admin", the fallback).
    CANONICAL_ROLES: tuple[str, ...] = (
        "super_admin", "operations_manager", "risk_officer", "compliance_officer",
        "finance_analyst", "cs_agent", "analyst", "marketing_manager",
    )

    @staticmethod
    def get_role_permissions(role: str) -> List[str]:
        return RBACService._ROLE_MAP.get(role, [])

    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        perms = RBACService.get_role_permissions(role)
        return "all_actions" in perms or permission in perms
