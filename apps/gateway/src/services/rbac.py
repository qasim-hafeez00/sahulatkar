from typing import List


class RBACService:
    # Canonical permission matrix — aligned with all gateway endpoints.
    _ROLE_MAP: dict[str, list[str]] = {
        "super_admin": ["all_actions"],
        "risk_officer": [
            "manage_risk", "read_blacklist", "read_risk", "read_user_financials",
            "read_reports", "read_user",
        ],
        "kyc_reviewer": [
            "manage_kyc_queue", "read_user", "read_compliance", "read_audit",
        ],
        "analyst": [
            "read_reports", "read_risk", "read_user_financials",
            "read_financials", "read_analytics",
        ],
        "support": [
            "read_user", "read_order",
        ],
        # Legacy role names kept for backward compatibility
        "operations_manager": [
            "manage_users", "update_user", "manage_orders", "manage_payments", "read_reports", "read_user",
        ],
        "credit_risk_analyst": ["read_risk", "read_user_financials", "read_reports"],
        "fraud_analyst": ["manage_risk", "read_blacklist", "manage_system"],
        "cs_agent": ["read_user", "read_order"],
        "finance_analyst": ["read_financials", "read_reconciliation", "read_reports"],
        "compliance_officer": ["read_compliance", "manage_kyc_queue", "read_audit"],
        "marketing_manager": ["read_marketing", "read_analytics"],
        "admin": ["read_user", "read_order", "read_reports"],
    }

    @staticmethod
    def get_role_permissions(role: str) -> List[str]:
        return RBACService._ROLE_MAP.get(role, [])

    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        perms = RBACService.get_role_permissions(role)
        return "all_actions" in perms or permission in perms

