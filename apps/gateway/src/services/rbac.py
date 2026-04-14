from typing import List

class RBACService:
    @staticmethod
    def get_role_permissions(role: str) -> List[str]:
        # Dummy matrix based on spec
        if role == "super_admin":
            return ["all_actions"]
        elif role == "operations_manager":
            return ["manage_users", "manage_orders", "manage_payments", "read_reports"]
        elif role == "credit_risk_analyst":
            return ["read_risk", "read_user_financials"]
        elif role == "fraud_analyst":
            return ["manage_risk", "read_blacklist"]
        elif role == "cs_agent":
            return ["read_user", "read_order"]
        elif role == "finance_analyst":
            return ["read_financials", "read_reconciliation"]
        elif role == "compliance_officer":
            return ["read_compliance", "manage_kyc_queue", "read_audit"]
        elif role == "marketing_manager":
            return ["read_marketing", "read_analytics"]
        return []

    @staticmethod
    def has_permission(role: str, permission: str) -> bool:
        perms = RBACService.get_role_permissions(role)
        return "all_actions" in perms or permission in perms
