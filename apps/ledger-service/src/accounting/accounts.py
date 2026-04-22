from dataclasses import dataclass
from decimal import Decimal


ACCOUNT_CODES = {
    "cash": "1001",
    "ar_installments": "1100",
    "vcn_issued": "1200",
    "ap_merchants": "2001",
    "charity_payable": "2100",
    "loan_loss_reserve": "2101",
    "customer_deposits": "2200",
    "owner_equity": "3001",
    "retained_earnings": "3900",
    "murabaha_profit": "4001",
    "affiliate_commission": "4002",
    "late_fee_collections": "4003",
    "cogs_merchant_payment": "5001",
    "gateway_fees": "5002",
    "vcn_issuance": "5003",
    "loan_loss_provision": "5004",
}