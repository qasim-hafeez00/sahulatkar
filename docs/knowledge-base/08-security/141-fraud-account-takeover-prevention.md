# Fraud & Account Takeover Prevention

**Status:** STABLE — the account-takeover-specific slice of the broader fraud framework in [`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md), pulled out here since it's specifically a security (not just credit-risk) concern.

## Account takeover (ATO) prevention mechanisms

| Mechanism | How it prevents ATO |
|---|---|
| OTP-based login | No password-only takeover vector for customers (password login exists as an alternative, but OTP is the primary path) |
| Single concurrent session | An attacker who obtains a valid session token can't use it alongside the legitimate user — the legitimate user's next login evicts the attacker (though this also means the *attacker's* login evicts the legitimate user, a two-way sword worth noting) |
| Admin mandatory TOTP MFA | Password-only compromise is insufficient to access admin functions |
| Device fingerprinting + trust scoring | New/untrusted devices contribute to risk scoring on subsequent actions, even after a successful login |

## Where ATO prevention is weaker than it should be

- **No TOTP brute-force lockout** (`GW-BL-05`) — an attacker with a stolen admin password could attempt unlimited TOTP guesses (though the search space of a 6-digit TOTP code with a 30-second validity window is large enough that brute force is impractical without a much larger flaw; still, a lockout is standard defense-in-depth and its absence is a gap worth closing).
- **No documented account-recovery flow security review** — how does a customer regain access if they lose their phone (the OTP delivery target)? Not documented anywhere in current engineering docs. This is a classic ATO vector in other systems (attacker socially engineers account recovery) that SahulatKar's documentation doesn't address at all — recommend this be explicitly designed and reviewed, not left implicit.
- **Refresh/access token confusion** (`SH-GAP-02`) — if a refresh token can function as an access token, an attacker who obtains a longer-lived refresh token (24hr TTL vs. 15min for access) gets a longer effective compromise window than intended.

## Related documents

[`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md), [`137-session-management.md`](137-session-management.md), [`29-authentication-authorization.md`](29-authentication-authorization.md).
