# Sprint Planning Process

**Status:** STABLE — sourced directly from `docs/MASTER_PLAN.md`'s sprint structure (S01–S22), which functions as the platform's sprint plan even though it wasn't previously documented as a standalone "process."

## Sprint structure

Each sprint in `docs/MASTER_PLAN.md` is scoped as one or more "iterations," each with an explicit file list (exactly which files to create/modify) and a push checklist (lint/type-check/tests/migration/Docker-build/health-check). This is an unusually concrete sprint-planning format — most sprint plans describe *outcomes*; this one describes the *literal files a session should touch*, which is specifically well-suited to AI-assisted development sessions (the plan explicitly says as much: "paste this file into every new AI chat session").

## Recommended session sequence (from `docs/MASTER_PLAN.md`)

The plan includes a 20-row "Recommended Session Sequence" table mapping each sprint/iteration to its key reference spec file — this is effectively the sprint backlog in execution order, and should be the first thing consulted when picking up new work, rather than re-deriving priority from scratch.

## How this should evolve now that the audit exists

Given `docs/PRODUCTION_GAPS_REPORT.md` reveals the original sprint sequence's "done" markers don't always mean functionally complete (e.g., Phase 2's checkout agent sprint is marked done in the component table despite the checkout form-filler being an incomplete stub), **the sprint planning process going forward should incorporate gap-closure work as its own tracked sprint category**, not just new-feature sprints — see [`43-product-roadmap.md`](43-product-roadmap.md)'s recommended resequencing (close Priority 1 gaps before Phase 4 work) for how this should reshape near-term sprint planning specifically.

## Related documents

[`43-product-roadmap.md`](43-product-roadmap.md), [`203-release-plan.md`](203-release-plan.md), `docs/MASTER_PLAN.md`.
