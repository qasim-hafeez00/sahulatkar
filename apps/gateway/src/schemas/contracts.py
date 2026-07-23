from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class WakalahGenerateRequest(BaseModel):
    order_id: int = Field(..., gt=0)


class ContractDisclosure(BaseModel):
    cost_price: float
    profit_amount: float
    total_sale_price: float
    profit_rate_pct: float
    currency: str = "PKR"
    installment_count: Literal[3, 4, 6, 12] = 4


class WakalahGenerateResponse(BaseModel):
    contract_id: int
    contract_number: str
    principal_name: str
    agent_name: str
    authorized_amount: float
    valid_until: datetime
    otp_sent: bool
    dev_otp: Optional[str] = Field(default=None, description="[DEV ONLY] OTP code — not present in production")


class WakalahSignRequest(BaseModel):
    contract_id: int = Field(..., gt=0)
    otp_code: str = Field(..., min_length=6, max_length=6)
    device_id: Optional[str] = Field(default=None, max_length=255)


class MurabahaGenerateRequest(BaseModel):
    order_id: int = Field(..., gt=0)
    installment_count: Literal[3, 4, 6, 12] = 4


class MurabahaGenerateResponse(BaseModel):
    contract_id: int
    contract_number: str
    disclosure: ContractDisclosure
    otp_sent: bool
    dev_otp: Optional[str] = Field(default=None, description="[DEV ONLY] OTP code — not present in production")


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
    # principal_cnic intentionally omitted: stored AES-256 encrypted; use KYC admin
    # endpoint to retrieve decrypted CNIC via authorised channel.
    signed_at: Optional[datetime]
    created_at: datetime
    contract_pdf_path: str

    model_config = ConfigDict(from_attributes=True)
