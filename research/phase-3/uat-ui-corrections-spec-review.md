# Independent specification review — UAT UI corrections

Date: 2026-10-29 (Asia/Kuala Lumpur). Reviewer: independent `spec_review` subagent, not the implementation author.

Reviewed base `76187b1fcb5e928e8f6cc78b3afc1c02477501ef` through head `3b24faa4bdd5a705854b4c31b2fa58d36597e69e` using the actual three-dot diff and final surrounding source. Sources: owner's two-correction request, [bounded specification](../../.scratch/uat-ui-corrections/SPEC.md), original local independent UAT report, and [governance](../../docs/agents/governance.md).

**Disposition: PASS. Zero specification findings.** No missing/partial requirement, incorrect implementation, or material scope expansion identified.

- “Use the existing rational formatter”: `renderOrganizerSection` now invokes the existing `formatRat` at `settletable/static/app.js:1234`. The browser regression asserts the actual Receipt & Charges rows for `(x1)`, `(x2)`, `(x3)`, `(x½)` and `(x⅓)`, before sealing, after sealing and after reload. It also checks receipt equality and displayed line amounts.
- “Make the available action clear before clicking”: unassigned pills have native `disabled` semantics when no whole portion remains, subdued styling, an associated visible explanation, and the unchanged Details / Split button. Applying this to fractional remainder follows the existing one-portion action's capacity requirement. Allocated diner pills remain edit controls.
- “Preserve existing allocations, organizer authorization and revision conflict behavior”: regression verifies blocked clicks preserve the snapshot, desktop/mobile editors remain usable, removal frees capacity, reassignment persists after reload. Final source leaves organizer-only handler binding, command revision fields, conflict recovery and backend authorization untouched. Existing transport tests explicitly cover forbidden diner assignment and stale item revisions.
- Exclusions respected: the changed-file list contains only the specification, frontend display/styles and browser tests. Financial engine, persistence, finalization and native confirmation implementation are untouched. The test uses a new temporary SQLite database, isolated browser profiles and task-owned processes; it refuses occupied app/debugging ports.

Independently executed `node tools/e2e_browser_test.mjs --port 18879 --ui-regressions-only` with task-local `ARTIFACT_DIR`: **PASS**, exit 0, 3.23 seconds. Inspected retained receipt and mobile-capacity screenshots. Log: `.scratch/uat-ui-corrections/independent-browser-tests.log`; captures: `.scratch/uat-ui-corrections/independent-evidence/`.

This is focused engineering regression evidence. It does not complete the original independent UAT or validate its untested finalization, export, collaboration, mobile accessibility or other blocked scenarios. Hosted CI and merge authorization remain the orchestrator's gates.
