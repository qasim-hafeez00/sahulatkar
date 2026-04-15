from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser

from src.core.dependencies import get_current_admin, get_db, RequirePermission

router = APIRouter(prefix="/admin/users", tags=["Admin Users"])


@router.get("")
async def list_admin_users(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=25, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    sort_by: str | None = Query(default="created_at"),
    sort_dir: str | None = Query(default="desc"),
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    offset = (page - 1) * limit
    where_clauses = ["deleted_at IS NULL"]
    params: dict[str, object] = {"limit": limit, "offset": offset}

    if search:
        where_clauses.append("phone ILIKE :search")
        params["search"] = f"%{search}%"
    if status:
        where_clauses.append("status = :status")
        params["status"] = status

    sort_column_map = {
        "id": "id",
        "phone": "phone",
        "status": "status",
        "created_at": "created_at",
        "failed_login_attempts": "failed_login_attempts",
        "locked_until": "locked_until",
    }
    sort_column = sort_column_map.get(sort_by or "created_at", "created_at")
    sort_order = "ASC" if (sort_dir or "desc").lower() == "asc" else "DESC"

    query = text(
        """
        SELECT id, phone, status, created_at, failed_login_attempts, locked_until
        FROM users
        WHERE {where_clause}
        ORDER BY {sort_column} {sort_order}
        LIMIT :limit OFFSET :offset
        """.format(where_clause=" AND ".join(where_clauses), sort_column=sort_column, sort_order=sort_order)
    )

    count_query = text(
        "SELECT COUNT(*) FROM users WHERE {where_clause}".format(where_clause=" AND ".join(where_clauses))
    )

    try:
        rows = (await db.execute(query, params)).mappings().all()
        total = int((await db.execute(count_query, params)).scalar_one())
    except Exception:
        rows = []
        total = 0

    return {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "items": [
            {
                "id": row["id"],
                "phone": row["phone"],
                "status": row["status"],
                "created_at": row["created_at"],
                "failed_login_attempts": row["failed_login_attempts"],
                "locked_until": row["locked_until"],
            }
            for row in rows
        ],
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
        },
    }


@router.get("/{user_id}")
async def get_admin_user_detail(
    user_id: int,
    current_admin: AdminUser = Depends(RequirePermission("read_user")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    query = text(
        """
        SELECT id, phone, status, created_at, failed_login_attempts, locked_until
        FROM users
        WHERE id = :user_id AND deleted_at IS NULL
        """
    )

    try:
        row = (await db.execute(query, {"user_id": user_id})).mappings().one_or_none()
    except Exception:
        row = None

    if row is None:
        return {
            "requested_by": {
                "admin_id": current_admin.id,
                "email": current_admin.email,
            },
            "user": None,
        }

    return {
        "requested_by": {
            "admin_id": current_admin.id,
            "email": current_admin.email,
        },
        "user": {
            "id": row["id"],
            "phone": row["phone"],
            "status": row["status"],
            "created_at": row["created_at"],
            "failed_login_attempts": row["failed_login_attempts"],
            "locked_until": row["locked_until"],
        },
        "tabs": ["personal", "financial", "orders", "payments", "activity"],
    }
