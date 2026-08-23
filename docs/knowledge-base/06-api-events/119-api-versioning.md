# API Versioning

**Status:** STABLE — expanded from the brief mention in [`23-api-standards.md`](23-api-standards.md).

## Current practice

Path-based versioning: `/api/v1` (Gateway) or `/v1` (other services). No service has shipped a `v2` yet, so no real precedent exists in this codebase for how a breaking change would be introduced — the following is proposed policy, not observed practice.

## Inconsistency to resolve

Gateway uses `/api/v1`, other services use `/v1` — pick one prefix convention platform-wide (already flagged in [`23-api-standards.md`](23-api-standards.md); repeated here since versioning consistency is specifically this document's concern).

## Proposed versioning policy (not yet formalized)

- A new major version (`v2`) is warranted only for a breaking change (removed field, changed semantics, incompatible auth) — additive changes (new optional field, new endpoint) should not require a version bump.
- Old versions should have a documented deprecation window before removal — no such window is specified anywhere currently, since the scenario hasn't arisen yet.
- Internal service-to-service calls (the `X-Internal-Token`-authenticated surface) should version independently of the customer/admin-facing surface, since they're deployed in lockstep as part of the same monorepo and don't need the same backward-compatibility guarantees external consumers would require.

## Related documents

[`23-api-standards.md`](23-api-standards.md), [`118-api-architecture.md`](118-api-architecture.md).
