# Project status

Updated 2026-10-20. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Phase 3 — incremental manual-first MVP implementation. The isolated calculator/parser, bounded local authoritative-draft, integrated invitation/session lifecycle, and bounded same-origin transport adapter slices are internally accepted and merged into `main`; the complete live application is not yet implemented.
- **Completed:** Phase 0 research/skills; feasible Phase 1; revised Phase 2 independent challenge and browser/SQLite probes; Phase 3 calculator and local authority with tests and independent reviews; repository CI (PR #2), namespace refactor (PR #3), integrated invitation/session lifecycle (PR #4), and bounded same-origin transport adapter (PR #5) merged.
- **Active objective:** Frontend client integration and meal lifecycle UI workflows (receipt review, diner item claiming, invitation landing) operating against the same-origin transport API.
- **Blocking gates:** live application use needs front-end client integration, renewal/recovery and operational validation. Local atomic access/calculation/persistence, invitation lifecycle, transport boundaries, and independent security gates pass within the bounded authority contract. Policy-dependent settlement/image/export features need unresolved human preferences before activation. Public release also needs backup/restore, device and operational validation.
- **Nonblocking risks for this phase:** modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local manual-first validation.
- **Architecture/stack:** Path C; Python standard-library `settletable` package with WSGI transport adapter (`SettleTableApp`) and single-host SQLite local authority in WAL mode. The source move preserves the historical `tabwise-apportion-v1` deterministic contract and all existing security/canonical domains. Web framework/hosting remain undecided; no external framework dependency.
- **Next work:** design and implement front-end client interface for meal drafts, participant claims, and invitation landing against `/api/` endpoints.

## Repository checkpoint

- Repository: [KAIYI7/settle-table](https://github.com/KAIYI7/settle-table); project name SettleTable. Local filesystem directory unchanged.
- Baseline commit: [`69895457d9e3524c90df24f3a21c284ea70cef6c`](https://github.com/KAIYI7/settle-table/commit/69895457d9e3524c90df24f3a21c284ea70cef6c), `chore: establish SettleTable project baseline`.
- Annotated checkpoint: [`phase2-accepted`](https://github.com/KAIYI7/settle-table/tree/phase2-accepted); tag object `42acff45556c3a0ed6fd85ab751cfdba25791023`.
- Verified 2026-10-17: remote `main` and peeled tag target both equal the baseline SHA; local tag object type is `tag`. [Audit](research/publishing/prepublish-audit.md), [remote verification](research/publishing/checkpoint.json).
- This status update follows the baseline commit; later documentation/work commits may advance `main` while the checkpoint tag remains fixed at the accepted baseline.

**Accepted slice evidence:** [interface](docs/calculation-interface.md); 15 test methods pass in the main agent's run; [66 independent spec checks](research/phase-3/spec-review.md) and [11 engineering probe groups](research/phase-3/engineering-review.md) pass. No material review finding remains for the bounded calculation contract. These counts are functional checks, not statistical accuracy or coverage estimates.

## Accepted authority checkpoint

- PR #1 reviewed head: `59cba5feb25423ebd43ebee17b7666d84f83d584`; premerge main: `7db4ef155149526f6c646158814d1851b5fdb21b`. Both matched actual remote refs and GitHub metadata before merge.
- Merge commit: [`af7ba147642b8b8e9a5aee973a95c59d46c38b9a`](https://github.com/KAIYI7/settle-table/commit/af7ba147642b8b8e9a5aee973a95c59d46c38b9a). Its two parents are exactly premerge main and reviewed head, preserving the small implementation history. The merged tree equals the reviewed head.
- Annotated checkpoint: [`authority-v1-accepted`](https://github.com/KAIYI7/settle-table/tree/authority-v1-accepted); tag object `389eb52462cfe0a17a4456504a41214956ae15bc`. Actual remote main and peeled tag target verified 2026-10-17 at the merge SHA; local object type is `tag`. Subsequent documentation/foundation commits may advance main without moving this checkpoint.
- [Local authority evidence](research/phase-3/authority-acceptance.md): 60 full-suite methods pass, with independent source/spec and security review and material findings resolved. This records bounded local acceptance, not Internet identity or full-product readiness.

## Accepted invitation and session lifecycle checkpoint (PR #4)

- PR #4 reviewed head: `0f63ecd00ea71c5c667c70ef750012f594ae3add`; premerge main: `7253cf9e2888802d00fb037f2a1fbcd517868e73`.
- Merge commit: [`75a3511982091d6c49f97a29dbf7a9fcb6de0205`](https://github.com/KAIYI7/settle-table/commit/75a3511982091d6c49f97a29dbf7a9fcb6de0205). Merged autonomously under orchestrator governance policy.
- Verified evidence: 79 full-suite methods pass locally; [independent security review](research/phase-3/invitation-security-review.md) records unconditional PASS/GO across all gates and all 5 post-implementation review findings; hosted GitHub Actions run [39404379865](https://github.com/KAIYI7/settle-table/actions/runs/39404379865) completed successfully on the exact PR head SHA.
- [Invitation acceptance evidence](research/phase-3/invitation-acceptance.md) and [invitation specification](.scratch/invitation-lifecycle/SPEC.md). Single SQLite transaction boundary preserved; zero bearer secret persistence; deterministic math unchanged.

## Accepted same-origin transport adapter checkpoint (PR #5)

- PR #5 reviewed head: `1f1fb789f5bc5cf93b04c0ec6063b5f63969a9b2`; premerge main: `52c6f731cbb2818610eb6793f0b2f15e81d773ee`.
- Merge commit: [`43b827f80db4236a282914197363eb077cb50cb0`](https://github.com/KAIYI7/settle-table/commit/43b827f80db4236a282914197363eb077cb50cb0). Merged autonomously under orchestrator governance policy.
- Verified evidence: 101 full-suite methods pass locally in 66.240s; [independent architecture challenge](research/phase-3/transport-adapter-challenge.md) and [post-implementation security review](research/phase-3/transport-adapter-review.md) record PASS/GO across all gates and all 6 remediations; hosted GitHub Actions run [39408626484](https://github.com/KAIYI7/settle-table/actions/runs/39408626484) completed successfully on the exact PR head SHA.
- [Transport specification](.scratch/transport-adapter/SPEC.md) and [transport implementation](settletable/transport.py). Wire limits (header 4 KB/16 KB, body 1 MB, depth 10, int 19 digits), CSRF defense (`X-SettleTable-Action: 1`, strict origin check), unauthenticated landing isolation (`Authority.inspect_invitation`), and host-only secure cookies enforced.

## Repository foundation

- CI merge: `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa` (PR #2). `.github/workflows/python-tests.yml` runs the entire suite on PRs targeting main and pushes to main, with pinned official actions, read-only token permissions and no supplied secrets/caches/artifacts. The owner confirms included minutes remain and no valid payment method is attached; no billing setting or paid usage was enabled. [CI research/review](research/foundation/README.md).
- Namespace merge: `91b824f395d062a994056e905f475fe83f52b3a8` (PR #3). Both production files moved from `tabwise` to `settletable` with identical bytes; no hash-domain, schema or canonical/replay change. Old-package-created SQLite compatibility passes; the coordinator's renamed full suite passes60 methods in73.078s. [Refactor evidence](research/foundation/package-refactor.md).
- Hosted PR checks ran all60 tests successfully for both CI and renamed integration; main push checks also run the full suite. Exact observed runs and limits are in [foundation evidence](research/foundation/README.md). Current checkpoint tags remain fixed while main advances.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).
