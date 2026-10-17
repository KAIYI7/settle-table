# Authoritative draft adversarial review

Completed 2026-10-17 against [bounded specification](../../.scratch/authoritative-draft/SPEC.md), on `feature/authoritative-draft`. **PASS for this independent source/spec/adversarial review of the bounded local slice.** Only the orchestrator accepts the slice; the separate security review and final integrated suite remain their own gates. One material finding, A1 below, was fixed and independently retested.

## Agreed seams and scope

Test trusted local bootstrap, authenticated `apply` and coherent `snapshot` through their actual public immutable interfaces. Exercise separate real SQLite connections and reopen/fresh-process recovery. Inspect disposable SQLite bytes only for the explicit no-credential-persistence requirement; exercise the documented transaction-failure seam for atomicity. Do not add production APIs, network endpoints or a replacement rounding implementation.

## Challenge plan

| Invariant | Independent challenge | Status |
|---|---|---|
| Current authorization precedes replay | Replay accepted claim after session/membership revocation; wrong-meal and expiry | PASS, both revocation kinds and forced serialization orders |
| No same-item lost update/overclaim | Race independent connections at identical item/financial revisions; fresh overcapacity retry | PASS, barrier-synchronized public test |
| Distinct-item concurrency | Concurrent current-item edits accept despite unrelated global revision | PASS, independent connections |
| Immutable replay identity | Changed payload/expected revision rejects; old exact replay retains original response | PASS, byte equality and original/current revision distinction |
| Atomic finalization | Race finalization against claim/receipt changes; compare literal calculator totals | PASS for both race types, actual calculator A334/B667/O0 |
| Atomic failure and uncertain response | Fail after mutation/result insertion; reopen/retry one identity without duplicate mutation | PASS for replacement and actual-calculator finalization |
| Recovery | Close/reopen and fresh Python process recover saved response | PASS for receipt replacement |
| Credential secrecy/bounds | Malformed credential before storage work; response/persistence/log scans | Public bounds PASS; source/storage review separate |
| Pending claims | Financial edit, release/reconfirm, no pending priority/displacement | PASS for current claim capacity and pending release |
| Security revocation reserve | Ordinary quota exhaustion cannot block either revocation | Source/test reviewed; execution belongs to independent security report |

## Findings and limitations

**Red evidence:** the first bootstrap/credential-boundary tracer test was added after the public interface was agreed in `docs/authority-interface.md`. On2026-10-17, `python -m unittest discover -s tests -p test_authority_adversarial.py -v` failed at import with `ModuleNotFoundError: tabwise.authority`; the production module did not yet exist. This is missing-capability evidence, not an implementation defect or passing functional result.

**Green evidence:** after the first production increment, the same command passed the first test in0.050s. It checks original draft visibility/overwrite refusal, malformed credential type/size/alphabet, wrong-meal denial, unchanged snapshot and no credential in snapshot representation. Disposable databases use ignored `.local/tests/` so sandbox file access and Windows handle cleanup are explicit. Later command types are imported only once implemented, keeping this tracer independent of future capability.

The bootstrap challenge then expanded to exact expiry-boundary denial and separate-meal isolation, plus injected `after_state` failure followed by successful same-ID bootstrap on a fresh connection. **Three tests pass in0.208s**; the failure leaves no unrecoverable meal. No source defect found in this increment.

**Receipt/replay increment:** five tests pass in0.479s. Independent real connections inject failure after receipt-state update, after accepted-result insertion and before commit: original snapshot remains equal on both connections, and the previously failed command identity subsequently accepts once. An `after_commit` response failure returns `commit_uncertain`; identical retry returns revision1. A fresh Python process (credential passed only over stdin, never process arguments or persisted fixtures) recovers byte-identical saved response and revision1. No production defect found in this increment.

**Claims increment:** eight tests pass in0.734s. Barrier-synchronized workers each open/close their own actual connection. Same-item revision racing yields one acceptance and one `item_revision_conflict`, irrespective of winner identity; fresh overcapacity retry leaves the original claim intact, then smaller available quantity succeeds. Distinct unchanged items both accept without a global-revision requirement. Receipt correction leaves prior claims pending; a pending owner cannot displace the new confirmed owner, can release explicitly, and cannot delete the claimed line. Exact old replay keeps its original bytes without mutating current pending/current state.

### A1 — postcommit public exception misclassified (material; resolved)

