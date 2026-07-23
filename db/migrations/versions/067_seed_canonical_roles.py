"""Seed the 8 canonical admin roles

Revision ID: 067
Revises: 066
Create Date: 2026-07-04 00:00:00.000000

Module 12 (Team & Access) — the `roles` table only had 2 rows (super_admin,
cs_agent, both created ad hoc by earlier test-account inserts). RBACService
was just consolidated from 13 roles down to 8 canonical ones; this seeds the
remaining 6 so admin_auth.py's create_admin/assign_admin_role (which resolve
role name -> roles.id) actually find a row for every assignable role.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.sql import table, column

revision: str = '067'
down_revision: Union[str, None] = '066'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

roles_table = table(
    "roles",
    column("name", sa.String),
    column("description", sa.String),
)

_NEW_ROLES = [
    {"name": "operations_manager", "description": "Day-to-day operations: users, orders, payments"},
    {"name": "risk_officer", "description": "Risk, fraud, and credit underwriting oversight"},
    {"name": "compliance_officer", "description": "Regulatory compliance, KYC review, audit trail"},
    {"name": "finance_analyst", "description": "Financial reporting, reconciliation, payments"},
    {"name": "analyst", "description": "Cross-functional reporting and analytics"},
    {"name": "marketing_manager", "description": "Marketing campaigns and partner analytics"},
]


def upgrade() -> None:
    conn = op.get_bind()
    for role in _NEW_ROLES:
        existing = conn.execute(
            sa.text("SELECT id FROM roles WHERE name = :name"), {"name": role["name"]}
        ).one_or_none()
        if existing is None:
            op.bulk_insert(roles_table, [role])


def downgrade() -> None:
    conn = op.get_bind()
    names = tuple(r["name"] for r in _NEW_ROLES)
    conn.execute(sa.text("DELETE FROM roles WHERE name = ANY(:names)"), {"names": list(names)})
