# Phase 2: real-browser collaboration transport validation

Access/run date: **2026-10-16**. Disposable experiment only; the orchestrator owns any phase/implementation decision. This artifact closes a narrow Phase 1 evidence gap rather than repeating OCR/domain research.

## Question and evidence boundary

Can the proposed serial authority, item/financial revisions, own-claim permission checks and operation identity survive actual requests from two independent browser clients? [Phase 1 architecture](../phase-1/architecture-decision.md) explicitly lacked browser/socket evidence. [Phase 1 simulation](../phase-1/experiments/collaboration/simulate.py) supplies the existing independently written model, not a production component.

**Experimental evidence:** two isolated **real headless Chromium contexts**, each with one page executing `fetch` against a Python threaded HTTP server bound only to `127.0.0.1:8766`. They are not Python/Node HTTP clients pretending to be browsers. Browser A and B both submit the initial item claim; a fixture barrier releases both server threads only once both requests arrive. Remaining actions use visible page buttons driven through Playwright locators. No app framework/scaffolding, external deployment, hosted model, paid service or private receipt is involved.

The prototype skill was read; its ordinary single-file/no-server and throwaway-branch rules were overridden only where the explicit real-transport question and persistent research-artifact requirement required it. The fixture remains isolated under `research/phase-2/experiments/collaboration/` and is never production-ready code.

## Observed results

[Machine evidence](experiments/collaboration/results.json), [code and reproduction](experiments/collaboration/README.md).

| Material check | Result | Observed behavior |
|---|---|---|
| Two independent browser sessions / actual HTTP | PASS | Chromium **151.0.7922.34**, Playwright **1.62.1**; two isolated contexts, no page errors. |
| Simultaneous claims against same item revision | PASS | Exactly one HTTP 200 and one 409; independent runner verifies the pair. Server arrival timestamps are 08:00:56.314357 and .314842 UTC (0.485 ms apart). Barrier is a controlled overlap, not an Internet latency model. |
| Quantity capacity and subsequent correction | PASS | Winning diner claims 2 of 3; losing diner's fresh request for 2 is rejected; fresh request for 1 succeeds. Another item's revision remains independently usable. |
| Operation identity | PASS | Winner's exact operation returns the identical original event; changed body with the same ID is rejected. |
| Roles / financial basis | PASS within fixture | Editing another diner's claim, diner amount edits and diner finalization rejected; stale item/financial/meal revisions rejected. Synthetic bearer credentials only; no secure invite flow proven. |
| Review and authoritative receipt total | PASS within fixture | Organizer changes dish from 1000 to 1001 sen, review is invalidated. Even after review, finalization rejects the 1-sen discrepancy against the authoritative **1300 sen**. Correcting back to 1000 and reviewing allows finalization. |
| Finalized state | PASS | Ordinary claim mutation rejected after current, reviewed, reconciled finalization. Final revision 8, financial revision 2; dish 1000 + tea 300 = 1300 sen. |
| Missed updates and snapshot recovery | CONDITIONAL PASS | B ignores intermediate changes, then fetches missed events and current snapshot; last committed snapshot matches. An out-of-order snapshot guard avoids older revisions replacing newer state. This does **not** simulate a dropped connection or packet loss. |
| Revoked access / duplicate replay | PASS within fixture | After organizer revocation, B receives 403 for snapshot, missed-event reads and replay of its original operation. No persistent session/invite authorization is implemented. |

Final runner: **30 passed, 0 failed, 0 browser page errors**, **420 ms** for the browser scenario after launch. This is one deterministic local fixture run, not a latency/performance benchmark or a statistical reliability estimate. An earlier run before adding the independent race-pair assertion passed 29 checks; the final result supersedes it. No failed semantic run was hidden.

All monetary fixture values and outputs are integer sen. Quantities are integer fixture quantities; this transport probe does not revalidate rational shares, charge bases, settlement accounting or all 67 Phase 1 domain scenarios.

## Important new finding and resolution

