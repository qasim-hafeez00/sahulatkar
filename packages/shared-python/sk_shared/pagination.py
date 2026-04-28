import base64
import json
from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel
from sqlalchemy import Select

T = TypeVar("T")

class PageResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    size: int
    pages: int

class CursorResponse(BaseModel, Generic[T]):
    items: List[T]
    next_cursor: Optional[str]

def apply_pagination(stmt: Select, page: int = 1, size: int = 20) -> Select:
    if page < 1:
        page = 1
    if size < 1:
        size = 20
    offset_val = (page - 1) * size
    return stmt.offset(offset_val).limit(size)

def encode_cursor(data: dict[str, Any]) -> str:
    """Encode a cursor dict (e.g. {"id": 42, "created_at": "..."}) to a URL-safe string."""
    return base64.urlsafe_b64encode(json.dumps(data, default=str).encode()).decode()

def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode a cursor string back to a dict. Raises ValueError on malformed input."""
    try:
        return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
    except Exception as exc:
        raise ValueError(f"Invalid cursor: {cursor!r}") from exc
