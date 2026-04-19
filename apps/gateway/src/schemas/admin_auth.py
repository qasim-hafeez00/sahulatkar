from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class AdminLoginRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    totp_code: Optional[str] = Field(default=None, min_length=6, max_length=6)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin_id: int
    role: str


class CreateAdminRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    # TASK-19: Sync with full RBAC role map
    role: Literal[
        "super_admin", "risk_officer", "kyc_reviewer", "analyst", "support",
        "operations_manager", "credit_risk_analyst", "fraud_analyst", "cs_agent",
        "finance_analyst", "compliance_officer", "marketing_manager"
    ] = "analyst"


class AssignRoleRequest(BaseModel):
    # TASK-19: Sync with full RBAC role map
    role: Literal[
        "super_admin", "risk_officer", "kyc_reviewer", "analyst", "support",
        "operations_manager", "credit_risk_analyst", "fraud_analyst", "cs_agent",
        "finance_analyst", "compliance_officer", "marketing_manager"
    ] = "analyst"