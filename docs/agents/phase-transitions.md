# Phase transition decisions

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-10-16 — Phase 1 → revised Phase 2

**Orchestrator decision: CONDITIONAL PASS for targeted feasibility closure.** Phase 1 completed its feasible requirements/domain, three-engine OCR, synthetic Notion and architecture-comparison work. It does not establish release readiness. This transition starts Phase 2 directly under the user's new delegation; no phase approval is requested.

| Material exit criterion | Disposition / evidence | Risk and scope restriction |
|---|---|---|
| Coherent workflow, confirmed collaboration/privacy requirements and explicit decision frontier | PASS — [requirements](../../research/phase-1/requirements.md) | Unresolved settlement/voucher/retention preferences block those policy-dependent features, not further validation. |
| Integer-money reconciliation and exercised domain invariants | CONDITIONAL PASS — [domain](../../research/phase-1/domain-model.md), executable scenarios/results | Disposable simulation is not production validation. Independently review correctness and carry counterexamples into acceptance criteria. |
| Viable permitted extraction path and honest field evidence | CONDITIONAL PASS — [OCR](../../research/phase-1/ocr-validation.md) | Local inference works; human review mandatory. Modern/held-out/device accuracy remains FAIL for unattended OCR claims. Manual entry can proceed independently. |
| Live-edit integrity across actual browser transport | FAIL — [simulation](../../research/phase-1/experiments/collaboration/README.md) proves only in-process behavior | Blocking production live-collaboration readiness; Phase 2 will run a real local transport/two-client probe. |
| Notion representation and failure model | CONDITIONAL PASS — [Notion](../../research/phase-1/notion-validation.md) | Connector/fake-remote evidence only; raw authenticated REST and real workspace limits remain unverified. Optional integration cannot block the core meal workflow. |
| Evidence-based architecture alternatives | PASS for comparison — [assessment](../../research/phase-1/architecture-decision.md) | Production selection was not met at entry; Path C favored, no automatic Next.js preference. Select the smallest stack against a bounded specification after protocol review. |
| Implementation-ready, secure bounded MVP specification | FAIL at transition entry | No production scaffold is authorized by this transition decision. Close protocol/specification gaps first; orchestrator may later approve implementation on recorded evidence. |

**Next scope:** independently challenge financial/security gates; validate actual localhost browser transport, revision/replay/revocation behavior; review optional Notion contract boundaries; write a bounded manual-first collaborative MVP specification and updated architecture decision. Reuse existing OCR evidence; no rerun without a new question. Phone/corpus work remains explicitly unmeasured rather than fabricated. No paid service, public deployment, credentials request or real private-data export is needed for this closure scope.

**Strategy revision:** split capability gates. Manual-first collaboration can become implementation-ready while modern OCR accuracy and authenticated Notion integration remain separately gated. Neither is silently declared validated; production auto-extraction, image archiving and live Notion delivery stay unavailable until their own gates pass. This avoids making absent phone hardware or account credentials prerequisites for all engineering work.

## 2026-10-16 — bounded Phase 2 closure → Phase 3 first calculation slice

**Orchestrator decision: CONDITIONAL PASS into production implementation of the isolated financial calculation module only.** Reviewed the actual independent reports, browser fixture/server/client/runner, SQLite source/results and specification; checked five source hashes against machine evidence in [closure verification](../../research/phase-2/closure-verification.json). Phase 2 closes the feasible engineering questions for this first slice, not every capability in the historical Phase 2 proposal.