**Verified defect:** source `bootstrap`/`apply` catch `AuthorityError` before the generic postcommit-classification branch. An `after_commit` hook raising `AuthorityError("injected")` rethrows that ordinary error despite state and accepted response having committed. Independent regression `test_postcommit_public_error_still_reports_uncertain_not_rejection` failed: observed `injected`, expected `commit_uncertain`; nine-test run had eight passes/one failure. Reported to orchestrator and implementer before production changes. This requires correcting exception classification, not weakening the regression.

Bootstrap has the same catch-ordering issue. Its dedicated regression also asserts that aftercommit loss does **not** permit same-ID provisioning/reset on reopen: the meal exists and raw credentials are intentionally unrecoverable. Session reissuance/recovery remains excluded; the module must describe this local lifecycle limitation rather than invent a recovery policy.

**Resolution verified:** implementer changed both public-error branches to check committed state and report `commit_uncertain`. Both independent postcommit regressions now pass; bootstrap reopen refuses same-ID reissuance. The original failing evidence above is retained.

**Finalization increment:** fourteen independent tests pass in1.203s. Simultaneous finalization versus claim or receipt edit accepts exactly one current mutation; the outcome is either the original reviewed financial basis finalized or a newer draft with no stale calculation. Literal consumption is A334/B667/O0 from the accepted1001-at-1:2 case. Failure after actual-calculator state mutation, result insertion and before commit restores the complete reviewed draft; reopen preserves the exact final result and replay bytes.

**Response-size boundary, explicitly injected:** after state mutation a trusted hook temporarily replaces only the serializer adapter for an accepted-result object, adding >1MiB test padding before invoking the **unchanged real serializer and1MiB bound**. It returns `resource_limit`, rolls back state/history, and the same identity later accepts normally. This proves the real size-rejection/transaction reaction; it does **not** claim a natural maximum-size receipt/result was exercised. The orchestrator explicitly authorized this targeted test seam before the test was written; ordinary public behavior tests do not patch internal collaborators.

## Final independent source review

