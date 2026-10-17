# Independent authoritative-draft security review

2026-10-17. **Independent source/security review: PASS for the bounded local slice; no material finding remains open.** The orchestrator's final whole-suite run and acceptance decision remain separate gates. This review does not authorize a phase transition or public release.

Reviewed the [bounded specification](../../.scratch/authoritative-draft/SPEC.md), [prior independent specification challenge](authority-spec-review.md), [accepted calculator interface](../../docs/calculation-interface.md) and [governance](../../docs/agents/governance.md). This reviewer owns no production implementation and cannot authorize slice acceptance. No security PASS is implied by the earlier specification review.

## Review plan

- Validate the exact bounded credential type/alphabet before encoding, hashing or database access. Probe malformed/oversized/subclass inputs and secret-safe rejection.
- Verify 32-byte random issuance, domain-separated verifier-only persistence, expiry and binding. Inspect actual temporary SQLite bytes and results for raw credentials; capture logs/errors without publishing secrets.
- Challenge current session, membership and command permission before accepted-result replay. Test identity collisions, changed envelopes, revoked/expired replay and organizer-only commands from a diner.
- Inspect one-transaction snapshot authorization/state reads, serialized independent-connection writes, atomic state/result rollback, safe storage errors and recovery.
- Exercise strict frozen/tuple inputs, booleans/floats/foreign IDs and bounded canonical/rational/text handling before expensive work.
- Exhaust the ordinary financial-history limit and verify first-time session/member revocations remain possible through the finite security reserve.

Final reviewed [authority source](../../tabwise/authority.py) SHA-256: `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`. Independent [security tests](../../tests/test_authority_security.py) SHA-256: `f96391f17293aa84a53bcbdbbd82ea82d396fba149e9613841e7ff566529024c`. The reviewer read the actual complete implementation incrementally, then the final changed hunks, not only implementer summaries. No external services, private receipts or real accounts are part of this review. Temporary databases and session values remain disposable local test data.

## Incremental evidence and findings

Initial bootstrap/snapshot increment (`8ce31c3`): independent tests in [test_authority_security.py](../../tests/test_authority_security.py) pass for exact credential type/size/alphabet rejection before a patched hash dependency and closed database, hidden bootstrap representations, and domain-separated verifier-only persisted storage. SQL dump and raw temporary database bytes are checked without printing token values. Command acceptance is not yet implemented at this checkpoint, so these results do not establish replay/finalization security.

**S1 — material, rollback failure containment (resolved).** Initial `_rollback` executed SQLite rollback without its own error guard; public exception paths called it before returning a safe error. A rollback I/O/closed-connection exception could therefore escape as an underlying SQLite exception and the connection could remain in an uncertain transaction. Reported promptly to the orchestrator. The implementation now guards rollback, detaches an unusable handle before attempting close, and contains cleanup exceptions. The independent regression injects rollback and close failures around a real temporary SQLite transaction: public `storage_error` suppresses underlying context, the connection is discarded, reopen shows revision0 and history0. This is injected-storage evidence, not a demonstrated ordinary filesystem incident or power-loss proof.

The review test's initial Windows cleanup failure was a test harness defect: `with sqlite3.connect(...)` controls transactions but does not close the connection. The independent inspection now uses `contextlib.closing`; rerun: **2 tests PASS**. No product behavior was changed for that harness correction.

Incremental source inspection verifies that all SQL values are parameters; caller actor/role fields are unsupported; frozen typed commands/tuples are checked before canonical serialization; current joined session/membership and command permission precede accepted-command lookup; and snapshot authorization and returned facts share a read transaction. An independent SQLite trace probe confirms diner permission denial occurs before any replay lookup and captures no raw credential. The trace remains transient test memory and is never a published fixture. The production module registers no logger/trace callback and imports no network, OCR or Notion capability.

Root's strict-work-order challenge identified rational comparisons preceding normalized numerator/denominator bounds. The current implementation checks those bounds before rational comparison/construction; this was a specification-conformance hardening, not a successful credential/authorization attack. Ordinary state is limited below the canonical wire ceiling to leave revision headroom for security revocations. Both hardenings will be covered by the final independent source hash and full suite.

**S2 — safe dependency-error consistency (resolved).** Source inspection found that `_now` invoked the trusted clock directly. A clock callback raising `AuthorityError` with arbitrary private diagnostic text would therefore be mistaken for an intentional domain rejection and rethrown unchanged. This is a trusted dependency failure, not an untrusted caller's privilege escalation. Reported to the orchestrator with the request to normalize callback exceptions, consistent with hook/entropy hardenings. The final source catches callback exceptions and raises stable `storage_error` with display context suppressed. This reviewer read the new public snapshot/apply regression and independently reran `python -m unittest discover -s tests -p test_authority.py -k clock -v`: **1 PASS**. Both failures preserve revision0 across reopen. The implementer's separate red→green run is recorded in its implementation evidence; this review independently verified the green state.

## Executed independent evidence

`python -m unittest discover -s tests -p test_authority_security.py -v` ran the initial five methods in **112.408 seconds, PASS**. The expensive test accepted exactly10,000 ordinary public commands (one receipt plus9,999 own-quantity edits), without direct history insertion, quota overrides, durability changes or history pruning. The next financial command returned `resource_limit` without mutation. First-time session and membership revocations then both committed; SQL inspection found10,000 ordinary plus2 security rows. Revoked diner replay denied, repeat fresh-ID revocations rejected without growth, exact authorized revocation replay stayed identical, and claims/participants were preserved. Full SQL dump and raw database bytes contained no raw credential.

After additional probes, the six non-quota methods passed together in0.365 seconds. A further parameterized diner-permission/actor-injection method passed independently. All eight current security methods have therefore executed successfully across these explicitly partitioned runs; this is not a claim that all eight ran together against the final hash. These are functional attack/regression checks, not statistical coverage estimates. The orchestrator will run the entire final suite once after source freeze, including the real quota experiment. The final clock delta does not alter successful-clock, replay, quota or revocation semantics.

Additional executed probes cover:

- Both `snapshot` and `apply` reject huge, wrong-type/subclass, non-ASCII, invalid-alphabet and surrogate credentials before a patched verifier hash or closed database is reached.
- A real finalization produces A334/B667 for quantity1:2 of1001sen, survives close/reopen and exact replay, emits no stdout/stderr, and exposes neither raw credentials nor verifier encodings in ordinary snapshots/results/canonical response bytes. All temporary database/sidecar files are checked for raw credentials.
- Entropy-source failure becomes a safe storage error with no committed meal. Grant representations hide the raw values; verifier-only storage is domain-separated and matches independently calculated SHA-256.
- All five organizer-only command kinds deny a diner, actor/role/`reviewed` dictionary injection rejects, and neither failure creates command history or advances revision.

## Capability limits and remaining risk

The database path, local bootstrap, clock/hook and privileged Python host are trusted. This review does not claim protection from a database administrator, arbitrary host code or a caller who deliberately copies a secret into ordinary domain text. The module itself must never serialize/log its separate credential argument or verifiers in ordinary responses.

No Internet identity, credential renewal/recovery, invitation redemption, HTTP defenses, secure account storage, production exposure, performance capacity, backup/restore or OS-crash durability is established. A bootstrap commit whose acknowledgement fails may leave a committed meal whose one-time raw credentials were never received; reset/renewal is deliberately unsupported, so this bounded local engine cannot yet serve as an operational session product. No destructive automatic reset should be inferred from that limitation. Private data, real accounts, network calls and paid services were not used.
