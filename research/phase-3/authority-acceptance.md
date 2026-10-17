# Authoritative-draft implementation acceptance

Started2026-10-17 on `feature/authoritative-draft`, from main `7db4ef155149526f6c646158814d1851b5fdb21b`. This record is incremental; **implementation acceptance is pending**.

## Scope and test seams

Implement the [reviewed specification](../../.scratch/authoritative-draft/SPEC.md), without broadening it. Trusted local bootstrap, authenticated snapshot and authenticated command application are the public test seams. The orchestrator selected these seams under existing governance; no routine user confirmation is needed. Tests use real disposable SQLite databases and independent connections, exact integer sen and bounded exact rationals. Security inspection of database bytes and explicitly injected transaction failures supplements public-interface checks.

The accepted calculator must remain byte-identical to baseline SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`. Its15 tests must continue to pass. No HTTP, UI, invitation redemption, settlements, images/OCR, Notion, deployment or external data belongs to this slice.

## Material gates

| Gate | Current evidence/status |
|---|---|
| Small red→green implementation increments | Pending; [implementation log](authority-implementation-log.md) will record actual failing/passing checks. |
| All20 specification acceptance scenarios | Pending; implementation and independent adversarial tests must map actual coverage and limits. |
| Actual calculator/SQLite/access/review integration | Pending; exact supplied examples and atomic accepted responses must be exercised. |
| Concurrent independent connections, reopen/fresh process, injected rollback | Pending; no OS crash/power-loss durability claim follows from these tests. |
| Credential nonleak, permission-before-replay, revocation and bounded inputs | Pending independent [security review](authority-security-review.md). |
| Independent actual-source/specification review | Pending [adversarial review](authority-adversarial-review.md), plus main artifact review. |
| Branch publication and PR | Pending successful acceptance; main and checkpoint tag remain unchanged. |

## Documentation consulted

Current Python documentation was fetched through Context7, resolving `/python/cpython` and querying explicit SQLite transaction control. Source: [CPython sqlite3 documentation](https://github.com/python/cpython/blob/main/Doc/library/sqlite3.rst), accessed2026-10-17. `isolation_level=None` under legacy transaction control disables implicit transactions and permits explicit SQL `BEGIN`/`COMMIT`/`ROLLBACK`; `timeout` bounds lock waiting. `executescript` can implicitly commit, so it must not run inside the atomic command transaction. This documents the implementation choice, not successful execution evidence.

Remaining operational exclusions: the module does not establish real Internet identity, remote invitation/recovery, production backups, throughput, phone behavior or full application readiness. Product-policy questions remain gated by their later features.
