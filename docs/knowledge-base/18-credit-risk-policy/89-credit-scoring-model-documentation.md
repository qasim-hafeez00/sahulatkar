# Credit Scoring Model Documentation

**Status:** STABLE (as far as engineering docs specify) — this is genuinely thin relative to what a model-risk-management function would normally require; gaps are flagged explicitly rather than papered over.

## Models in production (per design)

| Model | Role | Traffic split |
|---|---|---|
| XGBoost (champion) | Primary credit score | 90% |
| LightGBM (challenger) | A/B comparison against champion | 10% |
| CatBoost | Fraud model — handles categorical features (province, device brand, product category) natively | Runs alongside, not traffic-split |
| Isolation Forest | Unsupervised anomaly detector — catches novel fraud patterns the supervised models weren't trained on | Runs alongside |

## Training data

**Champion (XGBoost):** trained on the Home Credit Default Risk dataset as a **proxy** — explicitly not SahulatKar's own transaction history, since none existed at model-build time. Documented intent: retrain on real portfolio data from Month 4+ of operation. **No confirmation exists in current engineering docs that this retraining has actually happened** — recommend confirming current model provenance before treating scoring outputs as calibrated to SahulatKar's actual Pakistani thin-file population rather than a proxy dataset's population.

## Target variable and evaluation

- **Target:** DPD60 (defaulted at 60 days past due).
- **Metric:** AUC-PR, deliberately chosen over AUC-ROC because the outcome is imbalanced (~1.5–5% default rate) — AUC-ROC can look misleadingly good on imbalanced data.
- **Class imbalance handling:** SMOTEENN resampling to a 10:1 target ratio during training.

## What is not documented (real model-risk gaps)

- Feature list — no complete, versioned feature specification exists in the reviewed engineering docs beyond the layer-level signal descriptions in [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md) (e.g., "NADRA OCR confidence, scaled" — the exact scaling function isn't specified).
- Model validation/backtesting methodology and results.
- Fairness/bias testing (e.g., does the model perform equitably across provinces, given the platform explicitly encodes province as a categorical feature for the CatBoost fraud model — this is exactly the kind of feature that warrants a documented fairness check).
- Model monitoring in production (drift detection, performance degradation alerting) — not referenced anywhere.
- Retraining cadence and governance/sign-off process for deploying a new model version.

## Recommended action

Given credit scoring directly determines who gets financing and at what limit — a decision with real regulatory (SECP explainability requirement, see [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md)) and fairness implications — **this is one of the highest-priority documentation gaps in the entire knowledge base for Risk/ML leadership to close**, not just an engineering nicety.

## Related documents

[`88-eligibility-engine-specification.md`](88-eligibility-engine-specification.md), [`../03-bnpl-financing/14-eligibility-rules.md`](../03-bnpl-financing/14-eligibility-rules.md), [`../11-compliance/36-compliance-requirements-matrix.md`](../11-compliance/36-compliance-requirements-matrix.md).
