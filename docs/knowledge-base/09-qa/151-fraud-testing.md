# Fraud Testing

**Status:** STABLE (strategy for the parts that exist) — Credit Engine was out of scope for the 2026-04-27 audit, so confirmed test coverage for the fraud-detection layers themselves is unverified.

## What to test

Every rule in [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md)'s velocity table should have a corresponding test: simulate the threshold-triggering condition (e.g., 4 orders in 24h for the same user) and assert the correct action fires (DECLINE/REVIEW).

## Model-based fraud testing (CatBoost, Isolation Forest)

Since these are ML models rather than deterministic rules, testing looks different: regression tests against a fixed set of known fraud/non-fraud examples (confirming the model's output for these specific inputs hasn't silently drifted after a retrain or code change), rather than testing "the logic" directly. No such regression test suite is confirmed to exist in current engineering docs — recommend Risk/ML establish one, since a silent model-behavior drift is exactly the kind of bug that's invisible without dedicated regression coverage.

## Blacklist enforcement testing

Confirm a blacklisted CNIC/phone/device/IP correctly triggers Layer 1's instant decline on the *next* attempt after being blacklisted — and confirm the currently-missing blacklist-removal path (`GW-GAP-07`) is tested once built, including that a removed entry no longer triggers a decline.

## Fraud-pattern simulation for the checkout automation specifically

Given the platform's own risk (per [`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md)) that a merchant might detect and block the purchasing pattern — this isn't "our customer committing fraud against us" but "our own automation looking fraudulent to a third party." Worth a distinct test category: does the stealth/anti-detection stack (residential proxies, fingerprint randomization, human-like timing) actually behave as intended under automated verification (e.g., running it against known bot-detection test services)? Not referenced as an existing test category in current engineering docs.

## Related documents

[`../18-credit-risk-policy/93-fraud-risk-framework.md`](../18-credit-risk-policy/93-fraud-risk-framework.md), [`../18-credit-risk-policy/94-fraud-detection-rules.md`](../18-credit-risk-policy/94-fraud-detection-rules.md).
