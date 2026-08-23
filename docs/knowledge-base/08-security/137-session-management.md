# Session Management

**Status:** STABLE — the session-lifecycle-specific detail, expanded from [`29-authentication-authorization.md`](29-authentication-authorization.md).

## Session storage

Dual-tracked: a `user_sessions`/admin-session DB record plus a Redis key (`session:{token_hash}`, `admin:session:{token_hash}`) — Redis provides fast revocation checks without a DB round-trip on every authenticated request; the DB record provides durability and audit history.

## Session lifetimes

| Session type | TTL |
|---|---|
| Customer access token | 15 minutes |
| Customer refresh token | 24 hours, rotated on each use |
| Admin session | 2 hours (role-configurable), no fixed access/refresh split documented separately from the general JWT scheme |

## Concurrency rule

One concurrent session per customer — a new login invalidates the prior session (its Redis key and/or DB record marked revoked). No equivalent single-session rule is explicitly stated for admin accounts — worth confirming whether admins are intentionally allowed multiple concurrent sessions (e.g., desktop + mobile) or whether this is an oversight.

## Session revocation

`POST /auth/logout` revokes explicitly. Revocation is also implicit on: new login (customer single-session rule), and presumably on account suspension/blocking (not explicitly confirmed — does a suspended user's existing session get force-revoked immediately, or does it remain valid until natural expiry? Recommend confirming, since a suspended user retaining a valid session for up to 15 minutes/24 hours could access whatever a valid session permits during that window).

## Inactivity timeout

2-hour admin inactivity timeout (configurable per role); no inactivity timeout for customers — sessions remain valid for their full TTL regardless of activity.

## Related documents

[`29-authentication-authorization.md`](29-authentication-authorization.md), [`27-security-architecture.md`](27-security-architecture.md).
