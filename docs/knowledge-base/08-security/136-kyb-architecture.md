# KYB Architecture

**Status:** STABLE — not applicable, confirmed here in the Security category specifically since a security architecture document set would normally include this. See [`../17-merchant-documentation/68-merchant-verification-kyb.md`](../17-merchant-documentation/68-merchant-verification-kyb.md) for the full explanation.

## Summary

SahulatKar has no business-counterparty relationship with the third-party sites it purchases from, and therefore no KYB (Know-Your-Business) architecture — no business-verification pipeline, no business-document collection, no business-risk-scoring model. This is a direct consequence of the vendor-agnostic product model (see [`../01-company-product/01-product-overview.md`](../01-company-product/01-product-overview.md)), not a security gap.

## What exists instead

Domain-level operational metadata (`merchants.domain`, `checkout_success_rate`, `bot_detection_level`) tracked for extraction/checkout reliability purposes only — see [`../17-merchant-documentation/66-merchant-lifecycle.md`](../17-merchant-documentation/66-merchant-lifecycle.md). This is not a security control and shouldn't be relied on as one; a malicious or fraudulent website would look no different in this metadata than a legitimate one having a bad extraction day.

## Related documents

[`../17-merchant-documentation/68-merchant-verification-kyb.md`](../17-merchant-documentation/68-merchant-verification-kyb.md), [`28-kyc-verification-workflow.md`](28-kyc-verification-workflow.md) (the customer-side equivalent that does exist).
