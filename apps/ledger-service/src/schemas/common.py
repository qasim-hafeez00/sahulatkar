from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationResponse(BaseModel):
    page: int = Field(..., ge=1)
    limit: int = Field(..., ge=1)
    total: int = Field(..., ge=0)
