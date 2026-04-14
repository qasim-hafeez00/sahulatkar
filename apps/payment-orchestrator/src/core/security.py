from functools import wraps
from typing import Callable

from fastapi import HTTPException, status


def require_roles(*allowed_roles: str) -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            role = kwargs.get("role")
            if role not in allowed_roles:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
            return await func(*args, **kwargs)

        return wrapper

    return decorator