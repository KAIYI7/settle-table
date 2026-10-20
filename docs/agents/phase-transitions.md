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
| Strict integer sen/exact rational modes, signed scoped components, hard reconciliation and immutable results | PASS — [source](https://github.com/KAIYI7/settle-table/blob/af7ba147642b8b8e9a5aee973a95c59d46c38b9a/tabwise/calculation.py), [interface](../calculation-interface.md), [specification](../../research/phase-2/mvp-specification.md) |
| Required literal/malformed-input tests and real execution | PASS — main independently ran `python -m unittest discover -s tests -v`:15 methods, zero failures/errors; [coordinator record](../../research/phase-3/coordinator-verification.json). Implementer also records Python3.12 compatibility and incremental red/green evidence. |
| Independent financial/specification challenge | PASS — [spec review](../../research/phase-3/spec-review.md),66 public-interface checks including literal original-base/one-sen/ordering counterexamples |
| Independent engineering/correctness review | PASS — [engineering review](../../research/phase-3/engineering-review.md),11 targeted check groups; zero material findings within the bounded scope |
| Source integrity and scope conformance | PASS — baseline hashes match; no UI/server/identity/storage/payment/OCR/Notion feature is claimed by this module |

**Next work within Phase 3:** specify and implement the authoritative manual-entry draft slice against the accepted calculation interface: durable accepted commands/results, current membership and organizer/diner permissions, financial review/revision invalidation, atomic finalization and snapshot/conflict behavior. Existing browser and SQLite fixtures are feasibility evidence, not production modules to transplant. Before accepting that slice, integrate and test the actual calculation/transaction/access checks together and independently review security. Resolve genuine user-preference gates only when their feature needs them; no routine numbered-phase approval is requested.

**Blocking later capabilities remain unchanged:** secure Internet invitations and recovery, settlement confirmation/correction policy, receipt retention, actual phone/capture/modern OCR quality, real authorized Notion adapter, backup/restore and public-release operations. Public deployment and external data/account/spend actions still require their separate human escalation.

## 2026-10-17 — Verified repository checkpoint and local authority specification

**Orchestrator decision: PASS for repository establishment; PASS to begin the bounded local authority implementation within Phase 3.** These are separate decisions in that order. No authority production code was added during publication. The actual new specification and independent report were read before this decision; the five initial findings remain in the report with their resolutions.

| Gate | Disposition / evidence | Restriction or unresolved risk |
|---|---|---|
| Clean, reviewed baseline and remote checkpoint | PASS — [prepublication audit](../../research/publishing/prepublish-audit.md), [actual remote verification](../../research/publishing/checkpoint.json) | Annotated `phase2-accepted` remains fixed at `69895457d9e3524c90df24f3a21c284ea70cef6c`; subsequent docs advance main. Excluded assets and reproducibility limits remain explicit. |
| Bounded authority contract against accepted financial semantics | PASS — [specification](../../.scratch/authoritative-draft/SPEC.md),20 acceptance cases; main reviewed all commands, transactions, limits and exclusions | Quantity-only local slice, fixed participants and trusted bootstrap. Other split editors and operational session renewal are later work. |
| Independent security/specification challenge resolved | PASS — [actual review](../../research/phase-3/authority-spec-review.md), A1–A5 | Current permission before replay; bounded credentials; coherent read authorization; pending claims; bounded security-revocation reserve. Main selected these reversible engineering rules. |
| Integrated authority acceptance | FAIL / not implemented | Blocks declaring the slice complete. Actual calculator/SQLite/access composition, reopen/replay, race/rollback and independent source/security review are required. Specification acceptance is not implementation evidence. |
| Remote identity, live UI and release capability | FAIL / outside this local scope | No listeners or deployment. Internet invitations/recovery, UI defenses, backups and operational checks remain later gates. |
| Human escalation required for this bounded action | PASS — none | No spend, account action, external/private-data operation or unresolved policy activation. Future policy-dependent features remain gated. |

**Authorized next work:** implement/test trusted bootstrap and authenticated snapshots first, then accepted command replay, quantity claims, receipt attestation and atomic finalization with the accepted calculator. Use small red→green behaviors and disposable test databases; retain strict integer money and rational bounds. Independently review actual source and integrated evidence before accepting the slice. No routine phase approval is requested.

## 2026-10-17 — Local authoritative-draft acceptance on feature branch

**Orchestrator decision: PASS for the bounded local implementation; publish `feature/authoritative-draft` and open its PR against main as requested.** This accepts one slice within Phase 3, not a full product or public deployment. Main read the actual production module, tests/interface, independent reports and twenty-case mapping. [Acceptance detail](../../research/phase-3/authority-acceptance.md), [exact verification/hashes](../../research/phase-3/authority-verification.json).

| Gate | Decision / evidence | Remaining restriction |
|---|---|---|
| Spec, exact finance and calculator integrity | PASS — all20 cases mapped, actual calculator finalization and unchanged source hash | Quantity claims only; supplied receipt facts still require organizer attestation. |
| Test execution and atomic persistence | PASS — main60 tests in195.536s; real independent connections, races, rollback, reopen/fresh process and actual10,000-command quota | No power-loss/restore/load claim. Diagnostic-only assertion hardening followed by27 targeted passing reruns. |
| Independent source/spec and security reviews | PASS — both final reports pin source `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`; material A1/S1/S2 fixed and retested | Original failures remain documented; no open material finding. |
| Credential/replay/current access | PASS — hash-only credentials, safe callbacks/cleanup, current authorization before replay, real reserve and nonleak checks | Trusted host/bootstrap/clock; fixed sessions lack renewal and recovery. Lost bootstrap acknowledgement cannot reissue credentials. |
| Full Internet application/release | FAIL / excluded from this slice | Real identity/invitation/transport, UI, backup/restore, other split editors, settlement/correction policies, OCR and Notion require later gates. |

No scope redesign, calculator modification, paid/external-data operation or listener was needed. Ordinary state headroom below1MiB preserves security revocations; natural maximal-result capacity remains unmeasured and the response-size fault test is labeled as injected. The requested PR is the deliverable; this decision does not merge it or authorize another feature within this task.

## 2026-10-17 — Authority merge/checkpoint and repository foundation

The user reports completed independent external review without a merge blocker and explicitly authorizes merge/checkpoint and repository-foundation work. This supersedes the preceding task's stop-at-PR boundary.

| Gate | Decision / verified evidence |
|---|---|
| Reviewed head/base unchanged | PASS — actual PR1 metadata and Git remote refs match head `59cba5feb25423ebd43ebee17b7666d84f83d584` and main `7db4ef155149526f6c646158814d1851b5fdb21b`; GitHub reports mergeable. External review completion is user-supplied evidence, not fabricated GitHub review submissions. |
| Preserve accepted history | PASS — GitHub merge method `merge`, expected-head guard; resulting `af7ba147642b8b8e9a5aee973a95c59d46c38b9a` has those exact two parents and the reviewed head's tree. |
| Remote checkpoint | PASS — remote main verified at merge; annotated `authority-v1-accepted` object `389eb52462cfe0a17a4456504a41214956ae15bc` peels to the merge. |
| CI activation cost | PENDING account evidence — establish minimal full-suite CI only within included usage and verified zero paid-overage exposure; do not alter billing/payment settings. |
| Foundation and next-slice scope | PASS to research/review separate CI and package refactor changes, preserving all deterministic and persisted domains; then plan transport/identity/invitations. No new product feature begins in this foundation step. |

## 2026-10-17 — Foundation accepted; invitation/transport planning

**Orchestrator decision: PASS for repository foundation; proceed to bounded lifecycle specification/planning.** [Foundation index/evidence](../../research/foundation/README.md), [next plan](../../research/phase-3/next-slice-plan.md), [independent architecture/security challenge](../../research/phase-3/transport-identity-challenge.md).

| Gate | Decision and evidence |
|---|---|
| Included-only hosted usage | PASS on explicit owner account confirmation: included minutes remain, no valid payment method. Official quota blocking rule verified; no payment/budget settings changed. Workflow timeout/concurrency are not falsely treated as a billing cap. |
| Minimal full-suite CI | PASS — independently reviewed candidate, exact official SHA pins independently read; PR #2 hosted run completed60 tests in28.299s, then merged at `a4dd5302f93b41bbf72cbf29ecd596bc7bb7c1aa`; main push run also passed. No security/authority tests filtered or weakened. |
| Dedicated package refactor | PASS — PR #3 at `a50fa4585e91b8b8eadcf51177f545366b90f7d0`, merged as `91b824f395d062a994056e905f475fe83f52b3a8`; three production files byte-identical, seven callers have exact namespace-only deltas. Current imports `settletable`; all five versioned domains preserved. |
| Cross-version data and execution | PASS — old-tag→new-package10 exact replays/3 equal snapshots, schema/history/verifiers unchanged, revoked/expired/conflicting replay denied and fresh draft command accepted. Main local60 tests73.078s; hosted rename PR60 tests30.151s. An interrupted subagent session is not counted; the orchestrator reran and reviewed actual evidence. |
| Next slice readiness | PASS to plan/specify; CONDITIONAL for implementation — close one-time-grant acknowledgment/status behavior, bounded rotation/security reserve and additive old-DB compatibility in a reviewed concrete spec. Reject separate-store invitation wrappers. |
| Full browser/public service readiness | FAIL / outside current scope — real origin/CSRF/cookie/Host, identity recovery, abuse/backup/TLS and deployment evidence remain later gates. No public service, new framework or product feature added. |

The next local scope targets invitations and sessions for already declared diner identities within the authority transaction. Follow with a separately tested same-origin transport. Preserve current financial replay contracts and no raw-bearer persistence; do not activate recovery/handover/member restoration policy by inference. No routine phase confirmation is needed; genuine spend/exposure/account/product-policy escalation remains effective.

## 2026-10-20 — Invitation and session lifecycle specification acceptance; implementation authorized

**Orchestrator decision: PASS to begin implementation of the integrated invitation and session lifecycle within Phase 3.** Evaluated against [next-slice-plan](../../research/phase-3/next-slice-plan.md), [independent challenge](../../research/phase-3/transport-identity-challenge.md), and [specification](../../.scratch/invitation-lifecycle/SPEC.md); reviewed actual report from independent research subagent. All 8 review findings are incorporated.

| Material Gate | Disposition / Evidence | Restriction / Invariants |
|---|---|---|
| Single transaction owner | PASS — all lifecycle operations (`issue_invitation`, `redeem_invitation`, `rotate_session`, `RevokeInvitation`) reside strictly in `settletable.authority.Authority` on the single SQLite connection. | No separate store, sidecar DB, or check-then-apply framework. |
| Zero credential persistence & domain separation | PASS — tokens and credentials suppressed in repr, absent from SQLite/snapshots/commands/results/exceptions; new domain `settletable-invitation-v1\0` strictly separated. | No raw secret in logs, DB dumps, or test failure messages. |
| Single-use, expiry, and atomic rotation | PASS — tokens consumed atomically; rotation destroys prior session verifier; exclusive trusted-clock expiry enforced. | No unauthenticated participant creation, organizer handover, or account recovery. |
| Cascading revocation correctness | PASS — `RevokeSession` and `RevokeMembership` invalidate outstanding active invitations; `already_revoked` requires both session and invitations to be inactive. | Precludes resurrecting access via pre-existing invitations. |
| Resource limits and security reserve | PASS — 64 lifecycle generations per participant; ordinary quota capped at 10,000; security commands exempt with mathematical bound $\le 6,534$ rows. | Exhaustion of ordinary/lifecycle quota does not prevent revocation. |
| Reversible additive schema & v1 compatibility | PASS — `invitations` and `participant_lifecycle` created with `CREATE TABLE IF NOT EXISTS`; existing tables untouched; historical replay and snapshots byte-identical. | Verified by reopening disposable v1 databases. |
| Safe acknowledgment & retry policy | PASS — lost grant commits are explicitly uncertain; retry of consumed token or rotated session rejects; status visible in snapshot via `InvitationRecord`. | No recoverable secret storage. |
| Public exposure / spend escalation | PASS — no spend, no deployment, no network listener, no third-party services, no credential changes. | Strictly localhost/in-process Python standard library. |

**Approved next action:** Implement the vertical slices via TDD (`issue_invitation`, `redeem_invitation`, `rotate_session`, `RevokeInvitation`, cascading revocation, snapshot metadata, resource quotas, and backward compatibility), verify passing test suite, and run adversarial lifecycle tests.
