# Phase 1 recommendation and Phase 2 gates

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../../docs/agents/governance.md) and the [transition ledger](../../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

2026-10-16. **Phase 1 findings are ready for review; production readiness is not established.** The feasible local experiments ran, but modern representative OCR, real-device behavior, production REST integration and live multi-browser collaboration remain unverified. No Phase 2 work, final app scaffolding, production UI, deployment or irreversible architecture commitment has begun.

## Confirmed requirements

- Several diners edit the same meal live through private internet invitation links.
- Organizer controls receipt amounts/charges and finalization; diners edit their own assignments.
- OCR is device-local or self-hosted, in both validation and the future product. Third-party hosted image extraction/fallback is excluded by user choice; no paid image budget approved.
- No private receipt folder supplied. Valid monetary models use integer sen; human verification/correction stays required.

Full workflow/decision tree: [requirements](requirements.md). Domain language: [glossary](../../GLOSSARY.md). Policy alternatives remain explicitly marked, rather than silently accepted.

## Verified facts

- Only the `Current phase` section of AGENTS.md was changed for this authorization; outside-section bytes were preserved. Validation artifacts live under `research/phase-1/experiments/`.
- Six historical Malaysian dining images have recorded source IDs/revisions/hashes; curator CC-BY-4.0 provenance is qualified because original terms could not be retrieved. Four additional stress images are explicitly synthetic. No modern private corpus was supplied.
- Three installed local CPU configurations run on this Windows workstation after isolated dependency setup. Paddle's initial oneDNN failure and successful disabled-oneDNN retry are recorded; Tesseract narrow-line warnings are retained.
- Notion connector can create/read/update the six-entity synthetic model, relations, file attachment and status values. It does not enforce integer-sen NUMBER values. Raw REST/OAuth, rate/file boundaries and formula evaluation are not proven by connector success.

## Experimental evidence

| Experiment | Executed result | Practical limit |
|---|---|---|
| Dining arithmetic/state | **67 scenarios +54,000 seeded assertion groups pass**; exact integer/rational math; multi-payers, quantity/exact/percentage/shared splits, charges, inclusive tax, mismatch, joins/leaves, partial settlement and post-settlement correction | Not a formal proof, production validation layer, authorization or persistence test. Financial policies still need explicit choices. |
| Concurrent editing | **17 checks pass**, including a real two-thread stale-write race, quantity-capacity rejection, role restrictions, duplicates, revocation, explicit amendment and snapshot replay | In-process simulation, no sockets/browsers/Internet latency/durable identity. Last-writer-wins counterexample loses a diner claim. |
| Local OCR + frozen small parser | Six real and four synthetic images ×three engines ×two passes; separate per-field denominators and raw evidence | Exploratory development set, agent-transcribed labels, no independent human gold or held-out estimate; layout/parser errors confound engine recognition. |
| OCR gate | Rapid/Paddle final totals **6/6** on real scans, but each had **3/6 clean-yet-incorrect candidates** under confidence+reconciliation gate; Tesseract total3/6 and routed all6 to correction | Total/average confidence is insufficient for unattended item acceptance. Gate always retains human review; not a validated local-AI fallback policy. |
| CPU timing | Real warm medians Rapid **2.602s**, Paddle **14.254s**, Tesseract **2.390s**; sampled RSS Rapid154MiB, Paddle392MiB | Workstation wall times, not phone speed, true memory peaks, throughput under concurrency or a cost/SLA guarantee. Different model configurations, not all tunings. |
| Notion round-trip | Six disposable databases, nine synthetic rows; multiple payers, Unicode, receipt SVG, final revision4 status/readback;3365sen funding/owed and separate317sen transfer | Synthetic connector observations only. No real receipt or personal diner record uploaded. |
| Notion recovery | **12 local fake-remote checks pass**, including uncertain committed write after restart, duplicate reconciliation, retry budget and incomplete projection marker | No induced live rate pressure, network-failure retry or multi-page transaction proof. |

Detailed data/methods: [domain](domain-model.md), [OCR](ocr-validation.md), [Notion](notion-validation.md), [coordinator verification](verification.md).

## Architectural conclusions

1. **Path C remains favored:** a small new shell using proven patterns and selective licensed reuse. No reference supplies this complete itemized/multi-payer/live-edit model; combining their domain modules unchanged would introduce competing facts and arithmetic.
2. **Withdraw the automatic Next.js preference.** Current evidence selects no framework. Compare a thin browser client with a Python shared authority/local OCR against a device-native OCR route on actual phones. React/Vite, SvelteKit and Next are viable candidates, not installed decisions. No framework-specific skill was installed.
3. **A shared authority must validate accepted financial edits.** Live broadcasts alone do not prevent stale quantities/amounts, duplicate transfers or unauthorized finalization. The per-item/financial revision simulation is a candidate protocol, not a chosen server/database architecture.
4. **Keep consumption, restaurant funding, actual settlements and Notion copy status distinct.** Later receipt corrections preserve payments already made and can reopen balances. Printed subtotal tax bases can differ from item-line sums.
5. **Use Notion as B, delivered optionally as C:** asynchronous reporting/archive copy; reject A as primary operational financial store for this live-edit requirement. The app must remain usable when Notion is delayed/disconnected. Notion receipt archiving needs its own explicit retention/image-copy choice and is not OCR consent.
6. **Human review remains mandatory.** RapidOCR is a practical self-hosted baseline; Tesseract.js remains a browser candidate; this Paddle CPU path is slower and had runtime friction. The experimental parser/gate must not become a production pipeline. Hosted vision is excluded; local vision-model recovery remains unmeasured.

Full candidate-stack comparison against capture, OCR, PWA/offline, Notion, testing, deployment/cost and agent maintainability: [architecture assessment](architecture-decision.md).

## Assumptions and risks

**Assumptions used only for experiments:** MYR single-meal arithmetic; fictional identities; component-specific eligible bases supplied explicitly; stable tie identity; exact known source fields where annotated; cached models;1000receipts/month cost illustration. None silently establishes gifting/refund/charge policy, amount limits or supported merchant coverage.

**Risks:** parser mistakes despite correct totals; historical GST mistaken for modern SST validation; unknown original fixture rights; local vs controlled-server privacy conflation; CPU OCR blocking live edits; weak invitation identity/revocation; lost/offline edits; settlement disputes; unreviewed financial corrections; Notion number/permission/schema/plan limitations; partial/duplicate exports and stale lookup; model/package changes and incomplete phone testing.

**Recurring-cost conclusion:** executed local inference has no per-call model API charge. At measured medians,1000receipts imply about43.4/Rapid,237.6/Paddle or39.8/Tesseract wall-minutes, before concurrency/retakes. This is not billing. An Internet collaborative product still needs availability, TLS/auth, persistence/backups, image retention, bandwidth and controlled-server capacity. Notion Free may suffice only if its workspace/file/block limits fit. Exact host/plan/budget remains unselected; no hosting quote, paid vision purchase or production cost guarantee is made.

## Unresolved decisions requiring specification

- Invitation lifetime/revocation, identity recovery and organizer handover; whether organizer may override another diner's assignment and how consent/history are shown.
- Voucher as merchant discount versus prepaid tender/gift; eligibility, stacking/order, sponsorship and negative/refund/overpayment semantics.
- Percentage/quantity precision, stable rounding tie policy, per-item versus pooled residue; maximum amounts and transport bounds.
- Who confirms settlements and disputes; correction consent after settlement; cross-meal/group balances and initial refund scope.
- Target phones/browsers; device-only versus controlled-server default; receipt original retention/deletion and whether Notion receives an image copy.
- Notion connection type/actual workspace plan, compact versus full-detail export, raw REST authentication/media contract and permitted Notion-side edits.

Requirements already surface these decisions. They are not answered by a passing arithmetic experiment or framework popularity.

## Go/no-go for Phase 2

| Gate | Current disposition |
|---|---|
| Coherent integer-money domain and stress scenarios | **GO for further feasibility/spec work**; policies remain conditional |
| Local OCR installation/inference feasible | **GO for controlled local baseline**, not a production accuracy promise |
| Autonomous extraction / confidence-only acceptance | **NO-GO**; observed clean-but-wrong candidates |
| Representative Malaysian phone/SST/voucher accuracy | **NOT MET**; small historical/synthetic corpus and unreviewed annotation limits |
| Two-browser/phone live collaboration, reconnect and authorization | **NOT MET**; only domain concurrency simulation |
| Notion optional-copy shape | **GO for adapter contract validation**, not final production schema |
| Production REST/OAuth/media and workspace capability | **NOT MET**; connector and fake-remote evidence insufficient |
| Framework/database/hosting choice | **OPEN**; no unique winner or irreversible commitment |
| Production scaffolding/implementation/deployment | **NO-GO until explicit later approval**, regardless of experiment passes |

## Historical proposed Phase 2 scope — original approval requirement superseded

Recommend a bounded **feasibility-closure and implementation-ready specification** phase before committing production scaffolding:

1. Test actual Android/iOS capture/offline/model latency and two real browser clients, including stale same-item claims, aggregate overclaims, reconnect/replay, revoked invites and organizer finalization. Disposable UI/transport only, clearly separate from production.
2. Assemble a consented modern Malaysian dining corpus with independent reviewed labels and a held-out portion, including SST, real discounts/vouchers, shadows/perspective, modifiers and mixed scripts. Compare raw OCR versus parser failures; validate correction burden. Retain manual-first behavior and exclude hosted vision.
3. Validate raw Notion REST/OAuth and raster receipt upload/readback in a test destination, including local uncertain-write recovery against actual contract and account limits without deliberate quota exhaustion.
4. Resolve the policy/identity/retention questions above, set acceptance criteria and select the smallest stack from observed constraints. Present the proposed **manual-first collaborative MVP** slice, file layout/dependencies/security/backup plan and cost assumptions for a separate implementation approval.

This recommendation is intentionally narrower than authorization to build the app: important evidence is still absent. If the user instead approves a manual-first implementation before OCR automation is validated, its scope must explicitly keep OCR proposals nonauthoritative and retain these unresolved gates. No such approval is inferred here.

## Preserved scratch and stop point

[Private Notion scratch](https://example.invalid/notion/synthetic-notion-id-013) and its six child databases/nine rows remain disposable evidence under the connector's private-draft contract; ACLs were not independently audited. Cleanup instructions are in the Notion report. Existing workspace pages/data were not altered. All local experiments/results remain under `experiments/`; no production source directory exists.

**Historical stop point:** Phase 1 ended here under its original authorization. Later user delegation supersedes the phase-approval requirement. Current progression and human escalation gates are recorded in governance and the transition ledger.
