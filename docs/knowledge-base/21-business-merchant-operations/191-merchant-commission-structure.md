# Merchant Commission Structure

**Status:** STABLE (as a confirmed-unresolved pointer) — this document intentionally does not restate the full analysis in [`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md); it exists to fill this category's expected slot and route the reader to the canonical answer.

## Summary

The only commission-like structure in the platform is the `is_affiliate_partner`/`commission_rate` pair on the `merchants` table, whose actual commercial meaning (a real negotiated relationship vs. an inherited Rye API byproduct vs. an unused vestigial field) is unconfirmed in current engineering documentation. See [`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md) for the full analysis and the specific questions Business Development needs to answer.

## Related documents

[`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md).
