# Acceptance Criteria

**Status:** STABLE — acceptance criteria for the platform's major features, written against the never-`xfail` critical-path tests and the module specs, so they're directly testable rather than aspirational.

## Registration & Auth

- Given a valid Pakistani phone number, an OTP is sent and a 6-digit code verified within 3 attempts issues a valid JWT pair.
- Given an admin login, access is denied without a correct TOTP code — no fallback path exists.
- Given a customer logs in on a second device, the first device's session is invalidated (1 concurrent session per customer).

## KYC

- Given a face-match score ≥80%, the applicant is auto-approved and credit scoring is triggered without human involvement.
- Given a face-match score between 70–79%, the applicant is routed to manual review, not auto-approved or auto-rejected.
- Given an expired CNIC, the applicant is rejected regardless of any other signal, with no override.

## Credit decisioning

- Given a complete application, a decision (approve/decline/review) is returned in under 3 seconds at the p99 level.
- Given a decline or borderline decision, a SHAP-based explanation with human-readable factors is available via the explain endpoint.
- Given a user's first-ever order, the approved amount never exceeds their band's cold-start cap, even if their nominal band limit is higher.

## Contract signing (hard gate — never `xfail`)

- Given an order has not reached `contracts_signed`, any attempt to issue a VCN is rejected with HTTP 403 `MURABAHA_NOT_SIGNED`, with no exception path.
- Given a Murabaha contract is generated, `cost_price`, `profit_amount`, and `total_repayable` are all non-null — the contract cannot exist without them.
- Given a late fee is charged, 100% of it is routed to the charity allocation record — none of it appears as platform revenue.

## Payments

- Given a down payment webhook is received and HMAC-verified, the corresponding installment is marked paid and `payment.down_payment_confirmed` is published exactly once per payment (not duplicated on webhook retry, once deduplication is implemented — currently a known gap).
- Given an installment reaches its due date, an automated collection attempt fires (currently a known gap — not yet implemented; this criterion is the target, not the current state).

## Checkout automation

- Given a VCN is issued, the checkout agent either completes the purchase and returns a merchant order ID, or escalates to HITL within its retry budget — it never silently fails with no record (currently a known gap, since form-filling itself is incomplete).

## Ledger

- Given any journal entry is posted, `total_debit == total_credit` for that entry (currently a known gap — not enforced in code, target criterion).
- Given a Murabaha contract is signed, corresponding liability/receivable journal entries exist for that loan (currently fails for every loan — known critical gap, target criterion).

## How to read the "currently a known gap" annotations

Several criteria above are marked as failing today. They remain listed as acceptance criteria — not removed — because they describe correct required behavior; a criterion being currently unmet is tracked in `docs/PRODUCTION_GAPS_REPORT.md`, not resolved by deleting the requirement.

## Related documents

[`45-prd.md`](45-prd.md), [`../09-qa/30-qa-strategy.md`](../09-qa/30-qa-strategy.md) (critical-path test list this document mirrors).
