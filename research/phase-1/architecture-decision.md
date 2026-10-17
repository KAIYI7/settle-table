# Phase 1 architecture and stack assessment

2026-10-16. **Nonbinding research conclusions; no final framework, database schema, production scaffold or deployment selected.** This assessment follows review of the domain and OCR/Notion experimental results. Documentation sources/Context7 resolutions: [architecture evidence](architecture-evidence.md).

## Inputs that changed the Phase 0 recommendation

**User-confirmed requirements:** several diners edit the same meal live; private internet invitations; organizer controls receipt amounts/charges and finalization, diners their own assignments; OCR on device or self-hosted only, no third-party hosted image inference. No private receipt corpus supplied.

**Experimental evidence:**

- [Domain](domain-model.md): 67 concrete scenarios and 54,000 seeded assertion groups pass using exact integer sen/rational weights. These demonstrate tested arithmetic/state behaviors, not production security or all possible policies.
- [Concurrent-edit simulation](experiments/collaboration/results.json): 17 checks pass; replacing stale whole-record state loses a diner claim, while explicit revisions reject conflicting writes. Two real local threads yield one accepted same-revision edit. No browser/socket/Internet/persistence test is claimed.
- [OCR](ocr-validation.md): six historical dining scans plus four synthetic cases, two passes through three local engines. Totals can match while names/quantities are wrong. Required human review survives; the confidence/reconciliation gate is not suitable for automatic acceptance. RapidOCR was a practical CPU baseline; browser/native performance remains unmeasured.
- [Notion](notion-validation.md): six live disposable databases/nine synthetic rows, payers/allocations/relations/file/status readback; Number did not enforce integer sen; local uncertain-write/retry simulation passes12 checks. Raw REST/runtime limits still unverified.

## Re-evaluated path

**Conclusion: Path C remains the strongest shape**, with selected licensed helper reuse only after targeted review. This is supported by the gap between the requested itemized, multi-payer, live-edit workflow and every reference model, and by experiments identifying correctness rules the reference apps do not supply together.

| Alternative | Disposition |
|---|---|
| Fork BillSplit | Good correction/assignment inspiration; local draft + single-editor UI, equal fees, no authoritative payer/settlement/realtime domain. Extending it is not automatically cheaper than a small shell. |
| Fork Spliit / SplitPro | Mature expense ideas and integer/settlement patterns, but item/charge/multiple-payer models differ and guest/file permissions need fresh scrutiny. Neither inspected snapshot proves the required live item-edit flow. |
| Compose their modules unchanged | Reject: different source facts/signs/rounding and single-payer models do not compose directly. Patterns and carefully licensed isolated functions remain options. |
| New small shell | Favored: deterministic financial calculation, reviewed receipt proposal, explicit accepted edits and optional downstream adapters. No actual application module created. |
| Notion-first operational app | Reject for this requirement: live financial concurrency, integer/role/revision enforcement and multi-record invariants would still need an independent authority. |

## Candidate stacks after evidence review

All cells below are **engineering inferences from capabilities**, not measured head-to-head framework benchmarks. Camera/file capture, browser workers and PWA cache behavior are largely browser/device capabilities; choosing React or Next does not validate them. AI-agent maintainability is assessed through explicit contracts/locality/reproducibility, not an unsupported claim that an agent inherently knows one framework better.

| Candidate | Capture / responsive/PWA | Local OCR | Notion / live editing | Testing / agent maintainability | Deployment / recurring cost trade-off |
|---|---|---|---|---|---|
| Static TypeScript UI (framework deferred) + Python authority/OCR | Standard mobile file capture and responsive DOM; actual phones/offline assets still need validation | Direct fit to measured Rapid/Paddle; optional browser Tesseract; device can upload to controlled server | Python can hold credentials and serialize financial edits; realtime transport/auth still to validate | Exact integer Python core possible; typed wire contract important; keep OCR apart from financial authority | One Python runtime can serve static files and API; frontend build tool optional. CPU inference must not block collaboration; worker/model RAM costs measured next. |
| React + Vite + Python authority/OCR | Strong candidate for stateful receipt/assignment forms; same browser capture/PWA limits | Same as preceding; React is not an OCR engine | Separate typed API/realtime channel; secret credentials stay backend | TypeScript UI plus Python core; two language/toolchains but small explicit seams. No React-specific skill required for current experiments | Static UI + Python backend can be one hosted service/worker arrangement. Avoid unnecessary Node production server if all backend work is Python. |
| SvelteKit Node + optional Python OCR worker | Comparable browser/PWA surface; server/client split and adapters documented | Browser OCR or additional measured Python worker | Server-only modules hold Notion secrets; realtime authority still explicit | Plausible smaller UI code, but no measured development/maintenance advantage. Typed contracts and domain fixtures remain essential | Integrated web/API runtime, plus Python if selected engine requires it. More runtime types when CPU OCR is server-side. |
| Next.js Node + optional Python OCR worker | Viable interactive forms; SSR itself is not an established receipt need | Browser workers or separate Python OCR | Runtime handlers can hold secrets; static export cannot provide live mutations/sync | Relevant MIT references exist but do not justify importing their tRPC/ORM/auth breadth. RSC/server-action conventions add concepts to maintain | One web/API deployment plus Python if needed; self-hosting possible. No Vercel dependency required. No demonstrated advantage over alternatives for these requirements. |
| Native mobile shell (Flutter or platform-native) + shared authority | Potentially stronger camera/device integration; invitation recipients may need installation | ML Kit/Vision attractive device-only option, unmeasured here | Still needs shared Internet authority and secret-backed Notion adapter | Device/build/platform-plugin matrix and release QA; no native prototype or plugin compatibility measured | App release/QA overhead; can avoid server OCR compute, not collaboration/storage operations. Web plugin support must be checked separately. |
| Server-rendered HTML + targeted JavaScript + Python | Simple shell possible, but live assignment conflicts/optimistic feedback still require rich client state | Fits server OCR; browser-worker work separate | Credentials/server authority straightforward in principle | Fewer frontend dependencies at first, custom interaction/state logic can grow; no measured simplicity advantage | Can avoid Node runtime; do not equate reduced dependency count with lower total maintenance. |

