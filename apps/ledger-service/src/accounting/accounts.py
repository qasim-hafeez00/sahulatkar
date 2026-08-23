

ACCOUNT_CODES = {
    "cash": "1001",
    "ar_installments": "1100",
    # Initial Murabaha financing receivable (loan commitment, before VCN charge).
    # Distinct from ar_installments (1100) which tracks individual installment payments.
    "murabaha_financing_receivable": "1101",
    "vcn_issued": "1200",
    "ap_merchants": "2001",
    "charity_payable": "2100",
    "loan_loss_reserve": "2101",
    "customer_deposits": "2200",
    # Murabaha cost payable — obligation to pay merchant once goods are procured.
    "murabaha_cost_payable": "2201",
    # Deferred profit recognised over the loan life (liability until earned).
    "deferred_murabaha_profit": "2202",
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