# Phase 1 coordinating verification

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../../docs/agents/governance.md) and the [transition ledger](../../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Access date2026-10-16. [Machine checks](verification.json). This is evidence review, not production acceptance.

## Scope and authorization

Rechecked AGENTS.md: SHA256 of all bytes outside Current phase is `681a3445bfa0c0a5c86eadaa5359ab58c98edac9b16d0f8730e3687ae533b226`, identical to before the authorization update. No root `src/`, `app/`, `pages/`, package manifest, framework scaffold or ADR directory exists. All executable experiments are under `research/phase-1/experiments/`. Root GLOSSARY contains durable dining terms only; no production stack decision was written as an ADR.

Recorded both interview rounds: live diners, private internet invitations, organizer financial/finalization controls and diner own assignments; device/self-hosted-only OCR, no hosted image calls, no private folder. No paid image call occurred. No framework-specific skill installed.

## Domain and concurrent edits

Read the pure money/weight helpers and workflow scenarios. Initial review found monetary inputs not validated on every interface and suggestions represented as confirmed transfers. The runner was corrected to validate integer sen/identities and use an explicit simulation confirmation action. Coordinator executed the current runner:67 concrete scenarios and54,000 seeded assertion groups pass; Python3.14.6 and current source/result hashes recorded. Older54-scenario/51,000-assertion and Python3.14.0 prose was superseded rather than presented as current evidence.

Compared the historical inclusive-tax scenario with receipt annotation/source hash:600sen lines,566net subtotal,34included GST. This justified separating canonical item subtotal from other printed subtotal bases; it is not a current SST rule. New glossary definitions record this durable distinction.

Executed the17-check collaboration simulation, including a real two-thread race. Role/revocation and replay operate on fictional in-process identities. It has no production server, actual invitations, authentication or socket clients; no such claim is inferred.

## OCR

Coordinator resumed persisted work after the delegated OCR agent hit a usage limit. Existing source/annotation/preparation/Tesseract files were preserved. Added a deterministic synthetic perspective case, then ran20 calls per engine (two passes ×10images) sequentially: RapidOCR, PaddleOCR with oneDNN disabled, Tesseract.js with local language assets. Preserved initial Paddle oneDNN failure, successful retry and Tesseract warning logs. No repeated tuning toward final scores.

Parser/evaluator was frozen before the scored run. Reviewed its lack of truth access during parsing, exact sen parsing, spatial grouping, positive/absence denominators and ordered-item matching. Its name-before-quantity failure is recorded as parser error, not attributed to engine recognition. The gate's clean-but-incorrect candidates are preserved. No held-out or human-verified accuracy claim.

All30 second-pass observations correspond to the six real/four synthetic corpus entries. Source image hashes match each raw run;16 artifact hashes and13 selected model-asset hashes match. Checked normalized money in truth/proposals is integer sen or null, excluding descriptive presence metadata and raw OCR text. Labels/source/model rights and real-phone coverage remain qualified.

## Notion

Read synthetic connector request/readback evidence and retry simulator. Independently fetched the disposable root and Meals schema, confirming six child databases, NUMBER properties/relations and formula query limitation. Independently fetched final synthetic meal:3365sen total, revision4, Approved/Settled/Complete; attachment exists. Temporary signed download URLs were not copied into this research record.

Observed fractional NUMBER probe was deliberately invalid input on synthetic data while copy Pending, restored before financial calculation/report; the adapter rejects it. Valid financial sums use integers. Re-ran12 local recovery checks successfully. Live connector results do not validate raw REST credentials/OAuth, workspace billing plan, rate/file boundaries, ACLs, formula calculation or real retry behavior. The private-draft tool contract is the privacy evidence; no independent ACL audit was claimed.

## Reconciled conclusions

- Correct final totals/high OCR confidence did not establish correct item fields; human verification remains required.
- Live concurrency is now required; single-editor assumptions are withdrawn. In-process CAS/role checks demonstrate rules, not deployed collaboration.
- Notion supports reporting shape, while integer/transaction/role enforcement belongs outside it. Optional integration is favored; raw REST contract remains open.
- Path C remains a shape recommendation; no framework uniquely selected. Next.js is a candidate, no longer default.
- These experiments are independent disposable code, not copied production modules or automatically reusable application source.

## Remaining verification gates

Representative modern Malaysian dining/SST/voucher corpus with human labels; physical Android/iOS capture and device-local OCR; actual two-browser reconnect/security/latency; raw Notion REST/OAuth/media; production amount/transport bounds, retention, hosting and remaining financial policies. Final recommendation distinguishes these from completed experiments and recommends bounded Phase2 closure. No Phase2 work started.
