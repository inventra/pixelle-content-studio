# Pixelle Content Studio — Phase 2 Brief

Continue from the current MVP skeleton in this repository.

## Goals for this phase

### A) Daily news auto-ingest into Topics
Implement a practical first version of automatic topic ingestion from the existing Hermes/Obsidian daily briefing workflow.

Preferred source order:
1. Obsidian daily note under the user's vault
2. Existing repurpose/content note if useful
3. Fallback sample/manual source if the daily note is missing

Assumptions:
- Obsidian vault path: `/Users/wuwenkai/Projects/sales-wiki`
- Daily note pattern: `meetings/YYYY-MM-DD-daily-project-ai-sync.md`

Desired behavior:
- A service reads today's daily note
- It extracts at least the morning/evening topic blocks into topic candidates
- It can ingest those candidates into the Content Studio topic store
- Add a simple trigger path for this, such as API endpoint and/or UI button on Topics page
- Keep this product independent from LazyOffice

### B) Toulan Office draft style
Adjust draft generation so generated content feels like 偷懶辦公室 instead of a boring news digest.

Desired style:
- Not just a list of news items
- Explain why the tool/topic matters
- Explain practical use cases
- Explain what this helps people do
- Include actionable prompt/workflow guidance when relevant
- Tone: practical, insightful, not overhyped, not robotic

For draft generation, make Substack / Facebook / LINE outputs reflect that tone appropriately.

## Constraints
- Preserve current MVP structure and tests
- Add or update tests for the new behavior
- Run relevant tests
- Commit changes locally when done

## Final response requirements
When finished, report:
1. What files changed
2. What commands/tests were run
3. Any remaining limitations
