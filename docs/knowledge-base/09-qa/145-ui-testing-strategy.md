# UI Testing Strategy

**Status:** PLANNED — most of the UI this strategy would test does not exist yet (`web-customer` ~2%, `web-admin` ~10% complete per the last audit); this document describes the target strategy for when it does.

## Coverage bar (per `docs/MASTER_PLAN.md`)

Frontend unit tests via vitest, 70% coverage target; Playwright for frontend E2E on critical paths.

## What "critical paths" should specifically mean for this product

- The full customer journey through contract signing (US-12/US-13) — given the Shariah-relevant disclosure requirements, a UI test should verify the cost breakdown is actually rendered and readable before the sign button is enabled, not just that the API call succeeds.
- The admin HITL queue claim/resolve flow (AD-06) — given its 15-minute SLA, a UI regression here has immediate operational cost.
- The admin dashboard's traffic-light KPI rendering (correctly showing red/yellow/green per the thresholds in [`../13-analytics/42-kpi-metrics-dictionary.md`](../13-analytics/42-kpi-metrics-dictionary.md)) — a miscolored threshold could cause a real operational miss.

## Honest-state testing (specific to this platform's current gaps)

Per [`../16-customer-documentation/64-customer-experience-specification.md`](../16-customer-documentation/64-customer-experience-specification.md), several UI states currently have nothing genuine to display (e.g., checkout-progress screen against an incomplete automation backend). UI tests should verify the **honest/degraded state renders correctly** (a clear "still working on it" message, not a broken or misleadingly confident status) — this is a real, present-day testing need, not a hypothetical for once the backend catches up.

## Accessibility

Not referenced in current engineering documentation as a testing requirement — recommend Product/QA decide whether an accessibility standard (WCAG level) should be adopted and tested against, given none currently exists.

## Related documents

[`143-test-strategy.md`](143-test-strategy.md), [`../16-customer-documentation/64-customer-experience-specification.md`](../16-customer-documentation/64-customer-experience-specification.md).
