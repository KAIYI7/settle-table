# Project status

Updated 2026-10-17. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Phase 3 — incremental manual-first MVP implementation. The isolated financial calculation/parser slice is accepted; the complete live application is not yet implemented.
- **Completed:** Phase 0 reference/licensing/skills research; feasible Phase 1; revised Phase 2 independent challenge,30-assertion browser probe,20-check SQLite probe, Notion contract/specification; Phase 3 calculation slice with tests and two independent reviews. Completion does not imply every production capability is validated.
- **Active objective:** establish the clean GitHub baseline at `https://github.com/KAIYI7/settle-table`, with `main` and annotated `phase2-accepted` verified remotely. Publication audit and checkpoint must finish before any next-slice implementation.
- **Blocking gates:** production live authority needs real identity/revocation, atomic access/calculation/persistence integration and independent security review. Policy-dependent settlement/image/export features require unresolved human preferences before activation. Public release also needs backup/restore, device checks and operational validation.
- **Nonblocking risks for this phase:** modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local manual-first validation.
- **Architecture/stack:** Path C; Python standard-library calculation core selected. Browser/shared authority with SQLite/FastAPI candidates is staged, not a final web stack or hosting choice. Local/self-hosted extraction proposals and optional downstream Notion copy remain required directions. No framework-specific skill installed.
- **Next work after verified checkpoint:** resume the authoritative manual-entry draft objective: command/session specification, durable replay, permissions, revisions, review and atomic reconciliation. Human escalation remains required for spend, exposure, credentials, private data, destructive/irreversible external actions, unclear licensing and genuine product-policy preferences.

**Accepted slice evidence:** [interface](docs/calculation-interface.md);15 test methods pass in the main agent's run; [66 independent spec checks](research/phase-3/spec-review.md) and [11 engineering probe groups](research/phase-3/engineering-review.md) pass. No material review finding remains for the bounded calculation contract. These counts are functional checks, not statistical accuracy or coverage estimates.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).
