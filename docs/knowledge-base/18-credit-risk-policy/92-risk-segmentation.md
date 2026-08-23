# Risk Segmentation

**Status:** STABLE (the credit-band segmentation) · PLANNED (any segmentation beyond credit band, which isn't separately documented).

## Primary segmentation: credit band

A/B/C/D/F, per [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) — this is the platform's sole formal risk-segment taxonomy referenced consistently across engineering docs (used for limits, down payments, admin dashboard filtering — `GET /admin/users?risk_band=D` is an explicit documented query pattern).

## Secondary, informal segmentation signals (used but not named as a formal segment)

- **Cold-start vs. seasoned:** first-order users are treated as a distinct risk population via the cold-start caps and the Layer 7 "first-order (cold-start) users" 30%-of-portfolio concentration limit — functionally a segment, though never given a formal name in engineering docs.
- **Cross-border abandonment risk score:** a continuous 0–1 score (Layer 6) rather than a discrete segment, but functions similarly — <0.25/0.25–0.50/0.50–0.70/>0.70 act as de facto segment boundaries.
- **Product category risk multiplier:** segments *orders* (not customers) by category (smartphones/gold jewelry treated materially differently from clothing/appliances).

## What a more complete segmentation framework would add (not currently documented)

- Behavioral segments beyond band (e.g., "high-utilization but always-on-time" vs. "low-utilization, occasional late payer") — these are meaningfully different risk profiles that a single A–F band collapses together.
- Geographic segmentation beyond the Layer 7 "single city" concentration cap (e.g., province-level default-rate variance, which the CatBoost fraud model already encodes province as a feature for — suggesting the data exists to build this, just not yet formalized as policy).
- Vintage/cohort segmentation for portfolio monitoring (how does the March 2026 onboarding cohort's default rate compare to the June 2026 cohort?) — connects to the cohort analytics gap noted in [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md) (`GET /admin/analytics/cohort` is speced but not implemented).

## Recommended action

Risk should decide whether band alone is sufficient segmentation for portfolio management at current scale, or whether a richer segmentation (behavioral, geographic, vintage) is needed before meaningful portfolio-level risk appetite (see [`87-credit-risk-framework.md`](87-credit-risk-framework.md)) can be set and monitored.

## Related documents

[`87-credit-risk-framework.md`](87-credit-risk-framework.md), [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md).
