import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.auth import User
from src.core.dependencies import get_current_user, get_db
from src.schemas.support import (
    TicketCreateRequest,
    TicketDetail,
    TicketMessageCreateRequest,
    TicketMessageItem,
    TicketSummary,
)

router = APIRouter(prefix="/support", tags=["support"])


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else v


def _to_summary(row) -> TicketSummary:
    return TicketSummary(
        id=row["id"],
        ticket_number=row["ticket_number"],
        category=row["category"],
        subject=row["subject"],
        status=row["status"],
        order_id=row["order_id"],
        loan_id=row["loan_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("/tickets", response_model=TicketDetail, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.order_id is not None:
        owns_order = await db.scalar(
            text("SELECT 1 FROM orders WHERE id = :order_id AND user_id = :user_id AND deleted_at IS NULL"),
            {"order_id": payload.order_id, "user_id": current_user.id},
        )
        if not owns_order:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ORDER_NOT_FOUND")

    if payload.loan_id is not None:
        owns_loan = await db.scalar(
            text("SELECT 1 FROM loans WHERE id = :loan_id AND user_id = :user_id AND deleted_at IS NULL"),
            {"loan_id": payload.loan_id, "user_id": current_user.id},
        )
        if not owns_loan:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="LOAN_NOT_FOUND")

    ticket_number = f"TCK-{uuid.uuid4().hex[:10].upper()}"
    now = datetime.utcnow()

    row = (
        await db.execute(
            text(
                """
                INSERT INTO support_tickets
                    (ticket_number, user_id, order_id, loan_id, category, subject, status, created_at, updated_at)
                VALUES
                    (:ticket_number, :user_id, :order_id, :loan_id, :category, :subject, 'open', :now, :now)
                RETURNING id, ticket_number, category, subject, status, order_id, loan_id, created_at, updated_at
                """
            ),
            {
                "ticket_number": ticket_number,
                "user_id": current_user.id,
                "order_id": payload.order_id,
                "loan_id": payload.loan_id,
                "category": payload.category,
                "subject": payload.subject,
                "now": now,
            },
        )
    ).mappings().one()

    msg_row = (
        await db.execute(
            text(
                """
                INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, message_text, created_at)
                VALUES (:ticket_id, 'user', :sender_id, :message_text, :now)
                RETURNING id, sender_type, sender_id, message_text, created_at
                """
            ),
            {"ticket_id": row["id"], "sender_id": current_user.id, "message_text": payload.description, "now": now},
        )
    ).mappings().one()

    await db.commit()

    return TicketDetail(
        **_to_summary(row).model_dump(),
        messages=[
            TicketMessageItem(
                id=msg_row["id"],
                sender_type=msg_row["sender_type"],
                sender_id=msg_row["sender_id"],
                message_text=msg_row["message_text"],
                created_at=msg_row["created_at"],
            )
        ],
    )


@router.get("/tickets", response_model=list[TicketSummary])
async def list_my_tickets(
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    where_clauses = ["user_id = :user_id"]
    params: dict = {"user_id": current_user.id, "limit": limit, "offset": (page - 1) * limit}
    if category:
        where_clauses.append("category = :category")
        params["category"] = category

    rows = (
        await db.execute(
            text(
                f"""
                SELECT id, ticket_number, category, subject, status, order_id, loan_id, created_at, updated_at
                FROM support_tickets
                WHERE {' AND '.join(where_clauses)}
                ORDER BY created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        )
    ).mappings().all()

    return [_to_summary(r) for r in rows]


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_my_ticket(
    ticket_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    row = (
        await db.execute(
            text(
                """
                SELECT id, ticket_number, category, subject, status, order_id, loan_id, created_at, updated_at
                FROM support_tickets
                WHERE id = :ticket_id AND user_id = :user_id
                """
            ),
            {"ticket_id": ticket_id, "user_id": current_user.id},
        )
    ).mappings().one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    messages = (
        await db.execute(
            text(
                """
                SELECT id, sender_type, sender_id, message_text, created_at
                FROM ticket_messages
                WHERE ticket_id = :ticket_id AND is_internal_note = false
                ORDER BY created_at ASC
                """
            ),
            {"ticket_id": ticket_id},
        )
    ).mappings().all()

    return TicketDetail(
        **_to_summary(row).model_dump(),
        messages=[
            TicketMessageItem(
                id=m["id"], sender_type=m["sender_type"], sender_id=m["sender_id"],
                message_text=m["message_text"], created_at=m["created_at"],
            )
            for m in messages
        ],
    )


@router.post("/tickets/{ticket_id}/messages", response_model=TicketMessageItem, status_code=status.HTTP_201_CREATED)
async def add_ticket_message(
    ticket_id: int,
    payload: TicketMessageCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    owns_ticket = await db.scalar(
        text("SELECT 1 FROM support_tickets WHERE id = :ticket_id AND user_id = :user_id"),
        {"ticket_id": ticket_id, "user_id": current_user.id},
    )
    if not owns_ticket:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="TICKET_NOT_FOUND")

    now = datetime.utcnow()
    msg_row = (
        await db.execute(
            text(
                """
                INSERT INTO ticket_messages (ticket_id, sender_type, sender_id, message_text, created_at)
                VALUES (:ticket_id, 'user', :sender_id, :message_text, :now)
                RETURNING id, sender_type, sender_id, message_text, created_at
                """
            ),
            {"ticket_id": ticket_id, "sender_id": current_user.id, "message_text": payload.message, "now": now},
        )
    ).mappings().one()

    # A customer reply means the ticket needs agent attention again.
    await db.execute(
        text(
            "UPDATE support_tickets SET status = 'open', updated_at = :now "
            "WHERE id = :ticket_id AND status IN ('resolved', 'waiting_user')"
        ),
        {"ticket_id": ticket_id, "now": now},
    )
    await db.commit()

    return TicketMessageItem(
        id=msg_row["id"], sender_type=msg_row["sender_type"], sender_id=msg_row["sender_id"],
        message_text=msg_row["message_text"], created_at=msg_row["created_at"],
    )