**Verified source finding:** the original Phase 1 concurrency simulation's `Meal.apply(... finalize ...)` checks review and complete item quantity claims but has **no authoritative receipt-total comparison**. Its prior 17-pass result therefore did not prove receipt reconciliation at finalization. The Phase 1 domain experiment separately tested monetary conservation; combining those results is not proof that a future transaction layer enforces both atomically.

**Targeted experiment change:** the HTTP fixture wraps the model's accepted operations in a serial authority lock and adds an authoritative 1300-sen total check at finalization. The browser observed the explicit mismatch rejection after review, then successful correction. This fixture has no tax/fee/discount model: summing line amounts here must **not** be copied as the complete production reconciliation rule. Production finalization still needs a single transactional domain-validation gate including charges, inclusion bases, allocation conservation, current revisions and all unknowns.

## Limitations and unresolved gates

- **Blocking before real private Internet invitations:** real identity/session design, high-entropy scoped invites, hashed tokens, expiry/revocation policy, organizer recovery, per-meal authorization, CSRF/origin checks, rate limits and independent security review. Public fixture tokens, `/fixture-revoke`, `/report` and unauthenticated synthetic `/results` are intentionally unsuitable for deployment. Browser A deliberately holds the synthetic organizer token solely to exercise organizer actions.
- **Blocking before claiming durable accepted edits:** database transaction/compare-and-swap, operation result and mutation committed atomically, crash recovery, restart replay, cross-process concurrency, persistence of revocation and no torn settlement/finalization writes. In-memory Python locks prove none of these.
- **Not measured:** WebSocket/SSE, automatic live UI delivery, actual offline/reconnect failures, malicious payloads, packet reordering, mobile Safari/Android, real phones/camera, Internet delay, concurrent OCR CPU load, invitation usability and accessibility.
- **Not covered:** amounts/charges beyond two synthetic item lines, actual/partial settlements, payer accounting, amendments, Notion or image storage. Those need their own acceptance scenarios, not inference from this transport result.
- The in-app CUA browser could not reach the workspace loopback URL (`ERR_CONNECTION_TIMED_OUT`). Normal sandbox execution also blocked local sockets. Existing local headless Chromium with approved sandbox escalation resolved the environment issue while preserving loopback-only binding. No browser security warning was bypassed and no new software installed.

**Architectural inference:** the authority/revision approach is viable enough to continue a small manual-entry vertical slice and a durable transactional authority experiment. Polling, SSE and WebSockets remain transport choices; this evidence does not justify selecting a UI framework, database schema, distributed CRDT or public deployment. Required human receipt verification and integer-sen invariants remain intact.

## Reproducibility and current documentation

Reproduce using [README commands](experiments/collaboration/README.md), starting a fresh in-memory server each time. The server was stopped after validation. The bundled Node/Python/Playwright assets were discovered through `load_workspace_dependencies`; no global installs or account changes were made.

Exact source SHA-256 values are embedded in the result:

| Source | SHA-256 |
|---|---|
| `server.py` | `11c392c1c282dab900dc797ac6aa679db6ac58ec531f960851790db85f932376` |
| `client.html` | `27f9ab956951e4325b8516876709a9c8ffd0f4af62f9e259dbfce810ceeda638` |
| `run-browser.cjs` | `e860fe245980a0f32a6afcd04b5cdd883583724499a280b81edffef54ab6c83c` |
| imported Phase 1 `simulate.py` | `4d4b5fd07bf23c34fa6f370b32742f723e2d86497fc8746968958782e548644d` |

Context7 `resolve-library-id` selected official `/microsoft/playwright` (High reputation); `query-docs` on 2026-10-16 verified standalone Chromium launch, `newContext`, independent cookies/cache/session state and page interaction. Primary sources: [browser-context isolation](https://github.com/microsoft/playwright/blob/main/docs/src/browser-contexts.md), [standalone library usage](https://github.com/microsoft/playwright/blob/main/docs/src/library-js.md), [Browser API](https://github.com/microsoft/playwright/blob/main/docs/src/api/class-browser.md). Python stdlib HTTP usage is disposable script plumbing, not a production hosting recommendation.
