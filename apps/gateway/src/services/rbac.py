from typing import List


class RBACService:
    # Canonical permission matrix — aligned with all gateway endpoints.
    _ROLE_MAP: dict[str, list[str]] = {
        "super_admin": ["all_actions", "manage_admins"],
        "risk_officer": [
            "manage_risk", "read_blacklist", "read_risk", "read_user_financials",
            "read_reports", "read_user", "manage_system",
        ],
        "kyc_reviewer": [
            "manage_kyc_queue", "read_user", "read_compliance", "read_audit",
        ],
        "analyst": [
            "read_reports", "read_risk", "read_user_financials",
            "read_financials", "read_analytics",
        ],
        "support": [
            "read_user", "read_order", "read_support",
        ],
        "operations_manager": [
            "manage_users", "update_user", "manage_orders", "read_order",
            "manage_payments", "read_reports", "read_user",
            "read_partners", "read_support",
        ],
        "credit_risk_analyst": [
            "read_risk", "read_user_financials", "read_reports", "update_user",
        ],
        "fraud_analyst": [
            "manage_risk", "read_blacklist", "manage_system", "read_user",
        ],
        "cs_agent": [
            "read_user", "read_order", "read_support",
        ],
        "finance_analyst": [
            "read_financials", "read_reconciliation", "read_reports", "manage_payments",
        ],
        "compliance_officer": [
            "read_compliance", "manage_kyc_queue", "read_audit", "read_user",
        ],
        "marketing_manager": [
            "read_marketing", "read_analytics", "read_reports", "read_partners",
        ],
        "admin": [
            "read_user", "read_order", "read_reports",
        ],
    }

    @staticmethod
    def get_role_permissions(role: str) -> List[str]:
        return RBACService._ROLE_MAP.get(role, [])

    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        perms = RBACService.get_role_permissions(role)
        return "all_actions" in perms or permission in perms
