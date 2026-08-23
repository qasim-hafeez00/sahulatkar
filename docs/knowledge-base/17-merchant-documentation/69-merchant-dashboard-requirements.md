# Merchant Dashboard Requirements

**Status:** STABLE — no merchant-facing dashboard exists, is planned, or is referenced anywhere in current engineering documentation (`docs/System-md-files/M12-admin.md`'s 20 admin modules are entirely internal-staff-facing — none is scoped for external merchant access).

## Why

There is no merchant user role, no merchant login, and no merchant-scoped data view anywhere in the RBAC model (see [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md) — all 8 roles are internal staff roles). Since merchants have no account, they have nothing to log into.

## What internal staff use instead to see merchant-related data

`GET /admin/analytics/dashboard` and the `mv_merchant_performance` materialized view (orders, GMV, checkout success rate per tracked domain) give SahulatKar's own operations team visibility into merchant-adjacent metrics — but this is an internal admin capability (AD-22 "Merchant & Partner Management" in the 20-module plan, itself flagged as missing its backend — `GW-GAP-14`), not something any merchant can see.

## If this changes

A merchant-facing dashboard would only make sense once a real "affiliate partner" relationship exists (see [`75-merchant-commission-fee-model.md`](75-merchant-commission-fee-model.md)) — at that point this document should be rewritten with actual requirements (what would a partner need to see: their referred-order volume, commission owed, etc.) rather than extended from this placeholder.

## Related documents

[`65-merchant-overview.md`](65-merchant-overview.md), [`../08-security/29-authentication-authorization.md`](../08-security/29-authentication-authorization.md).
