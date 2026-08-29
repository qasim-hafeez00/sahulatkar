# Release Plan

**Status:** STABLE — distinct from [`43-product-roadmap.md`](43-product-roadmap.md) (which covers the multi-month phase structure); this document covers the mechanics of an individual release, per [`../10-devops/34-deployment-process.md`](../10-devops/34-deployment-process.md)'s CI/CD pipeline.

## Release cadence

Per the CD pipeline: every merge to `main` triggers a staging deploy automatically; production requires a manual approval gate after staging smoke tests pass. This implies a **continuous-ish** release model (no fixed release train/date) rather than scheduled releases — consistent with the platform's current solo/small-team development stage per `docs/MASTER_PLAN.md`.

## What a release includes

Per the CD pipeline's "detect changed services" step, a release can be partial — only services with actual code changes get rebuilt and redeployed, not a full-platform release every time. This means "a release" in this platform's context is really "a deploy of whichever services changed," not a versioned, all-services-together release train.

## Recommended release-plan discipline as the platform matures

Once the platform moves toward handling real customer money at scale (see [`../09-qa/155-release-acceptance-criteria.md`](../09-qa/155-release-acceptance-criteria.md) for the proposed launch gate), consider whether a more formal release-planning cadence is warranted — e.g., batching related changes into a named release with its own changelog and rollback plan, rather than continuous per-merge deploys, specifically for changes touching the ledger, credit engine, or Shariah contracts, given how much financial/compliance risk concentrates in those areas.

## Related documents

[`43-product-roadmap.md`](43-product-roadmap.md), [`../10-devops/34-deployment-process.md`](../10-devops/34-deployment-process.md), [`../09-qa/155-release-acceptance-criteria.md`](../09-qa/155-release-acceptance-criteria.md).