Reviewed the complete [production module](../../tabwise/authority.py), not only its tests: frozen typed vocabulary, validation/canonicalization, bootstrap, access lookup, coherent snapshots, receipt/claim/review/finalization handlers, revocations, command replay and all cleanup/error branches. Final SHA-256: `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`. The final trusted-clock exception-normalization delta was read after the earlier full-module review; it suppresses callback diagnostics before public `storage_error`. The [accepted calculator](../../tabwise/calculation.py) remains unchanged at SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`.

- Credential format/type is checked before hash/database work; only a domain-separated verifier reaches SQLite. Actors and organizer permissions derive from joined current persisted session/membership. Public command types provide no actor/role/target-person claim fields.
- `snapshot` uses one explicit read transaction for authorization, financial state and membership observations. `apply` uses `BEGIN IMMEDIATE`; authorization and command permission precede replay lookup. Canonical bytes **and** digest must match an accepted identity; old exact replay is returned before current business-revision/finalized checks.
- Same-item capacity excludes the caller's previous claim and includes only current-basis confirmed claims. Mutation occurs after capacity validation. Corrections preserve pending claims, invalidate review and retire removed source IDs; retained claims block deletion.
- Receipt-only review checks source facts/components without inventing allocation. Finalization hydrates the accepted `calc.Meal`, calls actual `calc.calculate` within the same write transaction, and writes calculation/state and accepted result before a single commit. No alternate apportionment code was introduced.
- The real bounded serializer runs on result bytes before command insertion and commit. History has no ordinary update/delete path. Revocation changes one fixed binding once, leaves financial identity/claims untouched, bypasses ordinary history quota and retains bounded state headroom.
- Precommit failures roll back; cleanup failure discards the connection. Postcommit hook/public/dependency failures report uncertainty. SQLite error values, paths, commands and credential values are not interpolated into public errors; SQL values are parameterized. The imports/call graph add no network, OCR, Notion or external account capability.

**Conclusion:** no remaining material defect found in this reviewed scope. Current restrictions are substantive: fixed participants/one session each, local trusted provisioning/clock/database owner, quantity-only collaborative claims, and no finalized correction/session recovery/network identity. They cannot be presented as complete Internet authentication or a finished application.

## Final execution and twenty-case mapping

[Independent tests](../../tests/test_authority_adversarial.py) SHA-256 `cf8687d40a8c7dfcd0e7aaf812d9c06384b008edc8c789c50f7551fa79239721`: `python -m unittest discover -s tests -p test_authority_adversarial.py -v` — **20 tests PASS in1.957s** on the final source hash. Barriers/events coordinate starts/serialization without sleep-based winner assumptions. The snapshot during uncommitted revocation returns one old committed active/revision basis; a later snapshot is denied. Both claim-first and revoke-first orderings are forced and checked. Unknown monetary values remain `None`; a known zero-price line still requires an explicit complete assignment.

Also independently executed during review: all15 calculator tests PASS, the two coordinator validation tests PASS, and14 authority tests PASS before the final clock-only delta. The implementer reports its added clock regression separately; the orchestrator owns the final all-tests run. These counts are functional checks, not statistical coverage or a throughput claim.

The table maps **every numbered acceptance case** to actual test/source evidence. `A` = [adversarial tests](../../tests/test_authority_adversarial.py), `I` = [implementation tests](../../tests/test_authority.py), `V` = [coordinator validation](../../tests/test_authority_validation.py), `S` = [security tests](../../tests/test_authority_security.py). This reviewer inspected all four test sources; security-only execution evidence is in the [separate review](authority-security-review.md), not claimed as this reviewer's own rerun.

| Spec case | Concrete evidence |
|---|---|
| 1 bootstrap/incomplete/secrecy | A `bootstrap_isolation_and_credential_boundary`, bootstrap failure/reissuance tests; S `storage_contains_only_domain_separated_verifiers`, finalized-result nonleak test |
| 2 session denial/body injection | A expiry/wrong-meal and both revocation tests; S credential-prehash and diner/injection matrix |
| 3 organizer-only commands/own claims | S `diner_cannot_issue_any_organizer_command_or_inject_actor_role`; I own-claim set/release; source session-derived actor |
| 4 same-item concurrency | A `same_item_race_has_one_stale_loser_and_no_capacity_overwrite` |
| 5 distinct-item concurrency | A `distinct_item_race_preserves_both_claims_without_global_revision` |
| 6 immutable retry/collisions | A `changed_payload_collision_cannot_rewrite_an_accepted_claim`; receipt/finalization saved-byte replay and reopen |
| 7 revocation/replay order | A both revocation kinds plus deterministic `revocation_first...` and `claim_first...` |
| 8 rollback/capacity restoration | A receipt/finalization precommit failures and same-item capacity test; S failing rollback/close containment |
| 9 reopen/fresh process/uncertainty | A `uncertain_response_retry_survives_fresh_process_without_duplicate`, finalized result reopen |
| 10 correction/pending/deletion | A pending-owner test explicitly rejects old financial basis, checks pending/current claims and claimed deletion; I correction test |
| 11 attestation/current basis | I review-before-claims and review preservation; V stale digest/mismatch; S unsupported forged shape |
| 12 actual1001 quantity allocation | A both finalization races and finalization rollback; I actual-calculator334/667 test |
| 13 incomplete/stale/mismatch | V unknown/mismatch/no-review/incomplete; A current review with pending claim blocks finalization, zero-price assignment rule; I actual calculator rejection |
| 14 included/scoped/discount examples | I included600/34, scoped3365/1683/1682, full one-sen discount tests; unchanged calculator tests |
| 15 strict input/bounds/identity | I `invalid_typed_facts_reject_without_mutation`; V real>1MiB command from valid individual bounds; S exact-type credential/injected-body tests; source exact shapes and count bounds |
| 16 finalization races/read-only | A both finalization race tests; I read-only financial command rejection and authorized finalization replay after reopen |
| 17 revocation preserves identity | A `both_revocation_kinds_deny_old_replay_and_preserve_financial_facts`; I repeated/self revocation rejection |
| 18 busy/storage/sizes/history | I actual held-write-lock bounded busy test; A pre/postcommit failures and explicitly injected real response bound; S real10,000-command reserve test; source no external work |
| 19 credential/read linearization | S prehash/closed-DB malformed credentials; A `snapshot_during_uncommitted_revocation_reads_one_old_committed_basis`, later denied read |
| 20 security reserve/pending rights | S actual ordinary quota exhaustion then both revocations/no-growth checks; A pending owner release/reconfirm without displacement |

No material gate is waived by this mapping. Natural largest-result capacity, real phone/client behavior, process/OS crash durability, multi-host storage, backup/restore and production security remain unverified/excluded. The real1MiB command boundary and full10,000-command history have dedicated tests; the accepted-response limit uses targeted injection instead of an unmeasured natural input claim.