| Exit criterion for this implementation scope | Disposition / reviewed evidence | Blocking risk or restriction |
|---|---|---|
| Explicit, bounded mathematical contract and acceptance tests | PASS — [specification](../../research/phase-2/mvp-specification.md), C1–C4 clarifications resolve [independent review](../../research/phase-2/specification-review.md) | Core proves supplied facts mathematically; it cannot establish human review, current revision or organizer identity. |
| Independent financial challenge integrated | PASS — [challenge](../../research/phase-2/gate-challenge.md) | Transfer-ID trap excluded from this calculation-only slice; rounded-base one-sen discount counterexample becomes a required regression. |
| Appropriate stack for the slice | PASS — [architecture](../../research/phase-2/architecture-decision.md) | Python standard library selected; no frontend/server/framework necessary. No source transplant from reference apps. |
| Real browser authority/revision feasibility | CONDITIONAL PASS — [30/30 Chromium assertions](../../research/phase-2/collaboration-validation.md) | Synthetic tokens/in-memory state, not production auth or actual network-failure recovery. Not a dependency of a pure calculator. |
| Durable transaction/replay feasibility | CONDITIONAL PASS — [20/20 actual SQLite checks](../../research/phase-2/transaction-validation.md) | Single-host synthetic fixture; no crash/power-loss, full financial/auth composition or backups. Blocks later authority acceptance until implemented/tested together. |
| Public live feature/authentication and full workflow readiness | FAIL — explicit gaps in both probes | Blocks public/live-feature completion, not isolated core implementation. No network host or identity feature in the first slice. |
| OCR, private image handling and real Notion integration | FAIL for feature acceptance — [Phase 1 OCR](../../research/phase-1/ocr-validation.md), [Notion contract](../../research/phase-2/notion-contract-review.md) | Keep these capabilities unimplemented/disabled pending evidence, privacy/account decisions. Their work remains in the product objective. |
| Human escalation needed for this narrow action | PASS — no spend, deployment, credential, private data, destructive operation or unclear source reuse | Future settlement/retention preferences are unresolved and excluded from the first slice. |

**Approved work:** build the independently implemented pure calculation interface and strict decimal-money parser, one behavior/test slice at a time; exercise required examples and malformed inputs; independently review specification conformance and engineering/correctness. Record code/test hashes and actual outcomes before calling the slice complete. The orchestrator selects these test interfaces under the user's delegation; no routine skill-driven confirmation is needed.

**Still blocking later acceptance:** authoritative human-review/revision/identity integration, secure invitations/revocation, durable live operations, funding/settlement policy, image retention, representative phone/OCR validation and authenticated Notion delivery. Subsequent implementation may proceed on recorded gates; none of these failures is silently waived by this transition.

## 2026-10-16 — Phase 3 calculation-slice acceptance

**Orchestrator decision: PASS for the isolated calculation/parser slice, within Phase 3.** Reviewed the complete production module, tests and interface, then actual independent probe sources/results/reports against the [fixed artifact baseline](../../research/phase-3/review-baseline.json). No production edit occurred after that baseline. Phase 3 as a whole is not complete.

| Slice completion criterion | Disposition / evidence |
|---|---|
| Strict integer sen/exact rational modes, signed scoped components, hard reconciliation and immutable results | PASS — [source](../../tabwise/calculation.py), [interface](../calculation-interface.md), [specification](../../research/phase-2/mvp-specification.md) |
| Required literal/malformed-input tests and real execution | PASS — main independently ran `python -m unittest discover -s tests -v`:15 methods, zero failures/errors; [coordinator record](../../research/phase-3/coordinator-verification.json). Implementer also records Python3.12 compatibility and incremental red/green evidence. |
| Independent financial/specification challenge | PASS — [spec review](../../research/phase-3/spec-review.md),66 public-interface checks including literal original-base/one-sen/ordering counterexamples |
| Independent engineering/correctness review | PASS — [engineering review](../../research/phase-3/engineering-review.md),11 targeted check groups; zero material findings within the bounded scope |
| Source integrity and scope conformance | PASS — baseline hashes match; no UI/server/identity/storage/payment/OCR/Notion feature is claimed by this module |

**Next work within Phase 3:** specify and implement the authoritative manual-entry draft slice against the accepted calculation interface: durable accepted commands/results, current membership and organizer/diner permissions, financial review/revision invalidation, atomic finalization and snapshot/conflict behavior. Existing browser and SQLite fixtures are feasibility evidence, not production modules to transplant. Before accepting that slice, integrate and test the actual calculation/transaction/access checks together and independently review security. Resolve genuine user-preference gates only when their feature needs them; no routine numbered-phase approval is requested.

**Blocking later capabilities remain unchanged:** secure Internet invitations and recovery, settlement confirmation/correction policy, receipt retention, actual phone/capture/modern OCR quality, real authorized Notion adapter, backup/restore and public-release operations. Public deployment and external data/account/spend actions still require their separate human escalation.
