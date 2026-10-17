# Authoritative draft implementation log

Scope: [reviewed local authority specification](../../.scratch/authoritative-draft/SPEC.md). Date: 2026-10-17. Calculator source is unchanged. Public test seams and dependency contracts are recorded in [authority interface](../../docs/authority-interface.md); the orchestrator selected these under delegated engineering authority.

## Incremental evidence

Implementation is in progress. Red/green observations are appended for each vertical capability; completion is not asserted until independent reviews and orchestrator gates pass. Tests use disposable SQLite files, fixed trusted clocks and real connections. No receipt images, raw capabilities or database snapshots are published.

- Increment 1 — trusted bootstrap and authenticated initial snapshot: red `ModuleNotFoundError: tabwise.authority`; first implementation run encountered a sandbox restriction on the platform temporary directory, so disposable databases use ignored `.local/tests/` instead. A duplicate meal cannot reset the draft; both separately provisioned diners see the same incomplete snapshot. Credentials use 32 random bytes and only domain-separated SHA-256 verifiers reach SQLite. Snapshot authorization/state read share a read transaction. Schema setup is outside acceptance transactions; explicit SQL transactions use `isolation_level=None` and explicit legacy transaction control where the runtime supports it.
  Green: `python -m unittest discover -s tests -p test_authority.py -v`, 1 test passed. No application networking or calculator changes.
