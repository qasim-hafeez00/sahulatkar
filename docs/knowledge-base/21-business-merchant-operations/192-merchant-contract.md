# Merchant Contract

**Status:** STABLE — none exists, and none is needed for the vendor-agnostic model as currently designed.

## Why

SahulatKar has no legal agreement with the vast majority of sites it purchases from — it transacts as an ordinary retail customer subject to that site's own general consumer terms of service, not a negotiated merchant contract. Whether a given site's own consumer ToS technically prohibits third-party/automated purchasing (and what legal exposure that creates) is a real open question referenced in the general BNPL research materials (`docs/Sahulatkar-docs/`) but not resolved anywhere in this codebase — this is a genuine legal risk area, not just a documentation gap, and Legal should assess it directly rather than assume it's covered by anything in engineering documentation.

## If a real affiliate-partner contract exists

If the affiliate-partner tier (see [`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md)) does represent an actual negotiated relationship with specific merchants, a real contract presumably exists for it somewhere outside this codebase (with Legal or Business Development) — this document should be updated to reference it once its existence and terms are confirmed.

## Related documents

[`../17-merchant-documentation/75-merchant-commission-fee-model.md`](../17-merchant-documentation/75-merchant-commission-fee-model.md), [`../02-business-workflows/06-merchant-vendor-journey.md`](../02-business-workflows/06-merchant-vendor-journey.md).
