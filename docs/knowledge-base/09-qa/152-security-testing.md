# Security Testing

**Status:** PLANNED — explicit Phase 4 targets (OWASP Top 10 audit, penetration testing on payment/VCN flows) per `docs/MASTER_PLAN.md` §8, not yet conducted per the audit.

## Automated security testing (currently specified)

`bandit` static analysis, zero high-severity findings required per CI policy (see [`30-qa-strategy.md`](30-qa-strategy.md)) — this is the only security-testing tooling confirmed to actually run today.

## What's planned but not yet done

- OWASP Top 10 checklist audit.
- Penetration testing specifically targeting payment flows and VCN isolation — given VCN credential exfiltration is the #1-ranked asset risk in [`../08-security/140-security-threat-model.md`](../08-security/140-security-threat-model.md), this should be prioritized as the first pen-test target once testing begins.
- No secret-scanning in CI (`INF-GAP-09`) — a gap this document should flag as a security-testing gap specifically, since scanning is itself a form of continuous security testing that's currently absent.

## Recommended targeted tests, given the platform's own confirmed gaps

Rather than waiting for a full external pen-test engagement, several of the already-known gaps in [`../08-security/140-security-threat-model.md`](../08-security/140-security-threat-model.md) can be turned into concrete, immediate security tests: rate-limit testing against the VCN-decrypt endpoint (currently has none — a test confirming this absence would document the gap and later confirm the fix), TOTP brute-force attempt testing (confirming there's currently no lockout, then confirming one exists post-fix), and a test confirming the SendGrid webhook currently accepts unsigned requests (documenting `NS-BL-01`, flipping to a rejection test post-fix).

## Related documents

[`../08-security/140-security-threat-model.md`](../08-security/140-security-threat-model.md), [`../08-security/142-security-incident-response.md`](../08-security/142-security-incident-response.md).
