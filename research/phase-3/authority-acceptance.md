# Authoritative-draft implementation acceptance

Started2026-10-17 on `feature/authoritative-draft`, from main `7db4ef155149526f6c646158814d1851b5fdb21b`. **Orchestrator decision: PASS / accepted for the bounded local authority slice.** This is internal acceptance on the feature branch, not merge or release of the complete application.

## Scope and test seams

Implement the [reviewed specification](../../.scratch/authoritative-draft/SPEC.md), without broadening it. Trusted local bootstrap, authenticated snapshot and authenticated command application are the public test seams. The orchestrator selected these seams under existing governance; no routine user confirmation is needed. Tests use real disposable SQLite databases and independent connections, exact integer sen and bounded exact rationals. Security inspection of database bytes and explicitly injected transaction failures supplements public-interface checks.

The accepted calculator must remain byte-identical to baseline SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`. Its15 tests must continue to pass. No HTTP, UI, invitation redemption, settlements, images/OCR, Notion, deployment or external data belongs to this slice.

## Material gates

| Gate | Current evidence/status |
|---|---|
| Small red→green implementation increments | PASS — [implementation log](authority-implementation-log.md), separate capability commits and actual failing/passing observations. |
| All20 specification acceptance scenarios | PASS — [twenty-case mapping](authority-adversarial-review.md), inspected against all four authority test files. |
| Actual calculator/SQLite/access/review integration | PASS — real `calculate` runs before the single state/result commit; literal334/667,3365, included-tax600/34 and one-sen discount examples pass. Calculator source remains unchanged. |
| Concurrent independent connections, reopen/fresh process, injected rollback | PASS — barrier/event-coordinated races, both revocation orders, coherent snapshots and reopen/replay; no OS crash/power-loss claim. |
| Credential nonleak, permission-before-replay, revocation and bounded inputs | PASS — independent [security review](authority-security-review.md), actual10,000 ordinary-command exhaustion then both revocations, safe input/dependency errors and token-free storage/results/logs. |
| Independent actual-source/specification review | PASS — [adversarial review](authority-adversarial-review.md) and security review pin final source; main read actual source, tests, interface and reports, including original findings/resolutions. |
| Branch publication and PR | PASS — [PR #1](https://github.com/KAIYI7/settle-table/pull/1) open against main; actual remote feature head verified. Main remains `7db4ef155149526f6c646158814d1851b5fdb21b`; annotated checkpoint target remains `69895457d9e3524c90df24f3a21c284ea70cef6c`. Later documentation commits may advance the feature head without changing tested source. |

## Coordinator execution and resolved findings

`python -m unittest discover -s tests -v`: **60 tests PASS in195.536 seconds**, Python3.14.6 / SQLite3.50.4. Breakdown:15 implementation,20 adversarial,8 security,2 coordinator validation and15 existing calculator methods. These are functional checks, not statistical coverage or a throughput estimate. [Exact hashes and run record](authority-verification.json).

The complete run loaded the review tests before a final diagnostic-only change: credential/verifier leak assertions now use fixed safe failure messages instead of printing their compared data. Predicates and scenarios are unchanged. Main reran all20 adversarial methods (1.733s) and the7 non-quota security methods (0.421s) against these final files; no redundant third quota run was needed. The actual quota ran in both the independent security workstream and the main complete suite.

Material original findings remain visible: rollback/close failure containment (S1), incorrect postcommit rejection (A1), unsafe trusted-clock diagnostics (S2). Each was fixed and retested. Implementation additionally closed hook diagnostic/entropy failure and invisible-label validation gaps. No material finding remains open. No reference-app source or calculator changes were required.

## Assumptions and unverified boundaries

Trust the local host, bootstrap caller, database owner and clock/fault dependencies; this is not Internet identity. Fixed participants and one expiring session each have no renewal/recovery. A lost bootstrap acknowledgement can leave credentials unrecoverable; automatic reset is excluded. Revoked financial identities/claims remain and may block later corrections. Ordinary state is limited to900,000 bytes to reserve revocation headroom below1MiB.

The real encoded-command limit was exercised through valid individual fields/counts. Accepted-response size rejection used an explicitly documented serialization fault with the real1MiB bound, not a naturally maximal receipt. Power-loss/process-kill durability, backup/restore, large natural-result capacity, load, phone/client behavior and operational account security remain unverified. These block their later capabilities, not this tested local module. No HTTP/UI/invitations/settlements/OCR/Notion/deployment was added.

## Documentation consulted

Current Python documentation was fetched through Context7, resolving `/python/cpython` and querying explicit SQLite transaction control. Source: [CPython sqlite3 documentation](https://github.com/python/cpython/blob/main/Doc/library/sqlite3.rst), accessed2026-10-17. `isolation_level=None` under legacy transaction control disables implicit transactions and permits explicit SQL `BEGIN`/`COMMIT`/`ROLLBACK`; `timeout` bounds lock waiting. `executescript` can implicitly commit, so it must not run inside the atomic command transaction. This documents the implementation choice, not successful execution evidence.

Remaining operational exclusions: the module does not establish real Internet identity, remote invitation/recovery, production backups, throughput, phone behavior or full application readiness. Product-policy questions remain gated by their later features.
