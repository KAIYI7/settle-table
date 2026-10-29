# Independent standards/source review — UAT UI corrections

Date: 2026-10-29 (Asia/Kuala Lumpur). Reviewer: independent `standards_review` subagent; no implementation authorship.

**Disposition: PASS. Zero documented-standard violations; zero actionable baseline smells.** Integration authority remains with the orchestrator, subject to the separate specification review and hosted CI gate.

Reviewed exact head: `3b24faa4bdd5a705854b4c31b2fa58d36597e69e` against base `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`. Commit list: `3b24faa fix: clarify receipt quantities and unavailable quick assignments`. Inspected `git diff <base>...HEAD`, all four changed files, and surrounding formatter, allocation renderers/handlers, transport calls and authoritative input validation.

## Documented standards

Sources: `AGENTS.md`, `docs/agents/governance.md`, `.scratch/uat-ui-corrections/SPEC.md`, and the project code-review skill. No CONTRIBUTING or CODING_STANDARDS document was found.

- Receipt review reuses `formatRat`; it does not change quantity or financial data. Authoritative rational values are numeric, and identifier validation excludes HTML delimiters. Participant names remain escaped in both visible text and new title attributes.
- Native `disabled` conveys unavailable actions and blocks ordinary activation. An associated visible explanation identifies Details / Split; allocated pills and the existing Details button remain enabled. Disabled pills no longer receive the available hover treatment.
- Availability uses the same whole-portion threshold as the unchanged quick-assignment handler. Organizer-only rendering/handlers, item/financial revision submission, conflict recovery, and backend capacity enforcement are untouched.
- Regression fixtures enter through real transport and inspect the actual receipt DOM before/after sealing and reload. Harness data/profiles are temporary; occupied ports are refused before spawning processes. Cleanup retains process handles created by the harness and does not target the unknown UAT listener/database.

## Smell baseline

No actionable new Fowler-baseline smell. The added scenario is bounded to this correction; extracting a new browser framework or refactoring existing allocation code is unnecessary for this scope.

## Evidence and limits

Independently ran `node --check` on both changed JavaScript files and `git diff --check <base>...HEAD`: PASS. Inspected coordinator logs recording 213 Python tests and 12 browser stages passing; did not independently rerun browsers. Hosted CI and the original incomplete independent UAT remain separate gates. This review does not close any untested UAT scenario.
