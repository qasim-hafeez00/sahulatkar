"""
Database session factory for use by background workers.

Workers cannot use FastAPI's dependency injection, so they import SessionLocal
directly from here. This module re-exports from sk_shared.database to maintain
a single source of truth for the engine/session configuration.

All API handlers should use the get_db() dependency in src.core.dependencies instead.
"""
from sk_shared.database import SessionLocal  # noqa: F401 — re-export for workers

__all__ = ["SessionLocal"]
