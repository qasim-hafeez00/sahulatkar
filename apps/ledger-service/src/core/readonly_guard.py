"""
Read-Only Session Enforcement

Provides decorators and wrappers to ensure ledger service operations
only read from external tables and never write to them. This prevents
accidental data corruption in other microservices' tables.
"""

from __future__ import annotations

import functools
import logging
from typing import Any, Callable, TypeVar

from sqlalchemy import inspect, event
from sqlalchemy.ext.asyncio import AsyncSession

from sk_shared.models.ledger import (
    JournalEntry,
    JournalEntryLine,
    LedgerAccount,
    LateFeeCharityAllocation,
    LedgerPeriod,
    LedgerAccountBalance,
)


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Ledger service owns these tables - can be written to
OWNED_TABLES = {
    "ledger_accounts",
    "journal_entries",
    "journal_entry_lines",
    "late_fee_charity_allocations",
    "reconciliations",
    "reconciliation_items",
    "ledger_periods",
    "ledger_account_balances",
}

# Explicitly read-only tables (owned by other services)
READONLY_TABLES = {
    "payment_transactions",
    "installments",
    "loans",
    "credit_applications",
}


class ReadOnlyViolationError(Exception):
    """Raised when a write is attempted on a read-only table."""
    pass


def readonly_guard(func: F) -> F:
    """
    Decorator to enforce read-only table restrictions.
    
    Intercepts SQLAlchemy flush events to ensure that only owned tables
    are modified during the execution of the decorated function.
    """

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # 1. Locate the AsyncSession
        session: AsyncSession | None = None
        
        # Check if first arg is a service with .db session
        if args and hasattr(args[0], "db") and isinstance(args[0].db, AsyncSession):
            session = args[0].db
        
        # Check positional args
        if session is None:
            for arg in args:
                if isinstance(arg, AsyncSession):
                    session = arg
                    break
        
        # Check keyword args
        if session is None:
            session = kwargs.get("session") or kwargs.get("db_session") or kwargs.get("db")
        
        # If no session found, we cannot enforce (warn and continue)
        if session is None:
            logger.debug(f"Read-only enforcement skipped for {func.__name__}: no session found")
            return await func(*args, **kwargs)

        def _before_flush(session_inner, flush_context, instances):
            """Internal validator called by SQLAlchemy before flush."""
            # Check NEW objects
            for obj in session_inner.new:
                table_name = _get_table_name(obj)
                if table_name and table_name not in OWNED_TABLES:
                    raise ReadOnlyViolationError(
                        f"Unauthorized INSERT into read-only table '{table_name}' during {func.__name__}"
                    )

            # Check DIRTY (modified) objects
            for obj in session_inner.dirty:
                table_name = _get_table_name(obj)
                if table_name and table_name not in OWNED_TABLES:
                    # Check if any actual columns were changed
                    if session_inner.is_modified(obj):
                        raise ReadOnlyViolationError(
                            f"Unauthorized UPDATE to read-only table '{table_name}' during {func.__name__}"
                        )

            # Check DELETED objects
            for obj in session_inner.deleted:
                table_name = _get_table_name(obj)
                if table_name and table_name not in OWNED_TABLES:
                    raise ReadOnlyViolationError(
                        f"Unauthorized DELETE from read-only table '{table_name}' during {func.__name__}"
                    )

        # Register the listener on the synchronous session
        sync_session = session.sync_session
        event.listen(sync_session, "before_flush", _before_flush)
        
        try:
            return await func(*args, **kwargs)
        finally:
            # Always remove the listener to avoid leaking it to other operations
            event.remove(sync_session, "before_flush", _before_flush)

    return wrapper  # type: ignore


def _get_table_name(obj: Any) -> str | None:
    """Helper to extract table name from a model instance."""
    try:
        mapper = inspect(type(obj))
        if hasattr(mapper, "mapped_table"):
            return str(mapper.mapped_table.name)
        return None
    except Exception:
        return None


def is_readonly_enforced(func: Callable[..., Any]) -> bool:
    """Utility to check if a function is protected by the guard."""
    return hasattr(func, "__wrapped__")
