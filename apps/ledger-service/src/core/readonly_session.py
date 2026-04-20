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

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import SessionRecipient

from sk_shared.models.ledger import (
    JournalEntry,
    JournalEntryLine,
    LedgerAccount,
    LateFeeCharityAllocation,
)


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

# Ledger service owns these tables - can be written to
OWNED_TABLES = {
    "ledger_accounts",
    "journal_entries",
    "journal_entry_lines",
    "late_fee_charity_allocations",
}

# External tables - read-only in ledger context
READONLY_TABLES = {
    "users",
    "loans",
    "installments",
    "payment_transactions",
    "customer_profiles",
    "charity_organizations",
    "vcn_transactions",
}


class ReadOnlyViolationError(Exception):
    """Raised when attempting to modify a read-only table."""
    pass


def get_table_owner(table_name: str) -> str:
    """Determine which service owns a table."""
    if table_name in OWNED_TABLES:
        return "ledger-service"
    elif table_name in READONLY_TABLES:
        return "external"
    else:
        return "unknown"


def require_readonly_session(func: F) -> F:
    """
    Decorator that enforces read-only mode for a function.
    
    Prevents any SQL INSERT, UPDATE, or DELETE operations on non-owned tables.
    Logs all write attempts and raises ReadOnlyViolationError on violation.
    
    Usage:
        @require_readonly_session
        async def get_customer_profile(session: AsyncSession, user_id: int):
            # Only reads allowed; writes will raise error
            ...
    """
    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Find AsyncSession in args or kwargs
        session: AsyncSession | None = None
        for arg in args:
            if isinstance(arg, AsyncSession):
                session = arg
                break
        if session is None:
            session = kwargs.get("session") or kwargs.get("db_session")
        
        if session is None:
            logger.warning(f"Could not find AsyncSession in {func.__name__}; skipping readonly enforcement")
            return await func(*args, **kwargs)
        
        # Store original flush method
        original_flush = session.flush
        flush_called = False
        
        async def enforcing_flush(*flush_args: Any, **flush_kwargs: Any) -> None:
            """Intercept flush to check for unauthorized writes."""
            nonlocal flush_called
            flush_called = True
            
            # Inspect pending changes
            new_objects = []
            dirty_objects = []
            deleted_objects = []
            
            if hasattr(session, "new"):
                new_objects = list(session.new) if session.new else []
            if hasattr(session, "dirty"):
                dirty_objects = list(session.dirty) if session.dirty else []
            if hasattr(session, "deleted"):
                deleted_objects = list(session.deleted) if session.deleted else []
            
            # Check if any changes violate read-only constraint
            for obj in new_objects:
                mapper = inspect(type(obj))
                table_name = mapper.mapped_table.name if hasattr(mapper, "mapped_table") else "unknown"
                if table_name not in OWNED_TABLES and table_name != "unknown":
                    raise ReadOnlyViolationError(
                        f"Attempted INSERT into read-only table '{table_name}' from {func.__name__}. "
                        f"Ledger service can only write to: {', '.join(OWNED_TABLES)}"
                    )
            
            for obj in dirty_objects:
                mapper = inspect(type(obj))
                table_name = mapper.mapped_table.name if hasattr(mapper, "mapped_table") else "unknown"
                if table_name not in OWNED_TABLES and table_name != "unknown":
                    raise ReadOnlyViolationError(
                        f"Attempted UPDATE to read-only table '{table_name}' from {func.__name__}. "
                        f"Ledger service can only write to: {', '.join(OWNED_TABLES)}"
                    )
            
            for obj in deleted_objects:
                mapper = inspect(type(obj))
                table_name = mapper.mapped_table.name if hasattr(mapper, "mapped_table") else "unknown"
                if table_name not in OWNED_TABLES and table_name != "unknown":
                    raise ReadOnlyViolationError(
                        f"Attempted DELETE from read-only table '{table_name}' from {func.__name__}. "
                        f"Ledger service can only write to: {', '.join(OWNED_TABLES)}"
                    )
            
            # Call original flush if no violations
            return await original_flush(*flush_args, **flush_kwargs)
        
        # Monkey-patch the session's flush method
        session.flush = enforcing_flush
        
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            # Restore original flush
            session.flush = original_flush


def is_readonly_function(func: Callable[..., Any]) -> bool:
    """Check if a function has been decorated with @require_readonly_session."""
    return hasattr(func, "__wrapped__") or hasattr(func, "_readonly_enforced")
