# Project status

Updated 2026-10-21. Project: **SettleTable**. Authority: [orchestrator governance](docs/agents/governance.md). Decisions: [transition ledger](docs/agents/phase-transitions.md).

- **Current phase:** Phase 3 — incremental manual-first MVP implementation, bounded local OCR pipeline, and optional asynchronous Notion reporting. The isolated calculator/parser, bounded local authoritative-draft, integrated invitation/session lifecycle, bounded same-origin transport adapter, transport hardening, same-origin browser MVP, browser E2E defect fixes, cross-platform CI browser test infrastructure, bounded local OCR pipeline, and bounded optional asynchronous Notion reporting slices are internally accepted and merged into `main`.
- **Completed:** Phase 0 research/skills; feasible Phase 1; revised Phase 2 independent challenge and browser/SQLite probes; Phase 3 calculator and local authority with tests and independent reviews; repository CI (PR #2), namespace refactor (PR #3), integrated invitation/session lifecycle (PR #4), bounded same-origin transport adapter (PR #5), transport-boundary hardening (PR #6), same-origin browser MVP (PR #7), browser MVP E2E defect fixes (PR #8), cross-platform browser test infrastructure with CI automation (PR #9), bounded local OCR pipeline with Malaysian SST parser (PR #10), and bounded optional asynchronous Notion reporting pipeline (PR #11) merged.
- **Active objective:** Phase 3 consolidation, operational review, and demonstration handover.
- **Blocking gates:** live Internet production release needs operational backup/restore, external deployment infrastructure, device validation, and privacy boundary approval. Local atomic access/calculation/persistence, invitation lifecycle, transport boundaries, browser UI, local OCR processing, optional Notion reporting, and independent security gates pass within the bounded authority contract. Policy-dependent settlement/image/export features need unresolved human preferences before activation.
- **Nonblocking risks for this phase:** modern held-out Malaysian OCR accuracy, real-phone camera/offline performance, original dataset rights, raw authenticated Notion REST/actual workspace limits, real hosting costs. These block relevant release/integration claims, not local manual-first validation.
- **Architecture/stack:** Path C; Python standard-library `settletable` package with WSGI transport adapter (`SettleTableApp`), single-host SQLite local authority in WAL mode, RapidOCR local CPU ONNX engine, optional decoupled Notion exporter (`settletable.notion`), and zero-dependency vanilla ES2022 / HTML / CSS browser frontend. The source move preserves the historical `tabwise-apportion-v1` deterministic contract and all existing security/canonical domains.
- **Next work:** Phase 3 consolidation, operational review, and demonstration handover.

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
- Merge commit: [`43b827f486ffa06d532c37d89826ccf2aa50051f`](https://github.com/KAIYI7/settle-table/commit/43b827f486ffa06d532c37d89826ccf2aa50051f). Merged autonomously under orchestrator governance policy (GitHub PR #5 closed upon direct merge to main).
- Verified evidence: 101 full-suite methods pass locally in 66.240s; [independent architecture challenge](research/phase-3/transport-adapter-challenge.md) and [post-implementation security review](research/phase-3/transport-adapter-review.md) record PASS/GO across all gates and all 6 remediations; hosted GitHub Actions run [39408626484](https://github.com/KAIYI7/settle-table/actions/runs/39408626484) completed successfully on the exact PR head SHA.
- [Transport specification](.scratch/transport-adapter/SPEC.md) and [transport implementation](settletable/transport.py). Wire limits (header 4 KB/16 KB, body 1 MB, depth 10, int 19 digits), CSRF defense (`X-SettleTable-Action: 1`, strict origin check), unauthenticated landing isolation (`Authority.inspect_invitation`), and host-only secure cookies enforced.

## Accepted transport hardening checkpoint (PR #6)

- PR #6 reviewed head: `65ae4bd7987fc5208f8705b6197171ef0728c057`; premerge main: `b0ca641659424751f727c9d9685121b6d9e03d4d`.
- Merge commit: [`e7a8a82918353d82188746c0d7b19fec499b2698`](https://github.com/KAIYI7/settle-table/commit/e7a8a82918353d82188746c0d7b19fec499b2698). Merged autonomously under orchestrator governance policy (GitHub PR #6 closed upon direct merge to main).
- Verified evidence: 104 full-suite methods pass locally in 63.364s; [independent security review](research/phase-3/transport-hardening-review.md) records unconditional PASS/GO across all 5 audit gates; hosted GitHub Actions run [39420125202](https://github.com/KAIYI7/settle-table/actions/runs/39420125202) completed successfully on the exact PR head SHA.
- [Deployment boundary document](docs/deployment-boundary.md) establishes Tier 1 ingress stream limits vs Tier 2 WSGI defense-in-depth; loopback bootstrap rejects proxy headers (`X-Forwarded-*`); provisioning returns strictly organizer credentials; session rotation omits raw bearer tokens from JSON in cookie contexts.

## Accepted same-origin browser MVP checkpoint (PR #7)

- PR #7 reviewed head: `cd4973c1cd73dae8f6ebe8e97640e04604ae16f6`; premerge main: `b5900f892cb86fc50a1bb73507d9d7e50275525b`.
- Merge commit: [`67f7190638696f8592cd49fa489b5f12f64b49e1`](https://github.com/KAIYI7/settle-table/commit/67f7190638696f8592cd49fa489b5f12f64b49e1). Merged autonomously under orchestrator governance policy (GitHub PR #7 closed upon direct merge to main).
- Verified evidence: 109 full-suite methods pass locally in 63.725s; [independent architecture challenge](research/phase-3/browser-mvp-challenge.md) and [post-implementation review](research/phase-3/browser-mvp-review.md) record PASS/GO across all 6 audit gates with all 4 remediations verified; hosted GitHub Actions run [39423753289](https://github.com/KAIYI7/settle-table/actions/runs/39423753289) completed successfully on the exact final PR head SHA.
- [Browser MVP specification](.scratch/browser-mvp/SPEC.md) and frontend implementation (`settletable/static/`). Zero external CDNs/fonts, strict Content-Security-Policy, DOM XSS immunity (`escapeHtml()`), $44\text{px}$ touch targets, human receipt confirmation digest binding, HTTP 409 Conflict handling, and deterministic cent-conserving calculation breakdown.

## Accepted browser MVP E2E fixes and real browser validation checkpoint (PR #8)

- PR #8 reviewed head: `172d56f8f5337fc9a518fb1935c754dc9335e76a`; premerge main: `c15a07204f447738bc0cb9d75e47854cf468249a`.
- Merge commit: [`a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc`](https://github.com/KAIYI7/settle-table/commit/a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc). Merged autonomously under orchestrator governance policy (GitHub PR #8 closed upon direct merge to main).
- Verified evidence: 113 full-suite methods pass locally in 60.448s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent security and code review](research/phase-3/browser-e2e-fixes-review.md) records unconditional PASS/GO across all 6 audit gates; hosted GitHub Actions run [39442110445](https://github.com/KAIYI7/settle-table/actions/runs/39442110445) completed successfully on the exact final PR head SHA.
- Key fixes: receipt-entry `ReplaceReceipt` contract supplies authoritative `subtotal_sen` and `total_sen` without fabricating zero amounts; `renderFinalizedCalculation` maps participant totals directly from `calculation.consumption` records; mutation handlers decouple forced snapshot refresh and sequence numbering guards against out-of-order poll clobbering; strict integer MYR input parsing rejects malformed strings and float drift.

## Accepted cross-platform browser test infrastructure & CI automation checkpoint (PR #9)

- PR #9 reviewed head: `5a879c5ed5ef7c95939da0b4fd98e2516d086e1b`; premerge main: `49f966c5c007c089cbb6f183cf53549cf06aa7c2`.
- Merge commit: [`1b693f56cb3cf3df0e7cb84727cccaf594d1e769`](https://github.com/KAIYI7/settle-table/commit/1b693f56cb3cf3df0e7cb84727cccaf594d1e769). Merged autonomously under orchestrator governance policy (GitHub PR #9 closed upon direct merge to main).
- Verified evidence: 113 full-suite methods pass locally in 47.362s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent security and code review](research/phase-3/test-infra-review.md) records unconditional PASS/GO across all 5 audit gates; hosted GitHub Actions run [39508712147](https://github.com/KAIYI7/settle-table/actions/runs/39508712147) completed successfully on the exact final PR head SHA in `ubuntu-24.04`, validating both Python tests and real browser E2E journeys in CI.
- Key improvements: dynamic cross-platform discovery for Chrome and Python binaries eliminating hardcoded paths; invitation bearer token redaction in console logs (`/invite/[REDACTED]`); container flags (`--headless=new`, `--no-sandbox`, `--disable-dev-shm-usage`, `--disable-gpu`); zero-extra-spend CI integration without paid test cloud services.

## Accepted bounded local OCR pipeline and Malaysian SST parser checkpoint (PR #10)

- PR #10 reviewed head: `b6dc100d04961917f93539fc4107127e9fe558d4`; premerge main: `0847e51f0436894371fa4fce23be2a9d2bf58054`.
- Merge commit: [`3455a57223d1e1582d1c3c8f8185186484364074`](https://github.com/KAIYI7/settle-table/commit/3455a57223d1e1582d1c3c8f8185186484364074). Merged autonomously under orchestrator governance policy (GitHub PR #10 closed upon direct merge to main).
- Verified evidence: 136 full-suite methods pass locally in 71.784s; 8/8 automated real-browser CDP test stages pass in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent architecture challenge](research/phase-3/ocr-architecture-challenge.md) and [post-implementation security review](research/phase-3/ocr-implementation-review.md) record PASS across all 6 audit gates with all remediations verified; hosted GitHub Actions run [39512879579](https://github.com/KAIYI7/settle-table/actions/runs/39512879579) completed successfully on the exact final PR head SHA in `ubuntu-24.04`.
- Key capabilities: local CPU inference via RapidOCR/ONNX Runtime with zero cloud vision fallback; route-aware binary ingress on `POST /api/meals/{meal_id}/ocr/extract` bypassing JSON parsing; raw binary header dimension checks protecting against decompression bombs ($\le 4096 \times 4096$, $\le 16\text{MP}$); strict wire MIME type vs magic byte verification; organizer authorization requirement (403 for diners, 401 unauthenticated); zero database mutation on advisory extraction; Malaysian dining receipt domain parsing (Wan Sheng tax-inclusive rule preserving calculation subtotal invariants, Kechara rule preventing fact invention, statutory SST/service charges, BNM $\pm 1, \pm 2$ sen rounding); mandatory UI human receipt verification and cryptographic digest sealing before finalization; deterministic CI test replay using token fixtures without native ONNX wheels.

## Accepted bounded optional asynchronous Notion reporting checkpoint (PR #11)

- PR #11 reviewed head: `8a83ba2287ad27764a51147bd594e4b4c4eba966`; premerge main: `a06142ce9ec60a927fa1e1ec074d0089a8183141`.
- Merge commit: [`d34ff75caf3047f5a8515d0b3503e3a3948871ae`](https://github.com/KAIYI7/settle-table/commit/d34ff75caf3047f5a8515d0b3503e3a3948871ae). Merged autonomously under orchestrator governance policy (GitHub PR #11 closed upon direct merge to main).
- Verified evidence: 150 full-suite methods pass locally in 62.383s; 9/9 automated real-browser CDP test stages pass in 3.4s via Headless Chrome (`tools/e2e_browser_test.mjs`); [independent architecture challenge](research/phase-3/notion-architecture-challenge.md) and [post-implementation security review](research/phase-3/notion-implementation-review.md) record unconditional GO/PASS across all 6 audit gates with all 7 remediations verified; hosted GitHub Actions run [39515609945](https://github.com/KAIYI7/settle-table/actions/runs/39515609945) completed successfully on the exact final PR head SHA in `ubuntu-24.04`.
- Key capabilities:
  1. **Strict Decoupling & Fault Isolation**: Live meal collaboration, item claiming, receipt review, and finalization execute 100% offline or air-gapped without Notion. Notion export failures leave SQLite meal state, claims, and calculations completely intact with zero database rollbacks.
  2. **Secret Hygiene & Token Redaction**: Notion API tokens (`secret_...` and `ntn_...`) are strictly excluded from SQLite persistence. Wire logs (`transport.redact_log_string`), error strings, and exception handlers scrub integration tokens to prevent leakage in server output or HTTP error bodies.
  3. **One-Way Canonical Projection & Financial Invariance**: Apportionment exported to Notion is mapped directly from authoritative `calculation.consumption` integer sen amounts. Notion formulas, rollups, or calculations are strictly zero; money formatting uses integer division without floating-point drift.
  4. **Block-Quota Efficiency (Compact Default)**: Generates $\le 40$ blocks per meal (1 callout + 2 headings + 2 tables + rows + divider + audit paragraph), yielding $>70\%$ block savings over relational multi-page designs and protecting Free tier workspace lifetime block quotas (1,000 blocks).
  5. **REST Schema Constraints**: Page-parent export strictly limits properties to `title` (per Notion REST constraint for non-database parents) while placing financial metadata inside the top Callout block; table block dimensions strictly match row cell arrays.
  6. **Concurrency & Idempotency State Machine**: SQLite tracking table `notion_exports` maintains `(meal_id, finalized_revision)` through `in_progress` -> `completed` state machine, rejecting duplicate concurrent clicks with 409 `export_in_progress` or 409 `already_exported` while permitting clean recovery on failure (`clear_notion_export`).
  7. **WSGI Worker Starvation Defense**: Synchronous `time.sleep` on HTTP 429/503 `Retry-After` is strictly capped at $\le 2.0$ seconds (max 2 retries, 5s cumulative timeout).
  8. **Deterministic CI Portability**: `MockNotionClient` validates exact REST constraints without opening outbound sockets, allowing all 150 Python unit tests and 9-stage Chrome CDP browser tests to execute at $0.00 spend.

## Repository foundation

- CI merge: `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa` (PR #2). `.github/workflows/python-tests.yml` runs the entire suite on PRs targeting main and pushes to main, with pinned official actions, read-only token permissions and no supplied secrets/caches/artifacts. The owner confirms included minutes remain and no valid payment method is attached; no billing setting or paid usage was enabled. [CI research/review](research/foundation/README.md).
- Namespace merge: `91b824f395d062a994056e905f475fe83f52b3a8` (PR #3). Both production files moved from `tabwise` to `settletable` with identical bytes; no hash-domain, schema or canonical/replay change. Old-package-created SQLite compatibility passes; the coordinator's renamed full suite passes60 methods in73.078s. [Refactor evidence](research/foundation/package-refactor.md).
- Hosted PR checks ran all60 tests successfully for both CI and renamed integration; main push checks also run the full suite. Exact observed runs and limits are in [foundation evidence](research/foundation/README.md). Current checkpoint tags remain fixed while main advances.

Confirmed user constraints and detailed open decisions remain in [Phase 1 requirements](research/phase-1/requirements.md). Research entry point: [index](research/README.md).
