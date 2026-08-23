"""
Security utilities for the payment orchestrator.
"""
import secrets
from functools import wraps
from typing import Callable

from fastapi import HTTPException, status


def require_roles(*allowed_roles: str) -> Callable:
    """Decorator for role-based access control on route handlers."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            role = kwargs.get("role")
            if role not in allowed_roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="INSUFFICIENT_PERMISSIONS",
                )
            return await func(*args, **kwargs)
        return wrapper
    return decorator


def constant_time_compare(a: str, b: str) -> bool:
    """
    Timing-safe string comparison to prevent timing attacks on shared secrets.
    Uses secrets.compare_digest internally.
    """
    if not a or not b:
        return False
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))