**Stack conclusion:** withdraw the Phase 0 default preference for Next.js. It remains viable, but no evidence uniquely selects it. For the next bounded feasibility work, compare a thin browser client with a Python shared authority against a native-device capture/OCR route on real phones. React/Vite and SvelteKit are realistic UI candidates after that gate, not installed choices. A native-first commitment is premature while private invitation/browser access is valuable and device OCR unmeasured.

**Why no framework skill was installed:** no framework is uniquely selected by current evidence and none is necessary for the remaining headless Phase 1 experiments. Existing Impeccable remains the design skill for a later authorized UI phase.

## Proposed interfaces and seams, not production code

The codebase-design discipline favors a few deep modules with narrow interfaces:

1. **Reviewed meal calculation:** explicit receipt basis, components and claims → conserved consumption and reconciliation issues. No OCR, transport or Notion side effect inside this calculation.
2. **Accepted meal edits:** actor/permission, stable operation identity and expected revisions → committed revision or explicit conflict. Persistence/transport implementation remains replaceable; diner membership is not a claim allocation.
3. **Extraction proposal:** image → evidence/boxes/proposed fields/issues. Real varying adapters were exercised for three engines, so this seam has evidence rather than hypothetical optionality. Any local model remains a new adapter to validate.
4. **Notion projection:** reviewed revision → report-copy operations and reconciliation status. Live connector is one proven adapter convention; raw REST/OAuth is still a separate integration contract.

These are research interfaces, not a package layout or service-count commitment. Start with clear separation of responsibilities; do not turn every seam into a separately deployed service. No automatic adoption of LangGraph, event sourcing, microservices, a particular ORM or distributed CRDT is justified.

## Concurrent editing implications

**Conclusion:** use an authoritative accepted revision for financial edits; last-writer-wins over whole receipts can lose claims. Small item-scoped revision checks can allow distinct-item edits, while changes to amounts/charges invalidate the shared financial basis and stale finalization. Quantity ownership can conflict even when two diners edit their own claims, so aggregate capacity must be checked atomically. Reconnect must reconcile committed operation IDs/revisions; unacknowledged edits remain pending.

**Proposals to validate:** transactional compare-and-swap plus committed updates, explicit conflict UI, revocable private invites/participant identity, organizer-only financial actions, audit-visible correction and immutable real transfer identity. SSE/WebSocket transport, transaction granularity, storage engine and offline replay design are **unselected**. No distributed claim merging, actual Internet latency or malicious-client protection was proven by the lock simulation.

## Privacy and deployment implications

- Device-only OCR and self-hosted OCR are distinct: the latter moves images to the controlled server. No hosted vision vendor receives receipt images under the confirmed product policy.
- Local OCR does not make live Internet collaboration offline. Drafts can survive disconnection, but financial finalization and transfer confirmation must wait for authoritative acceptance.
- Notion archiving is optional external storage/reporting; uploading a receipt there needs a deliberate image-copy/retention setting separate from OCR consent. Experiment used synthetic media only.
- Model assets must be provisioned/cached; self-hosted CPU occupancy, model RAM, concurrent diners and backup/retention determine realistic cost. Benchmark wall time is not a deployment price quote.
- FastAPI is a possible Python host, not installed app architecture. Official docs warn that each worker loads its own model memory and CPU inference must not block async collaboration. [Deployment concepts](https://fastapi.tiangolo.com/deployment/concepts), [async behavior](https://fastapi.tiangolo.com/async). Context7 resolve/query completed for this assessment.

## Remaining selection gates

Real Android/iOS camera/worker/native behavior; independently reviewed modern dining corpus; held-out parser performance; two-browser realtime conflict/reconnect probe; invitation identity/revocation and settlement confirmation policy; controlled-server hosting/retention preference; raw Notion REST contract; bounded amounts/quantities/transport representation. No benchmark in this phase establishes a production framework winner, hosted price, uptime promise or automatic receipt trust.
