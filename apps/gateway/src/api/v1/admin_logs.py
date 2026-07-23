"""Admin Logs & Audit Trail — Phase 4 thin module (standalone, non-compliance-scoped view)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import AdminUser
from src.core.dependencies import RequirePermission, get_db

router = APIRouter(prefix="/admin/logs", tags=["Admin Logs"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


@router.get("/errors")
async def list_error_logs(
    service: Optional[str] = None,
    severity: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if service:
        where_clauses.append("service = :service")
        params["service"] = service
    if severity:
        where_clauses.append("severity = :severity")
        params["severity"] = severity
    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, error_id, service, severity, message, user_id, request_id, created_at
                FROM error_logs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()
    total = int(
        await db.scalar(
            text(f"SELECT COUNT(*) FROM error_logs {where_sql}"),
            {k: v for k, v in params.items() if k not in ("limit", "offset")},
        )
        or 0
    )

    return {
        "items": [
            {
                "id": r["id"],
                "error_id": str(r["error_id"]),
                "service": r["service"],
                "severity": r["severity"],
                "message": r["message"],
                "user_id": r["user_id"],
                "request_id": str(r["request_id"]) if r["request_id"] else None,
                "created_at": _iso(r["created_at"]),
            }
            for r in rows
        ],
        "pagination": {"page": page, "limit": limit, "total": total},
    }


@router.get("/background-jobs")
async def list_background_jobs(
    status_filter: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    offset = (page - 1) * limit
    where_sql = "WHERE status = :status_filter" if status_filter else ""
    params: dict = {"limit": limit, "offset": offset}
    if status_filter:
        params["status_filter"] = status_filter

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, job_id, queue_name, task_name, status, error_message,
                       enqueued_at, started_at, finished_at
                FROM background_jobs
                {where_sql}
                ORDER BY enqueued_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    return {
        "items": [
            {
                "id": r["id"],
                "job_id": r["job_id"],
                "queue_name": r["queue_name"],
                "task_name": r["task_name"],
                "status": r["status"],
                "error_message": r["error_message"],
                "enqueued_at": _iso(r["enqueued_at"]),
                "started_at": _iso(r["started_at"]),
                "finished_at": _iso(r["finished_at"]),
            }
            for r in rows
        ]
    }


@router.get("/scheduled-tasks")
async def list_scheduled_tasks(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                """
                SELECT id, task_name, schedule_cron, is_active, last_run_at, next_run_at, last_status
                FROM scheduled_tasks
                ORDER BY task_name
                """
            )
        )
    ).mappings().all()
    return {
        "items": [
            {
                "id": r["id"],
                "task_name": r["task_name"],
                "schedule_cron": r["schedule_cron"],
                "is_active": r["is_active"],
                "last_run_at": _iso(r["last_run_at"]),
                "next_run_at": _iso(r["next_run_at"]),
                "last_status": r["last_status"],
            }
            for r in rows
        ]
    }


@router.get("/summary")
async def logs_summary(
    current_admin: AdminUser = Depends(RequirePermission("read_reports")),
    db: AsyncSession = Depends(get_db),
) -> dict:
    error_rows = (
        await db.execute(
            text("SELECT severity, COUNT(*) AS cnt FROM error_logs WHERE created_at >= NOW() - INTERVAL '24 hours' GROUP BY severity")
        )
    ).mappings().all()
    job_rows = (
        await db.execute(text("SELECT status, COUNT(*) AS cnt FROM background_jobs GROUP BY status"))
    ).mappings().all()
    return {
        "errors_last_24h_by_severity": {r["severity"]: int(r["cnt"]) for r in error_rows},
        "jobs_by_status": {r["status"]: int(r["cnt"]) for r in job_rows},
    }
