# Project status

Updated 2026-10-17. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Phase 3 — incremental manual-first MVP implementation. The isolated calculator/parser and bounded local authoritative-draft slices are internally accepted; the complete live application is not yet implemented.
- **Completed:** Phase 0 research/skills; feasible Phase 1; revised Phase 2 independent challenge and browser/SQLite probes; Phase 3 calculator and local authority with tests and independent reviews. Completion does not imply every production capability is validated.
- **Active objective:** repository foundation after merging [PR #1](https://github.com/KAIYI7/settle-table/pull/1): minimal secret-free full-suite CI, package-name evaluation/refactor, then bounded transport/identity/invitation planning. The user reports external review found no merge-blocking finding for the local scope; the merge and annotated checkpoint below are remotely verified.
- **Blocking gates:** live application use needs real Internet identity/invitations, renewal/recovery and transport-integrated access controls. Local atomic access/calculation/persistence and independent security gates pass only within the bounded authority contract. Policy-dependent settlement/image/export features need unresolved human preferences before activation. Public release also needs backup/restore, device and operational validation.
- **Nonblocking risks for this phase:** modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local manual-first validation.
- **Architecture/stack:** Path C; Python standard-library calculation and single-host SQLite local authority selected. Web framework/hosting remain undecided; no listener or frontend is implemented. Local/self-hosted extraction and optional downstream Notion remain required directions. No framework-specific skill installed.
- **Next work:** finish independently reviewable foundation changes; hosted CI activation requires verified available included usage with no paid-overage exposure. Resume planning for identity/invitation lifecycle and transport access controls before OCR, Notion or UI. Human escalation remains required for spend, exposure, credentials, private data, destructive/irreversible external actions, unclear licensing and genuine product-policy preferences.

## Repository checkpoint

- Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table); project name SettleTable. Local filesystem directory unchanged.
- Baseline commit: [`69895457d9e3524c90df24f3a21c284ea70cef6c`](https://github.com/KAIYI7/settle-table/commit/69895457d9e3524c90df24f3a21c284ea70cef6c), `chore: establish SettleTable project baseline`.
- Annotated checkpoint: [`phase2-accepted`](https://github.com/KAIYI7/settle-table/tree/phase2-accepted); tag object `42acff45556c3a0ed6fd85ab751cfdba25791023`.
- Verified2026-10-17: remote `main` and peeled tag target both equal the baseline SHA; local tag object type is `tag`. [Audit](research/publishing/prepublish-audit.md), [remote verification](research/publishing/checkpoint.json).
- This status update follows the baseline commit; later documentation/work commits may advance `main` while the checkpoint tag remains fixed at the accepted baseline.

**Accepted slice evidence:** [interface](docs/calculation-interface.md);15 test methods pass in the main agent's run; [66 independent spec checks](research/phase-3/spec-review.md) and [11 engineering probe groups](research/phase-3/engineering-review.md) pass. No material review finding remains for the bounded calculation contract. These counts are functional checks, not statistical accuracy or coverage estimates.

## Accepted authority checkpoint

- PR #1 reviewed head: `59cba5feb25423ebd43ebee17b7666d84f83d584`; premerge main: `7db4ef155149526f6c646158814d1851b5fdb21b`. Both matched actual remote refs and GitHub metadata before merge.
- Merge commit: [`af7ba147642b8b8e9a5aee973a95c59d46c38b9a`](https://github.com/KAIYI7/settle-table/commit/af7ba147642b8b8e9a5aee973a95c59d46c38b9a). Its two parents are exactly premerge main and reviewed head, preserving the small implementation history. The merged tree equals the reviewed head.
- Annotated checkpoint: [`authority-v1-accepted`](https://github.com/KAIYI7/settle-table/tree/authority-v1-accepted); tag object `389eb52462cfe0a17a4456504a41214956ae15bc`. Actual remote main and peeled tag target verified2026-10-17 at the merge SHA; local object type is `tag`. Subsequent documentation/foundation commits may advance main without moving this checkpoint.
- [Local authority evidence](research/phase-3/authority-acceptance.md):60 full-suite methods pass, with independent source/spec and security review and material findings resolved. This records bounded local acceptance, not Internet identity or full-product readiness.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).
