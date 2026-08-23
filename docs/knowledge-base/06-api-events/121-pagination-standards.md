# Pagination Standards

**Status:** STABLE — expanded from [`23-api-standards.md`](23-api-standards.md).

## The standard

Cursor-based pagination via `sk_shared/pagination.py`'s `PaginationParams` — this should be the single implementation every service's list endpoints use.

## Current reality

At least two independent, duplicated pagination implementations exist: Gateway's own manual pagination, and Product Service's `_encode_cursor()`/`_decode_cursor()` — neither uses the shared package that already exists for this purpose. Ledger Service's journal-entry listing is separately confirmed cursor-paginated, which may or may not be the same implementation as either of the above.

## Why this matters beyond code cleanliness

Divergent pagination implementations risk divergent *behavior* — different cursor encoding means a client can't apply a generic "next page" pattern across services, and any bug fix (e.g., handling a deleted item mid-pagination) has to be found and fixed in multiple places instead of once.

## Recommended remediation

Migrate Gateway and Product Service's pagination to `sk_shared/pagination.py`, and audit every other service's list endpoints to confirm they do the same — tracked as a cross-service consistency item in [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`../05-architecture/21-service-responsibility-matrix.md`](../05-architecture/21-service-responsibility-matrix.md).
