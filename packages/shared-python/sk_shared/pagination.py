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
