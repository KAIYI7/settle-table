# Independent authority specification challenge

2026-10-17. Reviewed actual [.scratch/authoritative-draft/SPEC.md](../../.scratch/authoritative-draft/SPEC.md), SHA-256 `7228d8c3245baa868a3d1aeb65c8374476a967586afb6cdc664370972b5f41ec`, against confirmed requirements, glossary, accepted calculation interface/source and MVP C1–C4. No implementation, Git mutation, external request or phase decision was performed by this reviewer.

**Final recommendation: PASS for the revised bounded local specification, with A1–A5 resolved as recorded below.** Initial review recommended CONDITIONAL PASS pending A1–A4 and required A5 acceptance coverage; the findings are retained to explain the changes. The scope does not need HTTP/OAuth/Internet release gates to justify local implementation. The main orchestrator owns authorization. These are specification findings and attack scenarios, not observed vulnerabilities in an implemented authority.

## A1 — History exhaustion must not disable access revocation

**Verified wording:** accepted-command count is capped at 10,000 per meal and rejects with `resource_limit`; accepted access revocation also increments revision and persists its response. No exception/reservation is stated.

**Risk inference:** a diner repeatedly submits valid own-claim changes with fresh command IDs until the shared financial command budget is exhausted. If the cap covers all command kinds, the organizer cannot revoke that session/membership immediately. Expiry eventually limiting access does not replace revocation.

**Blocking clarification:** preserve a bounded security-revocation path after the financial mutation budget is exhausted. For example, reserve additional capacity for first-time revocations of the fixed sessions/memberships, and reject already-revoked no-ops rather than letting arbitrary IDs exhaust the reserve. Keep current organizer authorization, atomic revision/result storage and history preservation. Choose the exact bounded rule as an engineering decision.

**Acceptance:** exhaust the ordinary command budget through valid financial commands; further financial writes fail without mutation, but both first-time session and membership revocation still commit and immediately deny subsequent snapshots/replays. Repeated no-op revocations cannot grow history indefinitely. No pruning of prior accepted facts.

## A2 — Make permission-before-replay unambiguous

**Verified wording:** transaction step 2 checks current session verifier, expiry, revocation, meal binding and membership before replay. Step 4 applies “permission” only to new commands. Accepted identity is correctly `(meal, participant, command)` rather than the caller's submitted actor.

**Risk/limit:** fixed roles and prohibited handover reduce the immediate exploit surface in this v1. Nevertheless, “current access” must not accidentally become “any active member can obtain a previously privileged result” when later role/session behavior changes.

**Blocking clarification:** resolve command kind and verify the session-bound actor's **current command permission** before accepted-result lookup on every `apply`. Exact replay bypasses stale expected revisions and post-finalization write restrictions; it does not bypass session, membership or role permission checks. No client actor/role field may participate in deriving authority.

**Acceptance:** a diner cannot issue/replay organizer command kinds, even using a known organizer command ID; another participant cannot retrieve that command through an identity collision. Revoke-before-replay denies; replay-before-revoke may complete at its serialized authorization point. Authorized exact finalization replay remains available after finalization.

## A3 — Bound credential work before hashing or encoding

**Verified wording:** credential entropy/storage/expiry rules are strong, and command/result encoding is bounded. A separate raw credential type/length/encoding contract is absent.

**Blocking clarification:** select one exact finite immutable credential shape, validate it before encoding/hash lookup, and apply the same rule to `apply` and `snapshot`. A 32-byte value or 64-character ASCII hex representation of 32 random bytes is a sufficient local seam; this is an engineering choice, not an account policy. Invalid types/subclasses and huge/malformed input reject with secret-safe errors. Keep verifiers and raw credentials out of snapshots, saved replay results and diagnostics.

Also retain validation of every command's typed collections, IDs, text and rational bounds **before** canonical serialization or Fraction construction. The eventual HTTP pre-read limit remains separate; it is not required for this no-listener module.

**Acceptance:** oversized, non-ASCII/malformed and mutable credential inputs reject before the verifier/encoder dependency is invoked, with no write or echoed credential. Valid opaque credentials work after reopen and cease working at expiry/revocation.

## A4 — Snapshot authorization must share the returned read state

**Verified wording:** snapshots promise a consistent committed state after checking current session/membership. Writes explicitly define their transaction; reads do not specify the matching transaction/linearization point.

**Risk inference:** checking authorization outside the financial read transaction permits authorization from one committed state and returned data from another, particularly around membership revocation.

