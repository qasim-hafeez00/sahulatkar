# Chart of Accounts

**Status:** STABLE — seed data, sourced verbatim from `docs/System-md-files/M10-M12-delivery-ledger-admin.md`.

## Accounts

```
ASSETS:
  1001 Cash/Bank
  1100 AR-Installments (Accounts Receivable — customer installments outstanding)
  1200 VCNs Issued (funds committed to issued, unspent virtual cards)

LIABILITY:
  2001 AP-Merchants (Accounts Payable — not actively used given immediate merchant payment, see below)
  2100 Charity Payable (accrued, undisbursed late fees owed to charity)
  2200 Customer Deposits (down payments received, pre-recognition)

EQUITY:
  3001 Owner Equity
  3900 Retained Earnings

REVENUE:
  4001 Murabaha Profit
  4002 Affiliate Commission
  4003 Late Fee Collections

EXPENSE:
  5001 COGS-Merchant Payment
  5002 Gateway Fees
  5003 VCN Issuance
  5004 Loan Loss Provision
```

## Notes on account usage given SahulatKar's specific model

- **2001 AP-Merchants** exists in the schema but, given there is no deferred merchant payment (SahulatKar pays merchants immediately via VCN — see [`../17-merchant-documentation/72-merchant-settlement-flow.md`](../17-merchant-documentation/72-merchant-settlement-flow.md)), it's unclear from current documentation whether this account is actually used in practice or is a vestigial account from an earlier design assumption. Finance should confirm whether any transaction type actually posts to it.
- **4003 Late Fee Collections** is a revenue account, yet the platform's own Shariah design states 100% of late fees are charity-routed, not retained (see [`../04-shariah/17-shariah-product-structure.md`](../04-shariah/17-shariah-product-structure.md)). This is worth Finance clarifying explicitly: does this account temporarily hold collected late fees before they're moved to **2100 Charity Payable**, or is its presence in the revenue section a naming/categorization artifact that should be corrected? As written, having a "Late Fee Collections" account under REVENUE without an obvious offsetting entry is exactly the kind of ambiguity that could let late-fee amounts get miscounted as platform income in a report, contradicting the platform's own compliance commitments.
- **5004 Loan Loss Provision** exists in the chart but, per [`87-credit-risk-framework.md`](../18-credit-risk-policy/87-credit-risk-framework.md), no documented loss-provisioning policy exists to say when/how much gets provisioned — the account is ready; the policy that would populate it isn't written yet.

## Related documents

[`109-ledger-architecture.md`](109-ledger-architecture.md), [`112-transaction-types.md`](112-transaction-types.md), [`../18-credit-risk-policy/98-collections-recovery-policy.md`](../18-credit-risk-policy/98-collections-recovery-policy.md).
