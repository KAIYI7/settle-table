# Internal Python package naming

Inspected2026-10-17 at authority PR head `59cba5feb25423ebd43ebee17b7666d84f83d584`. This is a source/compatibility assessment, not an implemented refactor or authorization to advance a phase.

**Recommendation / inference:** rename the import package `tabwise` to `settletable` in a dedicated, mechanically reviewable refactor before adding transport. Keep every versioned financial/security domain and serialized contract unchanged. The small current caller surface makes this the lowest-cost point to align discoverable source names with SettleTable. Retaining `tabwise` is technically sound but would perpetuate two names without an identified compatibility consumer.

## Verified source and persistence facts

| Accepted source | SHA-256 at inspected head |
|---|---|
| `tabwise/calculation.py` | `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a` |
| `tabwise/authority.py` | `1eef9e7959639de5407bc445e9344f3ef7e0bb9502bafcfb2026d2c794ed81f0` |

Source references below describe that exact revision. Historical paths remain resolvable in [the accepted PR tree](https://github.com/KAIYI7/settle-table/tree/59cba5feb25423ebd43ebee17b7666d84f83d584). No third-party API documentation is needed to assess these in-repository imports and serialization functions.

- `tabwise/authority.py:13` uses a relative calculator import, so the entire three-file package can move without production-body edits. Both production module files can retain identical bytes and hashes.
- `tabwise/authority.py:186` serializes compact, sorted-key ASCII JSON; `:261`, `:308` and `:325` decode explicitly named receipt/result/calculation fields. There is no pickle, module-qualified class name or `__module__` serialization in either production module. `:279` serializes the plain command class name (`ReplaceReceipt`, etc.), which must remain unchanged.
- SQLite tables at `tabwise/authority.py:353–370` are `meals`, `participants`, `sessions`, and `commands`. No table name contains the import namespace. `:643–652` authenticates and authorizes before looking up accepted command body/digest/result, then decodes the saved JSON. A package move alone therefore does not require a database migration. This is a source-derived conclusion requiring a cross-version reopening experiment before acceptance.
- Validation checks exact dataclass types (for example `tabwise/authority.py:220`, `:276`). Avoid loading both physical copies under different module names: their distinct class identities could make apparently identical facts fail validation. There is no existing distribution/package metadata (`pyproject.toml`, `setup.py`) among tracked project files and no declared external import consumers. That absence does not prove there are no untracked personal scripts.

### Contract literals to preserve verbatim

| Location at inspected revision | Literal | Why it survives a package rename |
|---|---|---|
| `tabwise/calculation.py:149` | `tabwise-apportion-v1` | Changes SHA-256 tie order and may change which diner receives a residual sen. Documented in `docs/calculation-interface.md:35` and pinned by `tests/test_calculation.py:40–54`. |
| `tabwise/authority.py:197` | `b'settletable-local-session-v1\0'` | Existing stored session verifiers must continue to authenticate. |
| `tabwise/authority.py:272` | `b'settletable-receipt-v1\0'` | Existing receipt digests and human-review attestations must remain valid. |
| `tabwise/authority.py:279` | `settletable-command-v1` | Part of canonical accepted command bytes. |
| `tabwise/authority.py:638` | `b'settletable-command-digest-v1\0'` | Existing durable replay digests must match. |

Also preserve JSON field names/order policy, `kind` values, command ID scope, revision behavior, rational encoding `[numerator, denominator]`, error codes, table definitions and amount semantics. None is a branding target. A global text replacement of `tabwise` would be incorrect even if most tests passed.

## Caller and documentation map

| Material | Required handling in the dedicated refactor |
|---|---|
| `tabwise/__init__.py`, `calculation.py`, `authority.py` | Move to `settletable/` as exact bytes; no calculation/security logic change. |
| Five current `tests/test_*.py` files | Update module imports; also the string patch target in `tests/test_authority.py:255` and embedded fresh-process program import in `tests/test_authority_adversarial.py:195`. Leave tie-domain comment/literal and verifier vectors unchanged. |
| `research/phase-3/engineering_probes.py:11,138` and `independent_probes.py:16,156` | If retained as runnable probes, update import and current source hash path together; do not overwrite previously recorded JSON evidence when merely checking imports. These are the only tracked research Python callers found. |
| `docs/calculation-interface.md`, `docs/authority-interface.md`, root `README.md` | Update current import instructions/examples and explain retained versioned tie domain. Root README currently says `tabwise` remains the namespace; revise that active statement when the rename lands. |
| `.scratch/authoritative-draft/SPEC.md`, `research/README.md`, `research/phase-3/README.md`, current status/index/ledger links | Clarify new current source/import path while retaining the accepted historical namespace distinction. Link historical source evidence to the immutable accepted tree where relative old links would break. |
| Phase3 review reports and verification JSON, publishing audit/manifests, red/green implementation logs | Preserve historical path/hash/test-output facts. Do not rewrite a historical `ModuleNotFoundError: tabwise` as if `settletable` had failed then, or change the old source path keys in a frozen hash manifest. A short new refactor evidence note can map old to new paths and unchanged hashes. |
| Phase1 Notion JSON asset filenames, synthetic old display names, repository-research temporary folder names | Historical evidence, unrelated to imports. Preserve rather than mass-renaming or replaying external experiments. |
| Vendored `.agents/skills`, ignored local environments/caches | Outside this refactor. Do not scan-rewrite third-party payloads or local receipts/credentials. |

**Inference:** no `tabwise` compatibility shim is necessary for the current unpublished local-only application module. State this as an intentional source-import change. If an actual external caller is discovered, reconsider a re-export-only adapter with identity tests; never duplicate the implementation. Python object `__module__`, traceback paths and default class representations will change naturally. They are not used by the inspected persistence format; pickle compatibility is not promised.

## Refactor acceptance evidence to collect

1. Before moving source, record the two module hashes above and prepare an ephemeral SQLite database through the accepted old package using a fixed trusted clock. Exercise receipt entry, rational claims, human review, finalization and accepted replay. Keep generated raw credentials only in process memory or transient IPC; never create a tracked credential fixture. Do not print credentials, SQL traces containing sensitive data or private database dumps.
2. Close all old connections, then load the renamed module in a fresh process and reopen that same database. Authenticate with the original credentials, compare receipt/review digest and immutable calculation values, and replay exact prior commands. Require **byte-for-byte saved `canonical_bytes` equality**, no duplicate accepted rows and no revision advance. Reusing the unchanged source under a renamed package in an isolated test subprocess is sufficient; no third-party dependencies or new schema are needed.
3. Include an unfinalized meal so the renamed module can accept a new claim/command after reopen; compare expected canonical body/digest semantics and conflict handling. Include revoked/expired credentials and changed-payload reuse to ensure preserved data has not become a permission bypass. Preserve the exact SQL schema and durable accepted body/digest/result bytes; do not compare whole SQLite file bytes, whose internal bookkeeping may legitimately vary.
4. Pin the existing one-sen `tiny` tie vector (A0/B1), signed adjustment vector and session-verifier domain test. Run the entire unmodified-behavior calculator/authority/security/adversarial suite, including the actual10,000-command exhaustion case. An import-only smoke test is insufficient.
5. Verify moved calculator and authority source files have the **same hashes** as the accepted originals. Review `git diff --find-renames` and inventory remaining `tabwise` matches: only versioned semantics, immutable evidence and intentional compatibility commentary should remain in active tracked material. Assert no new credential fixtures, database files or production behavior enters the diff.

**Unresolved:** actual cross-version SQLite reopening and the renamed full-suite run have not been performed by this assessment. The orchestrator must review that evidence and the actual diff before accepting a rename. Naming work must remain separate from CI setup and the next transport/identity/invitation capability.
