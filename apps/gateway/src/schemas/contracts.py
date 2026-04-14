from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class WakalahGenerateRequest(BaseModel):
    order_id: int = Field(..., gt=0)


class ContractDisclosure(BaseModel):
    cost_price: float
    profit_amount: float
    total_sale_price: float
    profit_rate_pct: float
    currency: str = "PKR"
    installment_count: int


class WakalahGenerateResponse(BaseModel):
    contract_id: int
    contract_number: str
    principal_name: str
    agent_name: str
    authorized_amount: float
    valid_until: datetime
    otp_sent: bool


class WakalahSignRequest(BaseModel):
    contract_id: int = Field(..., gt=0)
    otp_code: str = Field(..., min_length=6, max_length=6)
    device_id: Optional[str] = Field(default=None, max_length=255)


class MurabahaGenerateRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    installment_count: int = Field(default=4, ge=2, le=12)


class MurabahaGenerateResponse(BaseModel):
    contract_id: int
    contract_number: str
    disclosure: ContractDisclosure
    otp_sent: bool


class MurabahaSignRequest(BaseModel):
    contract_id: int = Field(..., gt=0)
    otp_code: str = Field(..., min_length=6, max_length=6)
    confirmation_checkbox: bool = Field(...)
    device_id: Optional[str] = Field(default=None, max_length=255)


class ContractSignResponse(BaseModel):
    signed: bool
    signed_at: datetime
    order_status: str


class ContractStatusResponse(BaseModel):
    order_id: int
    order_status: str
    wakalah_signed: bool
    murabaha_signed: bool
    wakalah_contract_id: Optional[int]
    murabaha_contract_id: Optional[int]
    financial_summary: Optional[ContractDisclosure] = None

    model_config = ConfigDict(from_attributes=True)


class AdminContractResponse(BaseModel):
    id: int
    contract_number: str
    user_id: int
    order_id: int
    principal_name: Optional[str]
    principal_cnic: Optional[str]
    signed_at: Optional[datetime]
    created_at: datetime
    contract_pdf_path: str

    model_config = ConfigDict(from_attributes=True)
