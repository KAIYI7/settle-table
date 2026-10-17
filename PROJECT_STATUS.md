# Project status

Updated 2026-10-17. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Phase 3 — incremental manual-first MVP implementation. The isolated financial calculation/parser slice is accepted; the complete live application is not yet implemented.
- **Completed:** Phase 0 reference/licensing/skills research; feasible Phase 1; revised Phase 2 independent challenge,30-assertion browser probe,20-check SQLite probe, Notion contract/specification; Phase 3 calculation slice with tests and two independent reviews. Completion does not imply every production capability is validated.
- **Active objective:** resume the authoritative manual-entry draft specification using the accepted calculator: durable command replay, permissions, revisions, human review and atomic reconciliation. The publication prerequisite is complete and remotely verified.
- **Blocking gates:** production live authority needs real identity/revocation, atomic access/calculation/persistence integration and independent security review. Policy-dependent settlement/image/export features require unresolved human preferences before activation. Public release also needs backup/restore, device checks and operational validation.
- **Nonblocking risks for this phase:** modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local manual-first validation.
- **Architecture/stack:** Path C; Python standard-library calculation core selected. Browser/shared authority with SQLite/FastAPI candidates is staged, not a final web stack or hosting choice. Local/self-hosted extraction proposals and optional downstream Notion copy remain required directions. No framework-specific skill installed.
- **Next work:** bound and independently challenge the next command/session specification before implementation; then build/test small behaviors and review integrated authority. Human escalation remains required for spend, exposure, credentials, private data, destructive/irreversible external actions, unclear licensing and genuine product-policy preferences.

## Repository checkpoint

- Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table); project name SettleTable. Local filesystem directory unchanged.
- Baseline commit: [`69895457d9e3524c90df24f3a21c284ea70cef6c`](https://github.com/KAIYI7/settle-table/commit/69895457d9e3524c90df24f3a21c284ea70cef6c), `chore: establish SettleTable project baseline`.
- Annotated checkpoint: [`phase2-accepted`](https://github.com/KAIYI7/settle-table/tree/phase2-accepted); tag object `42acff45556c3a0ed6fd85ab751cfdba25791023`.
- Verified2026-10-17: remote `main` and peeled tag target both equal the baseline SHA; local tag object type is `tag`. [Audit](research/publishing/prepublish-audit.md), [remote verification](research/publishing/checkpoint.json).
- This status update follows the baseline commit; later documentation/work commits may advance `main` while the checkpoint tag remains fixed at the accepted baseline.

**Accepted slice evidence:** [interface](docs/calculation-interface.md);15 test methods pass in the main agent's run; [66 independent spec checks](research/phase-3/spec-review.md) and [11 engineering probe groups](research/phase-3/engineering-review.md) pass. No material review finding remains for the bounded calculation contract. These counts are functional checks, not statistical accuracy or coverage estimates.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).
