from pydantic import BaseModel, Field


class VcnIssueRequest(BaseModel):
    order_id: int = Field(..., gt=0)


class VcnIssueResponse(BaseModel):
    status: str
    order_id: int
