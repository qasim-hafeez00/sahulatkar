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


# Module 12 — the canonical 8-role set (RBACService.CANONICAL_ROLES). Kept as a
# literal duplicate rather than importing RBACService here to avoid a schemas
# -> services import cycle; the two must be kept in sync by hand.
_CanonicalRole = Literal[
    "super_admin", "operations_manager", "risk_officer", "compliance_officer",
    "finance_analyst", "cs_agent", "analyst", "marketing_manager",
]


class CreateAdminRequest(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    role: _CanonicalRole = "analyst"


class AssignRoleRequest(BaseModel):
    role: _CanonicalRole = "analyst"