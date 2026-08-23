# Eligibility Engine Specification

**Status:** STABLE — this is the technical-specification-format companion to [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), written for an engineer implementing/maintaining the Credit Engine rather than for a product/risk reader. Full layer-by-layer detail lives in that document — this one covers engine-level behavior: performance budget, failure handling, and versioning.

## Performance budget (per layer, must sum to <3s total)

| Layer | Budget | Data source |
|---|---|---|
| 1. Hard blocks | <5ms | Redis only, zero DB round-trip |
| 2. Velocity | <20ms | Redis sliding windows |
| 3. Identity/device | <50ms | KYC signals, precomputed |
| 4. Alternative data | <200ms | JazzCash API (external call — the single largest latency budget item, since it's the only layer dependent on a third-party synchronous call) |
| 5. ML scoring | <100ms | In-process model inference (XGBoost/LightGBM/CatBoost/Isolation Forest) |
| 6. Category overlay | <30ms | In-process lookup |
| 7. Portfolio controls | <10ms | Precomputed/cached aggregate |

## Failure handling per layer (not explicitly documented — engineering should confirm/fill in)

What happens if Layer 4's external API call times out or errors? Current documentation does not specify a fallback (proceed without alternative data, at a penalty? fail closed to manual review? fail open to a decline?) — this is a real engineering decision that materially affects approval rate and risk, and should be explicitly specified and tested, not left as whatever the current implementation happens to do by accident.

## Short-circuiting behavior

Layer 1 is explicitly short-circuiting (any hard block = instant decline, no further processing) — this is both a performance optimization (skip 6 more layers of work for an obvious decline) and a correctness requirement (a blacklisted entity should never reach a "maybe approve" outcome via some other layer). Layers 2–7 are presumed to run in sequence and combine into a composite decision, but the exact combination logic (weighted sum? sequential override? first-decline-wins beyond Layer 1?) across Layers 2–7 is not explicitly specified in current engineering docs — recommend this be documented precisely, since it directly determines approval-rate behavior and needs to be reproducible for the SHAP explainability requirement to make sense.

## Model versioning

`risk_assessments.model_version` is tracked per assessment — meaning the engine is designed to support multiple model versions running or having run over time (e.g., champion/challenger per Layer 5). No documented process exists for how a new model version gets promoted from challenger to champion, or how a version is rolled back if it underperforms — recommend Risk/ML define this as an explicit MLOps process.

## Related documents

[`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`89-credit-scoring-model-documentation.md`](89-credit-scoring-model-documentation.md), [`../05-architecture/microservices/credit-engine.md`](../05-architecture/microservices/credit-engine.md).
