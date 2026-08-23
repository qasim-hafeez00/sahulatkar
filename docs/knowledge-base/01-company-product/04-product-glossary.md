# Product Glossary

**Status:** STABLE — terms and definitions drawn directly from the schema/spec docs (`docs/System-md-files/`) so they match what the code actually calls things.

Terms are grouped by domain. Where SahulatKar's usage differs from generic BNPL/fintech usage, that's called out explicitly.

## Customer & Identity

| Term | Definition |
|---|---|
| **User / Customer** | An individual with a `users` record; identified by E.164 phone (`+92XXXXXXXXXX`), CNIC-verified during KYC. |
| **KYC (Know Your Customer)** | The identity verification pipeline: CNIC OCR → NADRA Verisys check → liveness detection → face match → (if borderline) manual review. See [`../08-security/28-kyc-verification-workflow.md`](../08-security/28-kyc-verification-workflow.md). |
| **KYB (Know Your Business)** | **Not applicable in the current model** — SahulatKar does not onboard merchants, so there is no business-verification pipeline. Reserved terminology for a possible future "affiliate merchant partnership" tier. |
| **Tier 1 / Tier 2 KYC** | Tier 1 (standard, all new users, target <4 min): CNIC OCR, NADRA, liveness, face match, device fingerprint. Tier 2 (Enhanced Due Diligence, triggered by orders >PKR 5K or a fraud flag, target <10 min): adds bank/wallet connection, income proof, utility bill. |
| **NADRA Verisys** | Pakistan's National Database and Registration Authority identity-verification API; confirms a CNIC is valid/blocked/expired and checks name match. |
| **Liveness detection** | Anti-spoofing check (blink + head-turn) during KYC selfie capture, via Shufti Pro or equivalent vendor. Threshold: liveness score ≥ 0.85. |
| **Device fingerprint** | A hashed device identity (via FingerprintJS Pro) used for fraud/velocity signals — flags emulators, rooted devices, VPN usage. |

## Product & Extraction

| Term | Definition |
|---|---|
| **UPO (Universal Product Object)** | The normalized internal representation of a scraped product: title, price, availability, variants, shipping, computed financing terms — regardless of source platform (Amazon, Shopify, Daraz, custom site). |
| **Extraction waterfall** | The 4-tier fallback chain used to turn a URL into a UPO: Tier 1 Rye API (Amazon/Shopify) → Tier 2 JSON-LD/schema.org parsing → Tier 3 Playwright + LLM (any site) → Tier 4 HITL (manual). |
| **Merchant** | In SahulatKar's data model, any third-party website the checkout agent transacts with — not a partner or integration, just the destination of a purchase. See [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md). |
| **Prohibited category** | A Shariah-blocked product class (alcohol, tobacco, gambling, adult content, weapons, interest-bearing instruments) — checked and blocked before any financing offer is generated. |

## BNPL / Financing

| Term | Definition |
|---|---|
| **BNPL Plan / Payment Plan** | One of `pay_in_3`, `pay_in_4`, `pay_in_6`, or `pay_full` — the number of installments a customer selects for a given order. |
| **Financing / Loan** | The `loans` record created once a Murabaha contract is signed: principal, profit, total repayable, down payment, plan type, status. |
| **Wakalah Agreement** | The first of two Shariah contracts: the customer appoints SahulatKar as *Wakeel* (agent) to purchase a specific product at an authorized amount, on their behalf. Signed via OTP. |
| **Murabaha Contract** | The second Shariah contract: SahulatKar sells the procured product to the customer at cost price plus a disclosed, fixed profit — with a fixed installment schedule. Signing this is the **hard gate** that unlocks VCN issuance. |
| **Eligibility** | Whether a user passes the credit engine's 7-layer pipeline for a given order amount — see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md). |
| **Credit Limit** | The maximum outstanding principal a user is approved for, determined by credit band (A–F) and subject to cold-start caps on a user's first-ever order. |
| **Available Limit / Available Credit** | Credit limit minus currently outstanding principal across active loans. |
| **Credit Band** | One of A/B/C/D/F, output by the credit engine; determines limit and down-payment percentage. F = decline. |
| **Down payment** | 25–40% of order value, collected before VCN issuance; percentage set by credit band. |
| **Installment** | One scheduled repayment on a loan; carries `principal_portion`, `profit_portion`, `due_date`, `status`. |
| **Default** | An installment/loan that has passed its due date without payment and moved through the overdue → default state progression (see [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md)). |
| **Delinquency** | The state of having one or more overdue installments; drives the collections escalation timeline in [`../02-business-workflows/10-default-collections-workflow.md`](../02-business-workflows/10-default-collections-workflow.md). |

## Payments

| Term | Definition |
|---|---|
| **VCN (Virtual Card Number)** | A single-use, MCC-locked, amount-capped virtual card issued (via Stripe Issuing, moving to Lithic at scale) only after the Murabaha is signed and down payment is confirmed. Void after first successful charge or 24 hours, whichever first. |
| **Hard Gate** | The enforced rule that VCN issuance cannot occur until `order.status == "contracts_signed"`; violating this returns HTTP 403 `MURABAHA_NOT_SIGNED`. |
| **Payment / Payment Transaction** | A single gateway charge attempt (Safepay/JazzCash/EasyPaisa/Raast/manual) tied to an installment. |
| **Settlement** | Reconciliation of what a payment gateway reports it collected/paid out against SahulatKar's internal `payment_transactions` records. |
| **Refund** | Return of funds to a customer, e.g. on order cancellation or merchant non-fulfillment. **Not yet implemented in code** as of the last audit — see [`../02-business-workflows/09-refund-cancellation-workflow.md`](../02-business-workflows/09-refund-cancellation-workflow.md). |
| **Reversal** | A ledger-level correction entry, distinct from a customer-facing refund. |

## Ledger

| Term | Definition |
|---|---|
| **Ledger** | The double-entry system of record (`ledger_accounts`, `journal_entries`, `journal_entry_lines`) tracking every financial movement in the platform. |
| **Disbursement** | Funds paid out — in SahulatKar's case, primarily the charity disbursement of collected late fees. |
| **Charity routing** | The mechanism (DB trigger `fn_apply_late_fee()`, `late_fee_charity_allocations` table) that ensures 100% of late fees go to a designated charity (Edhi Foundation), never to platform revenue. |
| **Collection** | The daily automated sweep (`BillingSweepWorker`) that identifies due/overdue installments and attempts auto-debit. |
| **Underwriting** | The credit engine's decisioning process — see **Eligibility** above. |

## Order Lifecycle

See [`../03-bnpl-financing/16-financing-state-machine.md`](../03-bnpl-financing/16-financing-state-machine.md) for the full 19-state order lifecycle (`url_submitted` → ... → `completed`/`cancelled`/`refunded`/`disputed`).
