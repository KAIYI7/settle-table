# Disposable transaction validation

2026-10-16, Asia/Kuala_Lumpur. **Advisory evidence; the main orchestrator alone evaluates project transitions.** Question: can a single-host SQLite authority atomically accept a financial edit and its immutable replay result, reject stale concurrent edits, reconcile before finalization, and recover committed results after reconnect?

## Experimental evidence

**20 checks passed, zero failed.** [Source](experiments/transactions/probe.py), [results and final state](experiments/transactions/results.json), [run guide](experiments/transactions/README.md). Python 3.14.6, linked SQLite 3.50.4; actual configuration `journal_mode=wal`, `synchronous=2` (FULL), `foreign_keys=1`.

Source SHA-256: `3a74a95997dfeeba28465a7800b3a2b6e78cc261e003e51d4ad7759e83156cfb`. Recorded run: `DISPOSABLE-transactions-7d1a229062f94a0cabbc5c5b8071409f.sqlite`. This is a fresh real file under the experimental directory, never an in-memory lock or shared in-memory database. Re-running creates another unique scratch file and updates the result record; prior files remain untouched. No Phase 1 result was modified.

| Exercised behavior | Observation |
|---|---|
| Actual competing connections | Connection one holds `BEGIN IMMEDIATE`; zero-timeout connection two receives a locked error. After rollback, the same second connection can acquire the transaction. |
| Concurrent stale claims | Two threads independently open connections, synchronize before issuing two claim commands against revision 0, then each executes `BEGIN IMMEDIATE`. Exactly one accepts; the other reads the now-current revision and conflicts. One claim and one revision increment persist. An explicit retry against current revisions preserves both diners' claims. |
| Command identity/replay | Accepted command body/digest/result are committed with its financial state. Replaying an old command returns the exact stored JSON string even after a newer revision; no extra mutation occurs. Same actor/meal/command ID with an altered body rejects. Accepted command rows have update/delete-aborting triggers. |
| Atomic failure | Injected exceptions after financial writes and after result insertion both cause explicit rollback. State and command table equal the entire pre-attempt snapshot; the connection exits its transaction. A capacity error after deleting the old claim restores that old claim. |
| Finalization | Unassigned quantity and a deliberately mismatched authoritative total separately block finalization and leave no accepted result. One 1001-sen dish shared equally finalizes as A=501, B=500 using integer largest remainder and alphabetical tie breaking. Shares sum exactly to the authoritative total. |
| Restart/reconnect | After closing the connection, a separate fresh Python subprocess reads the exact committed finalization result. A new connection replays that exact stored result despite the command's now-stale expected revision. No network delivery or OS crash was simulated. |
| Money boundaries | Application input rejects `True` and `1.5` as invalid money; invalid probes do not alter data. A direct fractional update to the STRICT INTEGER column also fails. Every accepted money value remains integer sen. The experimental 10^9-sen bound is not a final product policy. |
| Actual transfer identity | A synthetic already-confirmed 200-sen transfer submitted through two different command/suggestion batches creates one actual-transfer row. Reusing that actual ID with 201 sen conflicts. This selects no real payer/recipient consent policy. |
| Subsequent edits | A later accepted edit invalidates finalized status while retaining the actual transfer. The domain experiment remains the evidence for full correction/refund arithmetic; this small probe only checks stored-fact preservation. |
| File check | `PRAGMA integrity_check` returns `ok`. This is not a comprehensive durability/security certification. |

**Important scope distinctions:** this probe persists only accepted outcomes. It does not promise replay of rejected-command error responses after state changes. Whole-meal revision checks are deliberately conservative, so independent-item parallel acceptance is not established. The transfer command is an explicitly synthetic import of an already-confirmed fact, not a settlement authorization endpoint.

## Current documentation facts

Context7 resolved SQLite to `/websites/sqlite_docs` (official primary documentation, High reputation); three scoped queries addressed transaction isolation/durability, strict typing and same-host WAL. Sources accessed 2026-10-16. Documentation describes current SQLite generally; the executed runtime is explicitly the version above.

- `BEGIN IMMEDIATE` acquires a write transaction immediately; it can fail with `SQLITE_BUSY` when another writer holds it. SQLite serializes writers. A successful transaction start does not eliminate the need to handle other I/O/constraint failures and rollback. [Transactions](https://www.sqlite.org/lang_transaction.html), [isolation](https://www.sqlite.org/isolation.html), [result codes](https://www.sqlite.org/rescode.html).
- WAL supports concurrent readers with one writer, and requires all direct database processes on the same host. It is not appropriate to share the SQLite file between remote diner devices or across a network filesystem. A server may mediate remote requests while keeping database access local. Long readers can prevent complete checkpoints. [WAL](https://www.sqlite.org/wal.html), [network use](https://www.sqlite.org/useovernet.html).
- `synchronous=FULL` in WAL adds a synchronization operation on each commit. Filesystem/hardware behavior still matters; successful exception/reopen experiments do not prove power-loss resilience. [PRAGMA synchronous](https://www.sqlite.org/pragma.html#pragma_synchronous).
- STRICT INTEGER losslessly coerces some values; it does not prove the original JSON input was an integer. SQLite represents booleans as integers. Keep explicit type validation at the application boundary, not just a database declaration. [STRICT tables](https://www.sqlite.org/stricttables.html), [Boolean representation](https://www.sqlite.org/quirks.html#no_separate_boolean_datatype).

## Conclusions and material limitations

**Conclusion:** the transaction shape is feasible for a bounded, single-host authority: validate/reconcile inside a short write transaction, atomically store accepted state and its command result, then acknowledge/broadcast after commit. Reconnect should retrieve/replay committed identities rather than blindly reapply the client's last proposed state. A unique actual-transfer identity belongs to a financial fact, independently of suggested payment plans. This is sufficient evidence to consider SQLite for a small local first slice, subject to the other orchestration gates.

**Not established:** production authentication/authorization, session revocation on replay, network reconnect/stream recovery, multi-process stress or realistic throughput, real phones, disk-full/SQLITE_BUSY retry policy, process kill, OS crash/power loss, filesystem corruption recovery, backup/restore, schema migration, horizontal scaling, full charge/discount/rational-quantity rules or settlement consent. No latency/throughput claim is made. Database triggers prevent accidental update/delete through this schema; they do not defend against a privileged database administrator or a modified schema.

**Production obligations if selected:** keep the file on persistent local storage behind an authenticated authority; recheck current authorization even when replaying a saved result; bind command identity to actor/meal and compare the immutable body; use bounded lock waits and explicit retry/conflict responses; keep image inference and network calls outside the write transaction; fetch authoritative state after gaps; preserve actual financial facts across revisions; implement backup/restore and operational checkpoint monitoring before deployment. Reject a multi-replica/shared-file deployment unless its storage and single-writer design are separately validated.

**Gate recommendation for the main orchestrator:** PASS for this narrowly stated real-file transaction/replay/finalization feasibility question. CONDITIONAL for use in a local implementation slice with the above obligations and reviewed specification. No release or deployment approval follows from this experiment, and no phase transition is authorized by this delegated report.
