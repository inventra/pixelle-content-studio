# Pixelle Content Studio MVP Brief

This repository is now the base for a new product: **Pixelle Content Studio**.

## Product boundary
- This product must stay **independent from LazyOffice**.
- Do not reuse LazyOffice routes, app code, or data models.
- This repo should evolve as a standalone content workflow + short-video studio.

## Desired workflow
1. Daily AI news is ingested.
2. The system shows candidate topics.
3. Kevin selects which topic/project should become content.
4. The system generates:
   - Substack draft
   - Facebook draft
   - LINE draft
5. After reviewing the drafts, Kevin can approve the topic for short video.
6. Then the system generates:
   - short video script
   - storyboard
   - final video render task via existing Pixelle-Video capabilities
7. Video publishing remains manual.

## MVP scope
Implement the product skeleton for:
- Topics page
- Content Studio page
- Video Decision page
- Assets / Render History page
- Topics API
- Drafts API
- Storyboards API
- simple local persistence
- bridge into existing Pixelle video generation task flow

## Planning references
Use these local plans as the source of truth:
- `/Users/wuwenkai/.hermes/plans/2026-05-03_123511-pixelle-content-studio-plan.md`
- `/Users/wuwenkai/.hermes/plans/2026-05-03_124553-pixelle-content-studio-mvp-breakdown.md`

## Key constraints
- Preserve existing Pixelle-Video video generation features where possible.
- Build the new orchestration layer on top.
- Keep the UX copy-friendly and review-friendly.
- Add clear approval gates before video render.
- Prefer incremental, testable implementation.

## Deliverable expectation
- Working local MVP
- Basic tests for new routers/services
- Clear run instructions
- Commit changes locally in the repo when implementation is complete
