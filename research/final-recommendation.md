# Final recommendation

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../docs/agents/governance.md) and the [transition ledger](../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Access date **2026-10-16**. Status: source/document research complete; no application implemented. Recommendations are **inferences/proposals**, not approved production decisions. Read [comparison](repository-comparison.md), [licensing](licensing-and-reuse.md), [domain](domain-model.md), [OCR](ocr-evaluation.md), [Notion](notion-architecture.md), [technology](technology-options.md) and [cost/risk](costs-and-risks.md) for evidence and limits.

## Recommended path: C

**Build a small new shell while borrowing proven architectural patterns**, with optional narrowly scoped MIT helper reuse only after provenance and stack review. No inspected project combines correct itemized dining allocation, multiple payers, explicit charges, human receipt correction and reliable Notion synchronization. Combining whole modules would import competing domain models, extra services and avoidable defects.

| Path | Assessment |
|---|---|
| A. Fork/adapt an existing app | Not preferred. BillSplit lacks a ledger and fee policies; Spliit/SplitPro lack item/charge/multi-payer schemas; other references have licensing or correctness obstacles. Sensible only if product requirements pivot to the parent app's primary use case. |
| B. Compose licensed modules | Possible selectively, but not the primary plan. Shared UI functions and arithmetic helpers may be reusable; independent models do not compose unchanged. Attribution and dependency/algorithm provenance checks still required. |
| **C. New small shell + proven patterns** | **Preferred.** Keep dining concepts explicit, arithmetic deterministic and adapters optional. Borrow workflows/test invariants; avoid recreating broad expense-management/banking systems. |
| D. Notion-first/no-code or native-first | Notion-first fails interactive/transactional needs. Native-first may win if strict device-only OCR/offline is mandatory, but that requirement is unresolved. |

## Hypotheses: verified, revised or still unproven

| Original hypothesis | Conclusion derived from persisted findings |
|---|---|
| BillSplit for receipt/item allocation UX | **Supported as a pattern.** Guided editable receipt → people/item chips → summary is useful. Its equal tax/tip allocation, guessed suggested tip and persistence gaps should not carry over. |
| Spliit for group/expense/balance behavior | **Supported with boundaries.** Group-local identities, balances, conservation tests and deterministic shares are strong references. Add dining items, charges and independent payer contributions. |
| SplitPro for precision/splits/settlements | **Partly supported; uniqueness rejected.** BigInt/currency boundaries, split choices and settlement records are useful. Spliit already has largest-remainder integer allocation; no need to import both engines. SplitPro signed net/single-payer rows are not our proposed source facts. |
| Local OCR for zero/low cost | **Feasible candidate, not established accuracy or lowest total cost.** No mandatory paid OCR API, but hardware/latency/model delivery and parser development cost remain. |
| Confidence-based AI fallback | **Recommended experiment, not a verified existing module.** ReceiptIQ and the Malaysian Paddle example call configured LLM parsing on every receipt. Confidence scores are not calibrated probabilities. Retain evidence and use arithmetic/field gates plus explicit consent. |
| Proportional tax/service/discount | **Recommended default with eligibility/override.** Allocate printed fixed amounts by relevant consumption using conserved minor units; item coupons/inclusive taxes/rounding require separate treatment. Do not assume a legal SST rate/base. |
| Notion as durable storage/reporting | **Supported as an optional durable copy/report.** Keep canonical ledger independent; one-way asynchronous synchronization initially, revision markers, retry/reconciliation and compact export. Notion is not the sole backup. |

## Proposed technical direction

**Product stack inference:** React/TypeScript/Next.js with a transactional relational ledger is the provisional preference for a shared mobile-browser product and secret-backed Notion integration. Vite SPA + small API is the leading alternative for a personal/local-first tool. An optional Python OCR worker is justified only if RapidOCR/Paddle materially beats browser OCR on target receipts. Native OCR remains an alternative if strict device-only offline operation dominates. No stack or framework skill is installed in this phase.

**Domain proposal:** store items/consumption allocations, scoped adjustments, payer contributions and actual settlements as separate facts. Use exact minor units, deterministic largest remainder per component, clear quantity semantics, server-enforced reconciliation and immutable/audited finalized revisions. Suggestions to settle are distinct from confirmed transfers. See worked two-payer example/invariants in [domain model](domain-model.md).

**Extraction proposal:** camera/upload → private original/processing copy → local OCR with boxes/scores → deterministic structured proposal/reconciliation → editable review. Ambiguous results may use optional bounded vision fallback; failed extraction goes to manual entry, never plausible demo values. Review remains necessary after valid JSON or a matching total. Select engine/provider by measured correction effort and privacy, not examples' defaults.

**Notion proposal:** Meals, People, Receipt Items, Item Allocations, Payers and Settlements, stable app IDs/revisions and private receipt copies. Support compact export where Free-plan volume matters. Current source docs distinguish data sources/database containers, 5 MiB Free uploads, plan-dependent rate windows and multi-member block limits/exemptions. No workspace modified.

## Environment result

Installed current official published Matt collection (27 manifest entries, version 1.3.1, exact SHA recorded) plus Impeccable 4.6.0 at project `.agents/skills`. Verified all 141 upstream files after line-ending normalization, and official Windows engine checksum/version. Existing global skill copies preserved; duplicates/host limitations are documented. No framework/design collection added on top of Impeccable. Official Vercel React and web-design skills evaluated; defer React performance skill until stack approval and omit overlapping web-design audit initially. Details: [agent skills](agent-skills.md).

Tracker/label/domain setup is complete following explicit user approval of the [configuration draft](skill-configuration-draft.md). [AGENTS.md](../AGENTS.md) preserves Context7 instructions and references the three `docs/agents/` convention files. This approval covers administrative setup only; the next phase below remains unapproved. No global settings or hooks changed.

## Recommended next phase — requires explicit approval

A bounded **requirements and validation phase**, before application implementation:

1. Confirm personal/shared usage, guest permissions, offline/privacy constraints, fee rules, expected volume and Notion workspace/integration type.
2. With consent, assemble a representative Malaysian receipt corpus (proposed 50–100 images across merchants/scripts/quality/charge formats), manual ground truth and a held-out set. Confirm fixture rights and redact personal data.
3. In isolated experiments, compare device/browser baseline and RapidOCR/Paddle, plus optional capped hosted fallback. Measure field/line totals, omission/hallucination rate, exact reconciliation, correction time, mobile latency/RAM and escalation spend. Record versions/hardware. No production shell yet.
4. Turn [domain invariants](domain-model.md) into an approved acceptance specification: shared dishes, quantities, scoped discounts, tax inclusion, tiny residuals, multi-payers, partial settlements and edits after settlement.
5. Validate Notion quota/schema/file/retry behavior in a user-approved test workspace, including a partial/uncertain write and duplicate retry. Confirm compact versus full export.
6. Select/pin the stack and licensed dependencies, document decisions and propose the smallest implementation slice for explicit approval. Keep bank sync, FX and autonomous payments out of the initial scope unless newly required.

**Unresolved:** best OCR engine/accuracy, exact hosting bill, private receipt policy, target workspace capacity and collaboration requirements. Upstream tests were inspected, not executed; no performance or coverage percentage is claimed. All critical recommendation claims were checked by the coordinating agent against source/documents; verification notes are in [review record](verification.md).

**Stop boundary:** this document is a recommendation only. Neither this proposed validation phase nor application implementation has begun; user approval is required to proceed.
