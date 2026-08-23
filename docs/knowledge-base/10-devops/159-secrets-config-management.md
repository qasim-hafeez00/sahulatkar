# Secrets / Configuration Management

**Status:** STABLE — the DevOps-process view; [`../08-security/138-secrets-management.md`](../08-security/138-secrets-management.md) remains authoritative for the security-specific detail (inventory, rotation gap). This document covers the operational/deployment-pipeline mechanics.

## Configuration flow

`.env` (local) → GitHub Actions secrets (CI) → AWS Secrets Manager → Kubernetes ExternalSecrets (staging/production) — see `docs/SECRETS_MANAGER_MIGRATION.md`.

## Non-secret configuration

Distinct from secrets: `system_parameters` (business/policy configuration — down payment percentages, credit thresholds) is meant to be admin-managed via a database table, not deployment-pipeline configuration at all — but per [`../18-credit-risk-policy/97-credit-policy.md`](../18-credit-risk-policy/97-credit-policy.md), the admin API for this is a stub (`GW-GAP-01`), meaning these values are currently baked into deployed code rather than genuinely separated from it. This is a configuration-management anti-pattern worth naming explicitly: business policy values are currently deployment artifacts, not runtime configuration, despite the schema clearly intending the latter.

## Feature flags

`.env` template includes feature flags (`FF_JAZZCASH_ENABLED`, `FF_RAAST_ENABLED`, `FF_LITHIC_VCN`) — a lightweight environment-variable-based flagging approach, sufficient for the current scale but with no runtime toggle capability (changing a flag requires a redeploy, same limitation as the `system_parameters` gap above).

## Related documents

[`../08-security/138-secrets-management.md`](../08-security/138-secrets-management.md), [`156-environment-strategy.md`](156-environment-strategy.md), [`../18-credit-risk-policy/97-credit-policy.md`](../18-credit-risk-policy/97-credit-policy.md).