**Blocking clarification:** perform authorization and all snapshot reads in one SQLite read transaction/snapshot. Define the authorization/read linearization point and the trusted-clock expiry check there. A snapshot established before revocation may complete with that consistent state; a snapshot established after committed revocation must deny. Do not claim retroactive cancellation of already-authorized work.

**Acceptance:** two-connection interleavings show both legal orderings and prevent mixed-version authorization/financial state. Ordinary snapshots contain no raw session/verifier fields or unrelated meal data.

## A5 — Pin the pending-claim capacity behavior in tests

**Verified current design:** only current-financial-basis confirmed quantities consume capacity. Old claims remain visible/pending, block finalization and require their own diner to reconfirm or release. That is an explicit conservative finalization gate, not permission to discard another diner's claim.

**Required coverage:** after a receipt edit, another current claim can consume capacity while old claims remain pending. A failed reconfirmation must preserve the old pending fact and response history; it must not delete it before rejecting. An explicit own release must be possible at current revisions even when the pending quantity no longer fits. Finalization remains blocked until all pending claims resolve. Snapshot diagnostics must make pending and confirmed/reserved quantities distinguishable.

This design does not promise that pending quantities reserve capacity or that every old diner can reconfirm immediately. State that consequence explicitly; do not let an implementation invent reservation, silent ownership transfer or organizer override. No diner removal/recovery policy is selected by this review.

## Supported composition and capability limits

- Actual accepted `calculate` must run inside the same transaction as current review/revision checks, final state and accepted response. The spec already requires this; the existing calculator/SQLite/browser probes separately cannot prove the composed module.
- Review may precede assignments, but finalization requires current authenticated receipt attestation, complete quantity claims, all signed scoped components/included-tax semantics and exact authoritative total. A stale stored calculation or supplied `reviewed=True` cannot substitute.
- Distinct-item acceptance, receipt-edit invalidation, immutable command bytes/results, restart replay, rollback failpoints and actual 1001/3365/one-sen fixtures are appropriately required. Maintain strict integer money and exact bounded rational claims throughout persistence/hydration.
- Trusted local provisioning and fixed participants are honest restrictions. This module cannot yet claim private Internet identity/invitation UX, account recovery, origin/CSRF defenses, production load, backup/restore, image retention or settlement consent. Those remain later capability-specific gates, not reasons to demand the complete product before a local module.

No user phase confirmation is needed for these technical clarifications. Record their resolution and revised acceptance cases, then let the orchestrator decide whether the local implementation scope is ready.

## Resolution review

The orchestrator revised the specification while this report was being completed. This reviewer read the actual new rules and acceptance cases, not only the summary. Revised specification SHA-256: `5c872c197a0287aa350ab29ff421b18ac5f85d101453997ea152c25e1476384f`.

| Finding | Revised contract | Review |
|---|---|---|
| A1 / security quota | Ordinary financial history cap excludes a bounded reserve for first-time session/member revocations; repeated fresh-ID revoked no-ops reject without history growth. New acceptance case 20 covers exhaustion and both revocation types. | PASS |
| A2 / permission-before-replay | Transaction step 2 checks current command-kind/target permission before replay lookup. Exact replay bypasses stale revision/finalized-state business checks only. | PASS |
| A3 / credential bound | Exact 43-character ASCII base64url credential shape from 32 random bytes; type/size/alphabet checks precede hashing, encoding and database work. New case 19 covers malformed input without disclosure. | PASS |
| A4 / snapshot coherence | Current session/membership, trusted authorization time and returned financial state share one SQLite read transaction/snapshot; revocation ordering is explicitly bounded. Case 19 covers the interleaving. | PASS |
| A5 / pending claims | Current-basis claims reserve quantity; pending claims stay visible/blocking, can be explicitly released at current revisions, and cannot be deleted through receipt replacement. Case 20 covers release/reconfirmation without displacement. | PASS |

No blocking specification clarification remains from this review for this narrow local module. Implementation acceptance still requires actual integrated authorization/replay/finalization/rollback tests and independent source review. This PASS neither establishes those unexecuted results nor authorizes a transition on the orchestrator's behalf.

After this review, the orchestrator changed the specification's status/completion paragraphs and added decision/review links to record its own readiness decision. The reviewed behavioral contract and20 acceptance cases were unchanged by that metadata update; the SHA above identifies the pre-decision reviewed version.
