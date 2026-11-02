# Phase transition decisions

## 2026-11-02 — Notion block schema and error diagnostics milestone: PR #28 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `02302e95bba8ce9adab621d9c523e59f09d31ffe` merged autonomously under orchestrator governance policy into `main` at `5c0a8d88e049d956241dd23328cc2ef4af499858`. GitHub PR #28 ([#28](https://github.com/KAIYI7/settle-table/pull/28)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| Notion block schema compliance | PASS: enforced `"object": "block"` and `type="table_row"` on all 9 `table_row` child block constructors across compact and full formats; updated `MockNotionClient` to strictly validate block object compliance. |
| Granular export diagnostics | PASS: differentiated `NotionNotFoundError` (HTTP 404, `page_not_found`) from `NotionValidationError` (HTTP 400, `validation_error`); sanitized error messages to prevent token exposure in `export_digest`. |
| Local regression | PASS: 230/230 Python test suite methods passed in 93.2s; 12/12 automated real-browser CDP test stages passed (`tools/e2e_browser_test.mjs --port 8095`). |
| Hosted CI | PASS: [run 41386556198](https://github.com/KAIYI7/settle-table/actions/runs/41386556198) passed all Python and browser steps on exact PR head `02302e95bba8ce9adab621d9c523e59f09d31ffe` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `ecebd01c-1413-4d68-a9a7-cf720a72e231`); zero critical/high/medium findings; all 3 low polish points remediated; no credentials or secrets committed. |
| Live Notion smoke test guidance | PASS: identified live connection prerequisites (integrations require explicit UI connection to target parent page via Notion `...` -> **Connect to** to avoid 404 `object_not_found`). |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-01 — Local OCR parsing and Notion redirect defense milestone: PR #26 merge

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `d65d383857229600252a7c1d206bb5e59280a0f1` merged autonomously under orchestrator governance policy into `main` at `e06f606d5f9ff822ce54de7334fe9bc4daf1e63b`. GitHub PR #26 ([#26](https://github.com/KAIYI7/settle-table/pull/26)) verified on hosted CI before merge.

| Gate | Disposition |
| --- | --- |
| OCR parser & RapidOCR compatibility | PASS: summary lines require monetary amounts to prevent column header false positives from aborting scanning; added trailing item quantity extraction; polymorphic handling of RapidOCROutput dataclass and tuple/list formats. |
| Notion security & redirect defense | PASS: DisallowRedirectHandler blocks all HTTP 3xx redirects on NotionHttpClient to eliminate Bearer token forwarding leakage across redirect chains; API version pinned at stable 2022-06-28. |
| Local regression | PASS: 226/226 Python test suite methods passed in 88.7s; 12/12 automated real-browser CDP test stages passed in 23.5s (`tools/e2e_browser_test.mjs`). |
| Hosted CI | PASS: [run 41314417879](https://github.com/KAIYI7/settle-table/actions/runs/41314417879) passed all Python and browser steps on exact PR head `d65d383857229600252a7c1d206bb5e59280a0f1` in ubuntu-24.04 (Python 3.14). |
| Code review & hygiene | PASS: independent review APPROVE (conversation `dd8929f9-5be4-467c-8547-cd29620df349`); zero critical/high/medium findings; audited publication diff contains zero authentic receipt images, ONNX models, virtualenvs, or personal paths. |
| Live Notion workspace & deployment | HELD: live smoke test procedure documented (`docs/notion-smoke-test.md`) with explicit consent and disposable setup steps; held behind PO authorization. No deployment or multi-payer work authorized. |

Authority: [governance](governance.md). Current state: [PROJECT_STATUS](../../PROJECT_STATUS.md). Only the main orchestrator records approval of progression; reviews are inputs.

## 2026-11-01 — Focused UAT corrective milestone: pre-merge decision

**Orchestrator decision: PASS for the bounded corrective merge**, subject to unchanged PR head and base at merge. This is not local MVP acceptance or deployment approval.

Merged [PR #24](https://github.com/KAIYI7/settle-table/pull/24) as `7aaf2b32a72462d956f93e8f54adfd627a7ff86e`; GitHub confirmed that SHA on remote `main` and PR head `0cfb96119fc17cb21f0d77b76c0362b1fe8acfcb`. The merge has both expected parents and its tree equals the reviewed head tree.

| Gate | Disposition |
| --- | --- |
| Financial policy and compatibility | PASS: owner confirmed fixed legacy scope and blocking empty fixed scopes; independent financial/security review and historical replay checks passed; calculator unchanged. |
| Modal and recovery | PASS: independent specification and recovery reviews, keyboard tests, competing identities, blocked and superseded refreshes, and preserved drafts. |
| Local regression | PASS: 216 Python tests; 12 Chrome E2E stages; focused financial/export and recovery tests; ten Concept C scenarios. Path cleanup independently reviewed and affected browser tests rerun. |
| Hosted CI | PASS: [run 41276975790](https://github.com/KAIYI7/settle-table/actions/runs/41276975790) passed all Python and browser steps on PR head `0cfb96119fc17cb21f0d77b76c0362b1fe8acfcb`. |
| Final review | PASS: 17 audited publication files matched reviewed local blob hashes; private repository, PR head, and base `73806f67338461ed169a47f4e639c02d71e56e56` rechecked. |
| Independent UAT and release | OPEN: separate manual UAT, physical mobile and screen-reader validation remain outstanding; no public deployment authorized. |

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

## 2026-10-20 — PR #4 Merge: Integrated Invitation and Session Lifecycle Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `0f63ecd00ea71c5c667c70ef750012f594ae3add` merged autonomously under the orchestrator governance policy into `main` at `75a3511982091d6c49f97a29dbf7a9fcb6de0205`. All 5 external review findings resolved; independent security review subagent delivered unconditional GO (`research/phase-3/invitation-security-review.md`); 79/79 test suite methods passed in 149.391s; hosted GitHub Actions CI run `39404379865` succeeded.

| Gate | Disposition / Evidence |
|---|---|
| Invariants & Financial Correctness | PASS — `settletable.calculation` byte-identical (`4e4484...`); 15 calculation tests pass; all 4 hash domains intact with null-terminator prefixes. |
| Secret Hygiene | PASS — Zero token persistence; `repr=False` on all bearer material; SHA-256 verifiers only; SQL/dump/bytes scans verify zero leakage. |
| Concurrency & Transactions | PASS — Exclusive `BEGIN IMMEDIATE` locks; dual-connection racing redemption and racing revocation serialize deterministically; cascading revocation verified across 3 pathways. |
| Error Handling & Entropy Failures | PASS — `secrets.token_urlsafe` and verifiers inside `try:` with rollback in `issue_invitation`, `redeem_invitation`, `rotate_session`; tested via entropy-injection mock. |
| Security Reserve Bound | PASS — Rigorously proved $\le 12,771$ commands ceiling for $N \le 100, G = 64$; enforced with defensive `< 15,000` limit on `security = 1` commands in `apply()`. |
| Duplicate `issue_id` Safe Rejection | PASS — Explicit `SELECT 1 FROM invitations WHERE meal_id=? AND issue_id=?` cleanly raises `AuthorityError('command_conflict')` without database integrity crashes. |
| Organizer Session Lockout Protection | PASS — `rotate_session` restricts callers to non-organizers (`_require(not organizer, 'forbidden')`), eliminating irreversible self-lockout from uncertain rotation. |
| Additive Backward Compatibility | PASS — Reopening v1 databases works additively; historical commands/snapshots replay byte-identically. |
| Hosted CI Verification | PASS — GitHub Actions run `39404379865` on head `0f63ecd` passed full test suite on Python 3.14 / Linux. |

**Next scope:** specify, challenge, and implement the bounded same-origin transport adapter (HTTP/transport boundary for meal requests) under orchestrator governance.

## 2026-10-20 — PR #5 Merge: Bounded Same-Origin Transport Adapter Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `1f1fb789f5bc5cf93b04c0ec6063b5f63969a9b2` merged autonomously under the orchestrator governance policy into `main` at `43b827f486ffa06d532c37d89826ccf2aa50051f`. GitHub marks PR #5 closed rather than merged because the branch was merged directly via git CLI (`git merge --no-ff`) and pushed to `main`; all reviewed commits and tree changes are fully integrated. Prior architectural challenge conducted (`research/phase-3/transport-adapter-challenge.md`); post-implementation independent security review delivered PASS / GO (`research/phase-3/transport-adapter-review.md`); all 6 review remediations (wire header limits, defensive payload parsing, secret logging redaction, SQLite WAL mode, case-insensitive auth headers, and Unicode NFC key deduplication) verified; 101/101 test suite methods passed in 66.240s; hosted GitHub Actions CI run `39408626484` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Wire Boundaries & Limits | PASS — Request header lines $\le$ 4 KB, total header block $\le$ 16 KB (431 `header_too_large`), body $\le$ 1 MB (413 `payload_too_large`), nesting depth $\le$ 10, integer digits $\le$ 19, duplicate keys (with Unicode NFC normalization) and floats strictly rejected. |
| CSRF & Origin Protection | PASS — Mandatory `X-SettleTable-Action: 1` header on all POST requests; strict `Origin` matching against `server_origin` for cookie or unauthenticated browser contexts; `Origin: null` blocked; conflicting Bearer/cookie rejected with 400 `conflicting_credentials`. |
| Unauthenticated Landing Separation | PASS — `GET /api/invitations/{token}` invokes read-only `Authority.inspect_invitation()`; non-mutating, zero token consumption, zero revision advance; tested over 5x sequential calls. |
| Error Mapping & Suppression | PASS — Canonical envelope `{"ok": false, "error": "...", "detail": null}`; unhandled exceptions suppressed to 500 `internal_error`; 401 attaches `WWW-Authenticate: Bearer`; 503 attaches `Retry-After: 1`. |
| Cookie Security | PASS — Host-only cookies with `HttpOnly; Secure; SameSite=Strict; Path=/` across bootstrap, redemption, and session rotation. |
| Actor Isolation | PASS — `actor` and `organizer` injection strictly rejected at transport parsing boundary with 400 `invalid_input`; actor identity derived strictly from session credential. |
| Secret Hygiene & Redaction | PASS — Zero tokens/credentials logged; `redact_log_string` masks URLs, Bearer credentials, and cookie values to `[REDACTED]`. |
| Concurrency & Persistence | PASS — SQLite opened in WAL mode with `busy_timeout=1000`; per-thread `Authority` instances maintain thread affinity. |
| Hosted CI Verification | PASS — GitHub Actions run `39408626484` on exact head `1f1fb78` passed all 101 tests on Python 3.14 / Linux. |

**Next scope:** Frontend UI / web client integration for meal drafts, item claiming, and invitation landing under the bounded transport API.

## 2026-10-20 — PR #6 Merge: Transport-Boundary Hardening Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `65ae4bd7987fc5208f8705b6197171ef0728c057` merged autonomously under the orchestrator governance policy into `main` at `e7a8a82918353d82188746c0d7b19fec499b2698`. GitHub PR #6 closed upon direct merge to main. Post-implementation independent security review delivered unconditional GO (`research/phase-3/transport-hardening-review.md`); all 5 audit gates passed; 104/104 test suite methods passed in 63.364s; hosted GitHub Actions CI run `39420125202` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Reverse Proxy Loopback Protection | PASS — `POST /api/meals/{meal_id}/bootstrap` rejects requests containing proxy headers (`X-Forwarded-For`, `X-Forwarded-Host`, `X-Forwarded-Proto`, `Forwarded`, `X-Real-IP`) with 403 `forbidden`, preventing external proxy bypass of loopback checks. |
| Credential Minimization at Provisioning | PASS — Bootstrap returns session credentials strictly for the organizer (`sessions: [{"participant_id": organizer_id, "credential": ...}]`); never returns pre-minted diner credentials over HTTP. |
| Cookie-Context Credential Hygiene | PASS — `POST /api/meals/{meal_id}/session/rotate` omits raw bearer credentials from the JSON response body when the caller authenticated via cookie, delivering credentials exclusively via `Set-Cookie` (`HttpOnly; Secure; SameSite=Strict; Path=/`) to prevent XSS exfiltration. Programmatic Bearer callers retain credential in JSON. |
| Ingress vs. WSGI Boundary Demarcation | PASS — `docs/deployment-boundary.md` explicitly documents the Tier 1 ingress boundary (TCP stream bounds in reverse proxy) vs. Tier 2 WSGI application defense-in-depth, including Nginx reference configuration. |
| Test Coverage & Invariant Integrity | PASS — 104/104 tests pass; zero modification to `settletable.authority` or `settletable.calculation`; deterministic math and state machine invariants intact. |

**Next scope:** Design, specify, and implement the same-origin browser MVP (organizer receipt entry/review, diner invitation landing, item claiming, and finalized allocation results) using local assets and responsive mobile-first UI.

## 2026-10-20 — PR #7 Merge: Same-Origin Browser MVP Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `cd4973c1cd73dae8f6ebe8e97640e04604ae16f6` merged autonomously under the orchestrator governance policy into `main` at `67f7190638696f8592cd49fa489b5f12f64b49e1`. GitHub PR #7 closed upon direct merge to main. Architectural challenge conducted (`research/phase-3/browser-mvp-challenge.md`); post-implementation independent security review delivered CONDITIONAL PASS with 4 minor remediations (`research/phase-3/browser-mvp-review.md`), all of which were resolved in commit `cd4973c` (server-authoritative `snap.issues` evaluation for finalization, in-memory invite token caching for link re-copy, $44\text{px}$ touch targets on stepper buttons, and `escapeHtml()` error sanitization); 109/109 full-suite tests passed locally in 63.725s; hosted GitHub Actions CI run `39423753289` succeeded on the exact final reviewed head SHA.

| Gate | Disposition / Evidence |
|---|---|
| Zero External Dependencies & Asset Isolation | PASS — Zero CDNs, zero web fonts, zero remote tracking/analytics scripts; 100% self-contained local assets (`settletable/static/`); system font stack utilized. |
| Static Asset Serving & Path Traversal Security | PASS — Static files served strictly through an in-memory dictionary allowlist (`STATIC_FILES`) and regex matching (`/static/([A-Za-z0-9_.-]+)`); `X-Content-Type-Options: nosniff`; `Cache-Control: no-store` on HTML routes; path traversal attempts fail regex and return 404 `not_found`. |
| Content Security Policy & DOM XSS Immunity | PASS — Strict Content Security Policy header attached to all HTML/static routes (`default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'`); all dynamic server data and user inputs escaped via `escapeHtml()`. |
| Authentication, Invitation Landing & Session Boundary | PASS — Host-only cookies with `HttpOnly; Secure; SameSite=Strict; Path=/`; unauthenticated landing `GET /invite/{token}` serves HTML shell without token consumption or state mutation; one-click redemption establishes cookie; caller identity and role context (`current_participant_id`, `is_organizer`) returned via `Authority.authenticate()`. |
| Dining Flow UX, Conflict Handling & Human Receipt Review | PASS — Mobile-responsive layout (touch targets $\ge 44\text{px}$, `viewport-fit=cover`); explicit human receipt verification step before finalization; concurrency conflicts (item revision collisions) return HTTP 409 Conflict with amber conflict banner, contested card highlight, and automatic refresh. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains remain completely untouched; all 109 automated tests pass. |

**Next scope:** Browser MVP end-to-end defect fixes, real browser journey automation with Headless Chrome, and local demonstration handover.

## 2026-10-20 — PR #8 Merge: Browser MVP E2E Defects & Real Browser Validation Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `172d56f8f5337fc9a518fb1935c754dc9335e76a` merged autonomously under the orchestrator governance policy into `main` at `a8436fdcb8848fe5ce299c883a26a2b0c2e64dfc`. GitHub PR #8 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/browser-e2e-fixes-review.md`); all 6 audit gates passed; 113/113 test suite methods passed in 60.448s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39442110445` succeeded on the exact reviewed head.

| Gate | Disposition / Evidence |
|---|---|
| Receipt-Entry Contract & Human Verification | PASS — `ReplaceReceipt` command in `settletable/static/app.js` computes authoritative `subtotal_sen` and `total_sen` from line items and adjustments; resolves `missing_amount` review rejection without fabricating zero amounts; mandatory human review preserved before finalization. |
| Authoritative Calculation Display | PASS — `renderFinalizedCalculation()` maps participant totals directly from `calculation.consumption` records (`participant_id -> sen`); renders explicit `Amount Missing` warning if data is absent rather than fabricating RM 0.00; grand total tied to `receipt.total_sen` and consumption sum. |
| Mutation Refresh & Conflict Recovery | PASS — Polling (`fetchSnapshot(false)`) and mutation refresh (`fetchSnapshot(true)`) decoupled; `state.mutationActive` cleared before forcing refresh; monotonic sequence numbering (`state.pollSeq`) guards against out-of-order poll clobbering; 409 stale conflict handled cleanly with amber alert and UI reload. |
| Strict MYR Input Parsing | PASS — `parseSen()` replaces permissive `parseFloat` with strict regex `/^[0-9]+(?:\.[0-9]{1,2})?$/` and pure integer sen arithmetic; rejects malformed characters, non-strings, negative amounts, and out-of-bounds values without floating-point drift. |
| Real Browser E2E Test Verification | PASS — `tools/e2e_browser_test.mjs` executes an 8-stage automated CDP test across two isolated Headless Chrome instances with independent user profiles and cookie stores; validates end-to-end flow from room creation to reload persistence. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains remain untouched; 113/113 full-suite tests pass. |

**Next scope:** Cross-platform browser test infrastructure improvements, bearer token log sanitization, and GitHub Actions CI browser journey automation.

## 2026-10-21 — PR #9 Merge: Cross-Platform Browser Test Infrastructure & CI Automation Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `5a879c5ed5ef7c95939da0b4fd98e2516d086e1b` merged autonomously under the orchestrator governance policy into `main` at `1b693f56cb3cf3df0e7cb84727cccaf594d1e769`. GitHub PR #9 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/test-infra-review.md`); all 5 audit gates passed; 113/113 test suite methods passed in 47.362s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39508712147` succeeded on the exact reviewed head in `ubuntu-24.04`, validating both the Python unit suite and the real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Dynamic Cross-Platform Discovery | PASS — `tools/e2e_browser_test.mjs` dynamically resolves Chrome/Chromium and Python binaries across Windows, Linux, and macOS without hardcoded paths; supports env vars (`CHROME_BIN`, `PYTHON_BIN`) and CLI flags (`--chrome`, `--python`, `--port`); resolves repository root via `import.meta.url`. |
| Secret Log Hygiene | PASS — Invitation bearer URLs are sanitized via regex (`/invite/[REDACTED]`) before `console.log` output; unhashed bearer tokens never leak into test output or CI logs; unredacted URL is retained strictly in-memory for browser navigation. |
| Container Headless Chrome Flags | PASS — Headless Chrome configured with `--headless=new`, `--no-sandbox`, `--disable-dev-shm-usage`, and `--disable-gpu` to guarantee crash-free execution in unprivileged Linux container and VM environments. |
| CI Integration & Zero-Cost Conformance | PASS — `.github/workflows/python-tests.yml` executes `node tools/e2e_browser_test.mjs` natively on `ubuntu-24.04` runner with pre-installed Chrome and Node built-ins; zero added dependencies, zero SaaS subscriptions, <0.2% monthly quota usage ($0.00 cost). |
| Test & Invariant Integrity | PASS — Deterministic calculation module and authority contracts untouched; 113/113 Python unit tests pass; real browser CDP harness passes all 8 stages. |

**Next scope:** Bounded local/self-hosted receipt OCR pipeline, organizer verification gate, Malaysian SST/service-charge extraction, and optional asynchronous Notion reporting.

## 2026-10-21 — PR #10 Merge: Bounded Local Receipt OCR Pipeline & Malaysian SST Parser Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `b6dc100d04961917f93539fc4107127e9fe558d4` merged autonomously under the orchestrator governance policy into `main` at `3455a57223d1e1582d1c3c8f8185186484364074`. GitHub PR #10 closed upon direct merge to main. Post-implementation independent security and code review delivered CONDITIONAL PASS (`research/phase-3/ocr-implementation-review.md`), with the wire `Content-Type` validation remediation applied, retested, and verified; all 6 audit gates passed; 136/136 test suite methods passed in 71.784s; 8/8 automated real-browser CDP test stages passed in 3.2s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39512879579` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Local-Only & Zero Cloud Fallback | PASS — OCR inference runs on local CPU via RapidOCR / ONNX Runtime (`settletable/ocr/engine.py:161-189`). Cloud OCR fallback is strictly excluded; missing engine raises `OcrUnavailableError` -> HTTP 503 `ocr_unavailable`. Air-gap socket test verifies zero outbound network connections (`tests/test_ocr.py:391-400`). |
| Safe Binary Ingress & Decompression Protection | PASS — Route-aware body ingress for `POST /api/meals/{meal_id}/ocr/extract` bypasses `parse_strict_json` for raw binary images up to 5 MB (`settletable/transport.py:384-406`). Image dimensions are parsed directly from raw binary headers (PNG IHDR, JPEG SOF markers, WebP VP8 chunks) and bounded to $\le 4096 \times 4096$ and $\le 16\text{MP}$ before bitmap decoding, preventing decompression bombs. Declared `Content-Type` is strictly validated against detected magic bytes. |
| Malaysian Receipt Domain & Invariants | PASS — Deterministic layout parser (`settletable/ocr/parser.py`) enforces the Wan Sheng tax-inclusive rule (`subtotal_sen = sum(items)`, `included_tax_sen` populated) preserving `settletable.calculation` subtotal invariants; correctly extracts statutory tax-exclusive SST/GST, service charge, negative discount sen, and BNM 5-sen rounding ($\pm 1, \pm 2$ sen); enforces the Kechara rule preventing fact invention by leaving unprinted discrepancies as `None` and routing to `manual_correction`. |
| Organizer Authorization & Zero State Mutation | PASS — `POST /ocr/extract` requires valid organizer credentials, returning 403 `forbidden` for diners and 401 for unauthenticated callers (`settletable/transport.py:586-591`). Extraction is strictly advisory with zero SQLite mutations (database file SHA-256 is 100% byte-identical before and after call). Mandatory human receipt review and cryptographic digest sealing in UI preserved before finalization. |
| Deterministic CI Portability & Test Coverage | PASS — `MockOcrEngine` uses pre-recorded JSON token fixtures (`tests/fixtures/ocr/tokens.json`), allowing 100% of the 136 Python tests to pass in CI without native ONNX runtime wheels; real browser CDP test passes all 8 stages. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched. |

**Next scope:** Optional asynchronous Notion reporting, maintaining strict decoupling from live meal collaboration.

## 2026-10-21 — PR #11 Merge: Bounded Optional Asynchronous Notion Reporting Pipeline Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `8a83ba2287ad27764a51147bd594e4b4c4eba966` merged autonomously under the orchestrator governance policy into `main` at `d34ff75caf3047f5a8515d0b3503e3a3948871ae`. GitHub PR #11 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/notion-implementation-review.md`); all 6 audit gates passed; 150/150 test suite methods passed in 62.383s; 9/9 automated real-browser CDP test stages passed in 3.4s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39515609945` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the 9-stage real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| Decoupling & Fault Isolation | PASS — Live meal collaboration, item claiming, receipt review, and finalization execute 100% offline or air-gapped without Notion. Notion export failures leave SQLite meal state, claims, and calculations completely intact with zero database rollbacks. Live dining never depends on Notion availability or credentials. |
| Secret Hygiene & Token Redaction | PASS — Notion API tokens (`secret_...` and `ntn_...`) are strictly excluded from SQLite persistence. Wire logs (`transport.redact_log_string`), error strings, and exception handlers scrub integration tokens to prevent leakage in server output or HTTP error bodies. |
| One-Way Invariance & Financial Integrity | PASS — Apportionment exported to Notion is mapped directly from authoritative `calculation.consumption` integer sen amounts. Notion formulas, rollups, or calculations are strictly zero; money formatting uses integer division without floating-point drift. |
| Quota & Block Efficiency | PASS — Generates $\le 40$ blocks per meal (1 callout + 2 headings + 2 tables + rows + divider + audit paragraph), yielding $>70\%$ block savings over relational multi-page designs and protecting Free tier workspace lifetime block quotas (1,000 blocks). Page-parent export strictly limits properties to `title` (per Notion REST constraint for non-database parents) while placing financial metadata inside the top Callout block; table block dimensions strictly match row cell arrays. |
| Concurrency & Idempotency State Machine | PASS — SQLite tracking table `notion_exports` maintains `(meal_id, finalized_revision)` through `in_progress` -> `completed` state machine, rejecting duplicate concurrent clicks with 409 `export_in_progress` or 409 `already_exported` while permitting clean recovery on failure (`clear_notion_export`). |
| Deterministic CI Portability & Test Coverage | PASS — `MockNotionClient` validates exact REST constraints without opening outbound sockets, allowing all 150 Python unit tests and 9-stage Chrome CDP browser tests to execute at $0.00 spend. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation module (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched. |

**Next scope:** Phase 3 consolidation, operational review, and demonstration handover.

## 2026-10-21 — PR #12 Merge: Phase 3 Consolidation, Operational Hardening & Demo Handover Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `de890fadebc8c3fb7f5eb0a1521e947b0f3a3be5` merged autonomously under the orchestrator governance policy into `main` at `5a5231d5250902968d3f716c9771ac8e23cf41ce`. GitHub PR #12 closed upon direct merge to main. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/consolidation-review.md`); all 5 audit gates passed; 154/154 test suite methods passed in 75.858s; 9/9 automated real-browser CDP test stages passed in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `39531452344` succeeded on the exact reviewed head in `ubuntu-24.04`, validating all Python tests and the 9-stage real browser E2E test in CI.

| Gate | Disposition / Evidence |
|---|---|
| OCR Review Boundary & Staging | PASS — In `settletable/static/app.js`, extracted OCR proposals are staged strictly in client memory (`state.ocrCandidate`) without writing to SQLite; file uploads no longer invoke premature `ReplaceReceipt`; UI displays clear confidence percentage, route badge (`⚠️ Needs Correction` vs `✓ Ready for Review`), and verification issues; explicit `Accept & Apply to Receipt` (dispatches `ReplaceReceipt`) and `Discard` buttons provide safe control; mandatory physical receipt review (`ReviewReceipt`) remains strictly enforced before finalization. |
| Notion Asynchronous Delivery & Duplicate Prevention | PASS — In `settletable/transport.py`, `POST /api/meals/{meal_id}/export/notion` runs in a background daemon thread (`threading.Thread`) and returns HTTP `202 Accepted` immediately by default (preserving `?sync=1` for testing), eliminating WSGI worker thread starvation for live diners; status polling endpoint `GET /api/meals/{meal_id}/export/notion` enables UI progress tracking; pre-creation title reconciliation in `export_finalized_meal` queries parent block children to adopt existing page if previous response was lost, preventing duplicate page creation; delivery semantics are explicitly documented as at-least-once with pre-creation title reconciliation. |
| Notion Free Block Budget Enforcement | PASS — In `settletable/notion/exporter.py`, constant `MAX_COMPACT_BLOCKS = 40` mathematically caps total exported blocks for arbitrary meal sizes via intelligent diner rollup ($P > 20$) and item rollup ($I > \text{remaining\_budget}$), protecting Free tier workspace lifetime block quotas (1,000 blocks); unconstrained `mode='full'` remains available; `count_notion_blocks` accurately tallies top-level blocks and table rows. |
| OCR Operational Validation & Demo Mock | PASS — `settletable/ocr/engine.py` supports both `rapidocr` and `rapidocr_onnxruntime` distributions; `tools/run_demo.py` provides `--mock-ocr` and `SETTLETABLE_MOCK_OCR=1` for immediate zero-dependency evaluation; zero image persistence to disk or SQLite; zero outbound network sockets. |
| Financial Invariants & Invariant Integrity | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) remain completely untouched; 154 unit tests and 9 real browser CDP test stages pass. |

**Next scope:** Phase 3 acceptance and User-Acceptance Readiness review.

## 2026-10-21 — User-Acceptance Readiness: OCR Edit-Before-Accept, Notion Hardening & UAT Handover Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `78f92ad6937e008cbb39e240212a4c148fc2834b` merged autonomously under the orchestrator governance policy into `main` at `84acc18`. Post-implementation independent security and code review delivered CONDITIONAL GO, with all 3 material findings (negative cash rounding sign inversion, `NotionRateLimitError` omission from reconciliation filter, and background worker generic error code recording) fully remediated and verified with regression tests. All 5 audit gates passed; 159/159 test suite methods passed in 59.603s; 9/9 automated real-browser CDP test stages passed in 3.6s via Headless Chrome (`tools/e2e_browser_test.mjs`).

| Gate | Disposition / Evidence |
|---|---|
| **OCR Candidate Edit-Before-Accept & Rounding Preservation** | PASS — In `settletable/static/app.js`, staged OCR candidate proposals can be corrected directly in an inline table (item names, quantities, unit prices, adjustments, and included tax) before applying to the draft receipt; live typing recalculates candidate subtotals and totals without input focus loss; `parseSen` and adjustment synchronizer preserve negative Bank Negara Malaysia cash rounding adjustments (e.g. -RM 0.02) without sign inversion; validation enforces positive line amounts and item existence before dispatching `ReplaceReceipt`; physical bill verification gate (`ReviewReceipt`) remains mandatory before finalization. |
| **OCR Local Inference Demarcation** | PASS — UI badge and documentation explicitly identify OCR as Server-Side Local Inference (RapidOCR CPU ONNX), eliminating misleading "on device" claims; extraction remains 100% advisory with zero SQLite mutation. |
| **Notion Reliability & Pagination** | PASS — `NotionHttpClient.query_block_children` implements cursor pagination (`max_pages=5`, `page_size=100`); pre-creation title reconciliation re-raises `NotionAuthError`, `NotionValidationError`, `NotionNotFoundError`, and `NotionRateLimitError` rather than silently swallowing them; delivery semantics remain at-least-once with pre-creation title reconciliation. |
| **Background Processing & Worker Starvation Defense** | PASS — Ephemeral background thread lifecycle is explicitly documented; synchronous export override `?sync=1` is disabled by default behind `allow_sync_export=False` (safeguarded via `SETTLETABLE_ALLOW_SYNC_EXPORT=1`), preventing WSGI worker starvation in public deployments; in-progress exports time out cleanly after 60s, recording `status='failed'` and allowing recovery; background export records granular error codes (`notion_rate_limited`, `notion_auth_error`, `invalid_input`, `notion_error`). |
| **Secret Hygiene & Demo Accuracy** | PASS — Verified that `tools/run_demo.py` prints zero credentials or session links to stdout; sessions are managed via host-only secure cookies and in-app invitation copying; comprehensive [User Acceptance Testing (UAT) Handover](docs/uat-handover.md) guide delivered. |
| **Financial Invariants & Invariant Integrity** | PASS — Deterministic calculation engine (`settletable/calculation.py`) and cryptographic hash domains remain completely untouched; 159 unit tests and 9 real browser CDP test stages pass. |

**Next scope:** Stakeholder User Acceptance Testing (UAT) walkthrough and Phase 4 operational hardening & production pilot planning.

## 2026-10-25 — PR #17 Merge: Bounded Phase 1 Atomic Item Allocation (`SetItemAllocations`) Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `92babe200ca1dd7cd6c73d83e678554f1ce727ad` merged autonomously under the orchestrator governance policy into `main` at `03a34c7a5f6436427387d7bda299f170f3f6e1eb`. GitHub PR #17 ([#17](https://github.com/KAIYI7/settle-table/pull/17)) verified on hosted CI before merge. Post-implementation independent security and code review delivered unconditional GO (`research/phase-3/atomic-item-allocation-remediation-review.md`); all 6 audit gates passed; 192/192 test suite methods passed in 74.5s; 11/11 automated real-browser CDP test stages passed in 18.8s via Headless Chrome (`tools/e2e_browser_test.mjs`); hosted GitHub Actions CI run `40171431186` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Atomic Item Replacement (`SetItemAllocations`)** | PASS — In `settletable/authority.py` (`Authority._set_item_allocations`) and `settletable/transport.py` (dispatched via `POST /api/meals/{meal_id}/apply` with `kind: "SetItemAllocations"`), replacement command validates item-level capacity $\sum \text{quantity} \le \text{item.quantity}$ atomically in a single SQLite transaction, eliminating intermediate deadlocks and partial claim corruption inherent in sequential updates. Supports equal splits, custom rational fractions, portion adjustments, subset splits, and full resets (`allocations = []`). |
| **Claim Provenance & Attribution Integrity** | PASS — Preserves unchanged diner-authored claims (`assigned_by = None`) and prior assigner provenance when an organizer modifies other allocations on the same item. Modified quantities or newly introduced allocations receive `assigned_by = actor` (the acting organizer). Verified by `test_set_item_allocations_preserves_unchanged_diner_claim_provenance`. |
| **Strict Wire Input Sanitization** | PASS — In `settletable/transport.py`, `_parse_quantity(qty, *, allow_none=False)` uses exact type checks (`type(val) is int`), strictly rejecting boolean literals (`True`, `False`, `[True, 2]`, `[1, False]`), floating-point values (`1.5`, `[1.5, 2]`), non-positive values, and malformed fraction lists across all four quantity endpoints (`ReplaceReceipt`, `SetOwnQuantity`, `AssignParticipantQuantity`, `SetItemAllocations`). Verified by 21-case matrix in `test_transport_strict_fraction_and_boolean_rejections`. |
| **Concurrency & SQLite OCC Race Handling** | PASS — Multi-threaded test `test_concurrent_race_set_item_allocations_and_set_own_quantity` uses independent SQLite connections and `Authority` instances across OS threads to verify serializability between organizer `SetItemAllocations` and diner `SetOwnQuantity`. Exactly one transaction succeeds; competing transaction fails cleanly with `item_revision_conflict` (HTTP 409), transaction rolls back without orphan records, and item capacity ($\le \text{total}$) is strictly conserved. |
| **Financial & Apportionment Invariants** | PASS — Deterministic calculation engine (`settletable/calculation.py`) and Hamilton-Hare apportionment tie-breaker (`tabwise-apportion-v1`) remain untouched; sen-level exactness and zero floating-point math preserved; 192/192 Python unit tests pass; 11-stage real browser CDP test passes. |
| **Production Boundary Demarcation** | PASS — Scope is strictly bounded to the Phase 1 backend engine and transport routes. Production frontend allocator and diner self-claiming UI remain untouched; Concept C UI integration is deferred pending PO review and authorization. |

**Next scope:** Production integration of Concept C (Unified Expandable Hybrid organizer allocation) frontend workflow.

## 2026-10-25 — PR #18 Merge: Phase 2 Concept C Organizer Allocation Production Integration Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `751c10ca2d0f7a126c576083a5d511975970aa82` merged autonomously under orchestrator governance policy into `main` at `1f34b3e6d04193908e0264c050a25528df1f13cc`. GitHub PR #18 ([#18](https://github.com/KAIYI7/settle-table/pull/18)) verified on hosted CI before merge. Post-implementation independent code review completed with CONDITIONAL PASS; all review findings (M-01 float math, L-01 mobile pill height, L-02 meta fraction formatting) remediated and verified locally; 192/192 Python test suite methods passed; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passed with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; hosted GitHub Actions CI run `40178531481` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Concept C Item-First Allocation Architecture** | PASS — Replaced the legacy global dropdown Allocation Target Selector with item-first allocation cards (`.hybrid-item-card`). Displays item name, line total, allocation progress bar, available diner pills for 1-click quick assignment, clean allocated diner pills without tiny buttons, and a responsive Details / Split trigger. |
| **1-Click Quick Assign & Capacity Safety** | PASS — 1-click on available diner pill assigns 1 unassigned whole portion instantly. If remaining portion is fractional, user is prompted via toast notification to use Details / Split for custom fractions. |
| **Selective Subset Split with Exact Rationals** | PASS — Organizers select an arbitrary subset of diners to split an item equally. Generates exact reduced rational fractions ($[1, n]$, $[m, n]$) with real-time formula and cost preview (`1 item ÷ 3 diners = ⅓ each (~RM 12.00)`). Explicit confirmation prompt displayed before overwriting pre-existing claims. |
| **Adaptive Desktop / Mobile Architecture** | PASS — Desktop ($\ge 768\text{px}$) expands inline drawer (`.hybrid-drawer`). Mobile ($< 768\text{px}$) displays accessible bottom-sheet modal (`.bottom-sheet-modal`) with scrim backdrop, drag handle, safe-area insets, touch targets $\ge 44\text{px}$, zero horizontal overflow ($375\text{px}$ width verified), and Escape key keyboard dismissal. |
| **Claim Provenance & Attribution Integrity** | PASS — Unchanged diner self-claims (`assigned_by = None`) and original financial revisions are strictly preserved when the organizer updates allocations via `SetItemAllocations`. Verified in real browser E2E test. |
| **Zero Floating-Point Drift & Wire Compliance** | PASS — Rational arithmetic functions (`makeReducedFraction`, `toRat`, `addFractions`, `subtractFractions`, `formatRat`) ensure quantities submitted over the wire strictly match backend integer and fraction pair types, preventing `float_number_rejected` HTTP 400 errors. Apportionment reconciles down to the sen. |
| **Diner Self-Claiming Boundary Intact** | PASS — Diner self-claiming view (`!snap.is_organizer`) remains 100% intact with stepper increments, decrements, and claim-all buttons. |

**Next scope:** Remediation and verification of allocation preview rounding and "All" shortcut zero-capacity guard.

## 2026-10-25 — PR #19 Merge: Concept C Preview Alignment & "All" Shortcut Guard Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `3699dd4efeeaa520101ec2b53bf9467301cbfca9` merged autonomously under orchestrator governance policy into `main` at `b4cf4e8`. GitHub PR #19 ([#19](https://github.com/KAIYI7/settle-table/pull/19)) verified on hosted CI before merge. Post-implementation independent code review completed with unconditional PASS (Zero findings); 192/192 Python test suite methods passed in 171.4s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 10-scenario production verification passed with high-resolution CDP evidence in `tools/verify_concept_c_production.mjs`; hosted GitHub Actions CI run `40197038604` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Deterministic Apportionment Previews (Finding 1)** | PASS — In `settletable/static/app.js`, implemented `apportionItemBase` using Largest Remainder (Hamilton-Hare) apportionment with pure-JS SHA-256 tie-breaker matching `settletable/calculation.py` (`_apportion`). Completely resolves RM 26.01 drift when RM 26.00 is split 3 ways (`867 sen + 867 sen + 866 sen = 2600 sen = RM 26.00` exactly). Output parity verified against Python calculator across test scenarios. |
| **Provisional Item Base Labeling & Hints** | PASS — Per-diner row previews explicitly label amounts as provisional base shares (`~RM X.XX base`), with descriptive tooltips (`title="Provisional item base share. Taxes, service charge, discounts, and rounding are apportioned at finalization."`) and persistent section subtitle (`Provisional item base • Taxes and service charge apportioned at finalization`). Distinctly differentiates unadjusted item base from finalized totals (which incorporate taxes, service charges, discounts, and rounding). Backend calculation engine preserved 100% untouched. |
| **"All" Shortcut Zero-Capacity Guard (Finding 2)** | PASS — When remaining capacity is 0 (`remRat === 0`), "All" button is rendered with `disabled` attribute and descriptive tooltip (`No unassigned portion remains`). Click listener guards against execution when `ratToNum(remRat) <= 0`, displaying a non-destructive info alert without submitting to the API. Other participants' allocations and exact rational arithmetic are strictly preserved. Verified via CDP live injection. |
| **Cross-Platform Verification Path Portability** | PASS — `tools/verify_concept_c_production.mjs` enhanced to dynamically resolve Python binary, Chrome/Chromium executable across Windows, macOS, and Linux, and configurable artifact directory (`process.env.ARTIFACT_DIR`) with automatic directory creation and fallback. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py` and `settletable/authority.py` untouched); sen-level exactness and zero floating-point math preserved; 192/192 unit tests pass; 11-stage real browser CDP test passes; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Formal closure of the organizer allocation milestone and local stakeholder UAT.

## 2026-10-27 — PR #20 Merge: Header Navigation and Toast Layout Polish Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `d8163e54d3315edd8d57eced1cc7cf7503c456c5` merged autonomously under orchestrator governance policy into `main` at `1926871`. GitHub PR #20 ([#20](https://github.com/KAIYI7/settle-table/pull/20)) verified on hosted CI before merge. Post-implementation independent code and UX review completed with unconditional APPROVE / PASS (Zero findings); 192/192 Python test suite methods passed in 80.4s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; visual layout metrics captured across Desktop (1280x800), Tablet (768x1024), Mobile (375x667), and Mobile Bottom Sheet + Toast stacking; hosted GitHub Actions CI run `40512835119` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Simplified Room Navigation Architecture** | PASS — Completely eliminated the redundant `.room-nav-bar` row. Retained `.room-status-card` and added high-contrast, accessible `← Home / Room` breadcrumb navigation (`.room-home-link`), ensuring mobile users retain discoverable Home navigation even when the sticky header's `#nav-home-btn` text link is hidden. Cleaned up obsolete `#room-leave-btn` references in `settletable/static/app.js`. Text contrast reaches 4.90:1 (exceeding WCAG AA 4.5:1), hit area exceeds 64x28px, and layout truncation (`overflow: hidden; text-overflow: ellipsis`) prevents overflow. |
| **Corrected Header & Content Spacing** | PASS — Resolved CSS specificity collision where `.container` (`padding: 0 16px`) silently overrode `main` (`padding: 20px 16px 40px`). Explicitly declared `main#app, main` with `padding: 20px 16px 48px;` (desktop) and `padding: 16px 12px 40px;` (mobile). Eliminated negative margins and hardcoded offsets; content reliably begins 20px (16px on mobile) below the sticky header. All `.room-status-card` styles declared in `settletable/static/style.css`. |
| **Responsive Viewport Toast Placement** | PASS — Introduced `syncHeaderHeight()` to dynamically write `--app-header-height` to `:root`. Anchored `#alert-container` with `top: calc(var(--app-header-height, 68px) + 12px)` on desktop (starts at 81px, 12px below 69px header) and `+ 8px` on mobile (starts at 65px, 8px below 57px header). Zero overlap with sticky header navigation controls (Refresh, Leave Room). Preserved non-scrolling viewport stability, pass-through pointer events, and keyboard Esc dismissal. |
| **Rigorous Layering (z-index Hierarchy)** | PASS — Established explicit stacking hierarchy across page content (`z-index: 1`), sticky application header (`z-index: 200`), mobile bottom-sheet scrim (`z-index: 900`), mobile bottom-sheet modal (`z-index: 950`), and transient notifications (`z-index: 1100`). Guaranteed error alerts and conflict banners remain visible and interactive above modal sheets without blocking modal footer action buttons (`Clear All Claims`, `Done`). Verified via CDP live injection. |
| **Test Suite Resilience & Portability** | PASS — Parameterized `tools/e2e_browser_test.mjs` with `process.env.SETTLETABLE_PORT` and dynamic `${serverOrigin}`, updated assertions to verify `.room-status-card` and `.room-home-link`. All 192 Python unit tests and all 11 real browser CDP stages pass. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py`, `settletable/authority.py`, and `settletable/transport.py` untouched); sen-level exactness and zero floating-point math preserved; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Final stakeholder UAT handover and Phase 4 deployment planning.

## 2026-10-28 — PR #21 Merge: Toast Placement Refinement Accepted

**Orchestrator decision: PASS / MERGED into main.** Reviewed head SHA `487de389c267f1e57e7d23973b84b44078e404fe` merged autonomously under orchestrator governance policy into `main` at `0bca517`. GitHub PR #21 ([#21](https://github.com/KAIYI7/settle-table/pull/21)) verified on hosted CI before merge. Post-implementation independent dual-axis code and UX review completed with unconditional PASS (Zero findings); 192/192 Python test suite methods passed in 83.9s; 11/11 automated real-browser CDP test stages passed in `tools/e2e_browser_test.mjs`; dedicated 5-case geometry and visual verification suite passed in `tools/capture_toast_evidence.mjs`; hosted GitHub Actions CI run `40625125967` succeeded on the exact reviewed head in `ubuntu-24.04` (Python 3.14).

| Gate | Disposition / Evidence |
|---|---|
| **Safe-Area Aware Bottom Viewport Anchoring** | PASS — Anchored `#alert-container` to viewport bottom with `bottom: calc(24px + env(safe-area-inset-bottom, 0px))` on desktop and `16px` on mobile. Achieved **541.0px clearance** on desktop (room card bottom: 185px, toast top: 726px) and **451.6px clearance** on mobile (room card bottom: 149.4px, toast top: 601px). Completely eliminates overlap with the `← Home / Room` breadcrumb navigation, room title, and Drafting status badge. |
| **Contextual Mobile Bottom Sheet Inversion** | PASS — Dual-layer CSS (`:has(.bottom-sheet-modal) #alert-container`, `body.has-bottom-sheet #alert-container`, `#alert-container.alert-container-top`) and JavaScript state synchronization in `syncAlertContainerPlacement()`. When a mobile bottom sheet modal is active, the toast automatically docks to the top (`y = 65–117px`), completely clearing modal footer actions (`Apply Equal Split`, `Clear All Claims`, `Done`). Touch targets for modal buttons remain 100% interactive and unblocked. |
| **Natural Directional Entry Motion** | PASS — Keyframe animations aligned to entry origin: `toast-in-bottom` (`translateY(12px) scale(0.98)` to `translateY(0) scale(1)`) for bottom toasts and `toast-in-top` (`translateY(-8px) scale(0.98)` to `translateY(0) scale(1)`) for contextual top-docked toasts, providing polished physical feedback. |
| **Responsive Wrapping & Rigid Touch Targets** | PASS — Long error messages (150+ chars) wrap cleanly via `overflow-wrap: break-word; word-break: break-word; min-width: 0;` with zero horizontal overflow (`bannerScrollWidth === bannerClientWidth` at 353px on 375px mobile viewport). Close button touch target enforced at rigid $36\times 36\text{px}$ with `flex-shrink: 0; touch-action: manipulation;`. |
| **Fixed Viewport Scroll Stability** | PASS — Under deep page scroll (`scrollY = 450px`), toast remains fixed at the viewport bottom (`y = 726–776px`, `inViewport: true`), with zero scroll jumping, layout shift (CLS = 0), or content displacement. |
| **Accessibility & Keyboard Dismissal** | PASS — Semantic ARIA roles preserved (`role="alert"` / `aria-live="assertive"` for errors; `role="status"` / `aria-live="polite"` for success). `Escape` keyboard dismissal verified with immediate event listener cleanup on dismissal to prevent memory leaks. |
| **CI Runner Stability Hardening** | PASS — In `tools/e2e_browser_test.mjs`, added `--disable-background-networking` and `--disable-default-apps` Chrome flags and extended connection polling to 300 attempts (30s), eliminating runner timeouts under high worker saturation. |
| **Financial & System Invariants Intact** | PASS — Zero backend changes (`settletable/calculation.py`, `settletable/authority.py`, and `settletable/transport.py` untouched); sen-level exactness and zero floating-point math preserved; Impeccable detect reports 0 anti-patterns. |

**Next scope:** Final stakeholder UAT walkthrough and Phase 4 deployment planning.





## 2026-10-28 — Bounded synthetic allocation authorization implementation readiness

Orchestrator decision: PASS for implementation of an opt-in local authorization-only integration; risk HIGH (authentication, authorization, concurrency and additive nonfinancial persistence). The owner approved this sole bounded feature and source publication; no public deployment or permanent credential provisioning. The reviewed contract fixes accepted Finalize consumption as amount authority and uses stable opaque references with a dedicated synthetic merchant/customer binding. Existing allocation and accepted command bytes remain invariant; no contribution/reimbursement/settlement effects, capture/refund or new financial schema. Independent source/security/adversarial review, failure/restart evidence using isolated stores, full local Python/browser regression and successful hosted exact-PR-head CI remain blocking delivery gates. Feature startup defaults disabled and local test infrastructure is disposable. Existing Internet release blockers remain. No phase-4 hosting work is authorized by this transition.


## 2026-10-28 — Optional allocation authorization simulation accepted (PR #22)

**Orchestrator decision: PASS / MERGED.** [PR #22](https://github.com/KAIYI7/settle-table/pull/22) merged with a merge commit after review and successful exact-head CI. Reviewed head `a1c82c8ed159fd1e5c2ddd89ae18d6d2f67e5b54`; merge `79d68548d65230755a5837b9debe071bd902cf3b`; premerge main `f0f58646e41ad3ccce207801b401cd72bd45e43f`. Actual merge parents and equality to the reviewed source tree were verified.

| Gate | Disposition |
| --- | --- |
| Financial and accepted-source authority | PASS: immutable accepted Finalize consumption supplies integer sen; allocation and command bytes remain unchanged; no contribution, reimbursement or settlement effect |
| Security and privacy | PASS: organizer-only initiation, organizer/self reads, reauthorization, server-only machine credential, fixed destination and disabled default; independent source/security/adversarial review accepted |
| Persistence, failure and recovery | PASS: real SQLite races and rollback; separate-process PostgreSQL/Kafka retries, cache expiry, lost-response restart, dependency outages and explicit restore write freeze |
| Local regression and UI | PASS: 213 Python tests, 21 focused simulation tests, 11 existing Chrome stages, explicit simulation browser journey, responsive controls and bounded GET polling |
| Hosted CI | PASS: [run 40649706607](https://github.com/KAIYI7/settle-table/actions/runs/40649706607), associated with the exact reviewed head, passed 213 Python tests and all 11 browser stages |
| Publication and cleanup | PASS: reviewed public source only; task-owned local processes, containers and disposable credentials removed; pre-existing resources preserved |

This completes the bounded, default-disabled local simulation milestone. Existing Internet release blockers remain. No public hosting, permanent account/credential provisioning, real payment or further feature is authorized by this transition.

## 2026-10-29 — Two focused independent-UAT UI corrections

**Orchestrator decision: PASS / MERGED** for [PR #23](https://github.com/KAIYI7/settle-table/pull/23). Risk MEDIUM overall (receipt quantity display Medium; capacity affordance Low). Scope is limited to existing rational display formatting and unavailable quick-assignment affordances, plus regression tests/evidence. [Verification](../../research/phase-3/uat-ui-corrections.md).

Reviewed source commit `3b24faa4bdd5a705854b4c31b2fa58d36597e69e`; final PR head `e00f914c49e04c72e13a57c58fc0cb70463a9cc7` adds evidence only and preserves reviewed production/test bytes. Premerge remote main rechecked at `76187b1fcb5e928e8f6cc78b3afc1c02477501ef`.

| Gate | Disposition |
| --- | --- |
| Receipt review display | PASS: actual DOM x1, x2, x3, x½, x⅓ before/after sealing and reload; unchanged authoritative receipt/line amounts |
| Allocation affordance | PASS: native disabled quick assignment at insufficient whole capacity, visible associated explanation, usable desktop/mobile Details / Split, reallocation and persistence after reload |
| Scope and authority | PASS: existing financial engine, authorization, revision conflict recovery, persistence and finalization/native confirmation implementation untouched; unknown UAT database/listener and unrelated resources preserved |
| Independent reviews | PASS: separate standards/source and specification reviewers report zero findings; independent focused Chrome rerun passes |
| Full local regression | PASS: post-review rerun 213 Python tests in 50.797s and all 12 real Chrome stages; 1280 × 900 / 375 × 667 focused visual evidence inspected |
| Hosted exact-head CI | PASS: [run 40820110948](https://github.com/KAIYI7/settle-table/actions/runs/40820110948), check head SHA equals final PR head; logs confirm 213 Python tests and 12 browser stages pass |
| Final diff/base recheck | PASS: actual hosted PR diff reviewed, production/test bytes equal independently reviewed source; remote main and branch refs unchanged before authorization |

Merge commit `449dc8c2322c7b64a429e28db8290da38f141975` was verified on remote main. Its parents are exactly the premerge main and reviewed PR head above, and its tree `53f9483d653160805ca9792d5d3121d2b2c62356` equals the final reviewed PR-head tree. This decision closes only the two corrections. The original independent UAT remains incomplete: its blocked and untested scenarios require a separate independent retest in a confirmed isolated environment. No public-release, deployment or further feature scope is authorized.
