# Local draft authority interface

`tabwise.authority` owns one-host SQLite meal state. The external seam is `Authority(path, *, clock=time.time, failure_hook=None)`, `bootstrap`, `snapshot`, `apply` and `close`. It raises `AuthorityError` with a safe stable `code`; it never returns raw storage exceptions. Inputs and outputs are exact frozen slotted dataclasses and exact tuples. Constructors alone do not validate facts.

`bootstrap(meal_id, participants, *, session_ttl=3600)` accepts a tuple of `Participant(id, name, organizer=False)` with exactly one organizer. It returns `BootstrapResult(meal_id, sessions)`, containing one `SessionGrant(participant_id, credential)` per participant. Credentials appear only in that one-time trusted return, are omitted from its representation, and are never persisted. This is trusted local provisioning, not account registration. `snapshot(credential, meal_id)` returns the entire consistent immutable `DraftSnapshot`; `apply(credential, meal_id, command)` returns `AcceptedResult` only after commit. `close()` closes the connection.

Receipt facts: `ReceiptItem(id, label, quantity=1, line_sen=None)`, `ReceiptAdjustment(id, label, kind, amount_sen, eligible_item_ids, rationale)`, and `Receipt(items=(), subtotal_sen=None, total_sen=None, adjustments=(), included_tax_sen=0)`. Monetary values are integer sen or documented unknown `None`. Quantities are exact `int`/`Fraction`; adjustment scopes are nonempty tuples. Receipt review does not invent diner allocations.

Commands (positional order shown; keywords recommended):

- `ReplaceReceipt(command_id, expected_revision, expected_financial_revision, receipt)`
- `SetOwnQuantity(command_id, item_id, quantity, expected_item_revision, expected_financial_revision)` (`None` releases)
- `ReviewReceipt(command_id, expected_revision, expected_financial_revision, receipt_digest)`
- `Finalize(command_id, expected_revision, expected_financial_revision)`
- `RevokeSession(command_id, expected_revision, participant_id)`
- `RevokeMembership(command_id, expected_revision, participant_id)`

`DraftSnapshot` exposes meal/financial revisions, receipt digest/facts, `items` as `ItemState(item_id,item_revision)`, immutable `claims` as `Claim(item_id,participant_id,quantity,financial_revision,status)`, current review, finalized calculation, diagnostics, fixed participants and inactive participant IDs. A claim status is `confirmed` or `pending`. `ReviewRecord` records participant ID, financial revision, receipt digest and command ID. `AcceptedResult` exposes command ID/kind, original committed revisions, changed claims, optional actual calculator result and `canonical_bytes`. Those bytes are the durable exact response; exact authorized retries return identical bytes and original revision, not a current snapshot.

Trusted `failure_hook(stage)` can raise at `after_state`, `after_result`, `before_commit`, or `after_commit`. Precommit exceptions roll back both state and response. An `after_commit` exception reports `commit_uncertain`; retry the identical command. Hooks receive no credentials or state. They are trusted test dependencies, not an untrusted callback facility. Database administrators and privileged Python callers remain outside this permission guarantee.

Commands and accepted results are at most 1MiB of canonical JSON. Ordinary state mutations additionally retain a 900,000-byte state ceiling, leaving security-revocation headroom below the 1MiB storage ceiling. State/response limits reject before commit without pruning earlier accepted history. A failed rollback discards the connection; reopen through a new `Authority` before further work.

No networking, invitation lifecycle, UI, settlement, OCR or Notion is included. Read the binding [specification](../.scratch/authoritative-draft/SPEC.md) for bounds, permission/replay ordering, pending ownership and deferred policy gates.
