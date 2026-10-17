# SettleTable package refactor evidence

Started2026-10-17 after the orchestrator selected the [mechanical naming recommendation](package-naming.md). Dedicated branch: `refactor/settletable-package`. Scope is source imports/documentation and compatibility validation only; CI and product capabilities remain separate.

## Acceptance plan and source baseline

The public calculation and local authority interfaces are unchanged apart from their Python import path. Move the existing package to `settletable`, update current callers, preserve all source bytes and all versioned hash/serialized-contract literals. Historical evidence is retained under its original names and hashes.

Accepted baseline is annotated `authority-v1-accepted`; expected calculator SHA-256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`, authority SHA-256 `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0`.

**Pending experiments:** complete60-test calculator/authority suite including actual10,000 durable commands; cross-version accepted-source SQLite reopening/authentication, exact command replay, review/calculation/receipt digest fidelity, revoked and expired denial, changed-command conflict and new draft command. Compatibility script lives separately under `experiments/` and requires local Git history; routine CI tests gain no Git dependency.

Credentials generated for the experiment may pass transiently between isolated child processes through captured pipes. They must never be printed by the driver, included in the safe result artifact or written to a credential fixture. Disposable source copies/databases stay in ignored `.local/`.

No acceptance or passing runtime claim is made at this initial record. Results and limitations follow after execution.

## Executed compatibility checks

**Experimental evidence / PASS:** [compatibility script](experiments/namespace_compatibility.py) against the actual accepted tag and renamed working tree; [safe result](package-compatibility.json). The initial pre-move invocation failed generically because the requested new source path did not exist; this was missing-refactor evidence, not a financial defect. After the move, the isolated old-package preparation and new-package reopening passed.

-10 authorized accepted commands replayed byte-for-byte across package names without state/revision/row changes;3 complete old snapshots matched, including receipt digest, review record and immutable actual-calculator results.
- The original database schema, persisted command bodies/digests/results and session verifiers matched. A changed payload under an existing command ID was rejected. Revoked snapshot/claim replay and expired credentials remained denied.
- A new quantity command on an unfinalized old meal succeeded at revision3; all original command rows and verifier records remained intact.
- Exact one-sen tie and signed adjustment vectors passed under both packages. Both production module files retain the accepted SHA-256 hashes above.
- Generated raw credentials remained in memory/transient captured child-process pipes only. Every disposable file was scanned after closing the subprocess connections; none contained a raw credential. The driver emits only safe aggregate results and generic failure diagnostics. Temporary read connections use explicit `contextlib.closing` after independent review noted that a SQLite connection context alone does not close a handle.

The experiment is deliberately outside routine `tests/`, requires the local accepted Git tag and writes only disposable `.local/` data plus an explicitly selected safe output path. It establishes package-move compatibility for exercised accepted states; it does not introduce a general database migration framework or promise compatibility with Python pickle/module-qualified external objects.

**Full-suite execution:** the implementer's initial session could not be recovered after an agent usage-limit interruption and is not counted as passing evidence. The coordinator independently reran `python -m unittest discover -s tests -v`: **60 tests PASS in73.078s**, Python3.14.6 / SQLite3.50.4, including the real10,000-command test. No assertions or test semantics changed; exact comparisons verify only package imports, one mock path, embedded subprocess import and probe hash paths changed. Historical probe JSON was not regenerated.

**Orchestrator review / PASS for the dedicated mechanical refactor:** [actual-source/caller/experiment review](package-refactor-review.md). Both original production hashes remain identical, and the coordinator independently reran the compatibility script successfully. Hosted PR integration is a subsequent merge gate. There is no new product capability or CI change in this refactor.
