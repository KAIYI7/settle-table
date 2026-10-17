# Disposable Notion connector experiment

Publication note2026-10-17: all account destinations/IDs in the published traces and narrative are consistent synthetic aliases. `example.invalid` links cannot access or clean up the original scratch. Private originals remain in ignored local audit backups; reproduce account observations only in a fresh, explicitly authorized disposable destination. Numeric observations/schema/errors are preserved; these are not replayable account requests.

Phase 1 only. Uses fictional records and integer sen. No production library/schema or real receipt.

Private experiment root: [TabWise Phase 1 DISPOSABLE validation](https://example.invalid/notion/synthetic-notion-id-013).

The connector's `draft` creation mode guarantees workspace-level private creation according to its tool contract. No page was shared, moved into existing content, or published. Child experiment databases inherit this fresh destination. Sharing ACLs are not independently exposed by the inspected fetch response.

The original root and descendants were retained for evidence. Owner-only cleanup uses the original private local record, not the published alias, and must target only the verified disposable destination. Deleting does not reclaim Free lifetime block quota.

`connector-evidence.json` records the initial schemas; `connector-roundtrip.json` records redacted synthetic requests/results and IDs. Account identity, credentials, internal attachment references and request tracking tokens are excluded. These are connector observations, not raw REST traces.

`synthetic-receipt.svg` stores the uploaded synthetic SVG markup with a trailing newline (598 local bytes; connector content upload was 597 bytes). It is not a real receipt or OCR fixture.

Run `python research/phase-1/experiments/notion/retry_simulation.py` from the workspace root to reproduce the local-only retry experiment. Python 3.14.6 produced 12 passing checks. It writes `simulation-results.json` and `simulation.sqlite`; fake remote tables contain synthetic integer-sen payloads only. Re-running resets only those two tables inside this experiment's dedicated SQLite file. It never sends HTTP requests.

SHA-256 of `retry_simulation.py` at validation: `22aca725a826064a4e9b89bfa5ac8d7c6dd22c23a698b54331fca646c1f13791`.

Current findings, observed connector errors, corrected requests and unresolved REST boundaries are in `../../notion-validation.md`. Scratch data is restored to integer-sen values and the meal is revision 4 / Complete. The intentionally invalid fractional input probe is explicitly recorded as rejected adapter input, not a valid financial model value.
