# Phase 1 product requirements

> Historical authorization context: this report predates the user's orchestrator delegation on 2026-10-16. Requirements for user approval of numbered phases in this snapshot are superseded by [current governance](../../docs/agents/governance.md) and the [transition ledger](../../docs/agents/phase-transitions.md). Evidence and capability limitations remain valid to the extent stated; private-data, spending and product-policy consent are still separate.

Status: draft requirements and decision frontier; 2026-10-16. This document distinguishes **mandated** requirements (user instruction), **proposed** behavior, and **unresolved** product choices. It is not approval to build the production app. Prior evidence: [Phase 0 domain](../domain-model.md), [comparison](../repository-comparison.md).

## Mandated scope

- Full workflow: receipt capture → extraction → human verification → participants → item/shared-item assignment → charges/discounts → per-person consumption → restaurant payer balances → actual/partial settlements → Notion reporting/synchronization.
- All monetary models, experiment inputs and outputs use integer minor units: MYR 12.30 = 1230 sen. Quantities/weights are exact rationals, separate from money. Unknown extracted amounts remain unknown, never zero by default.
- Extraction proposes values; human verification/correction remains required. Missing lines, guessed tips, stale assignments or plausible demo data cannot silently become liabilities.
- No production implementation/UI/scaffolding/deployment or irreversible stack commitment in Phase 1. Experiment locations and evidence labels remain explicit.

## Workflow and acceptance behavior (proposed)

| Stage | Input/action | Required visible outcome and gate |
|---|---|---|
| Capture | Camera or image file; manual entry escape | Preserve original, capture order and consent/retention context; mark blurry/incomplete image for retake rather than invent fields. Multiple-photo stitching is an open scope choice. |
| Extract | OCR/vision attempt, engine/model version | Structured proposal with raw evidence and field provenance. Separate unit price from line total, and printed subtotal from grand total/tender/change. Engine failure remains failure/manual entry. |
| Verify | Reviewer edits merchant/date/items/amounts/charges | Original and editable values can be compared; missing/ambiguous values and printed/computed discrepancy stay visible. Every financial edit invalidates prior confirmation. |
| People | Stable meal participant identities, optional known People records | Display names do not identify allocations. A payer may consume nothing; a diner may pay nothing. Guest/account/Notion-user identity are distinct. |
| Assign | Individual/shared items with equal/weight/quantity/percent/exact methods | Eligible people only; each item is fully assigned or has a visible unassigned amount. Quantity conservation separate from money conservation. |
| Charges | Explicit printed SST, service, discounts, rounding; inclusion/base reviewed | Allocate each signed component exactly once. Item-specific discounts follow eligible consumers. Printed included tax is informational, not an added charge. |
| Totals | Recalculate reviewed components and allocations | Per-person totals and their component breakdown sum exactly to the authoritative total. A reconciliation gate prevents finalization while mismatch/unassigned values remain. |
| Payers | Record actual restaurant contributions, multiple payers supported in analysis | Contributions do not change consumption. Funded status requires exact equality to authoritative total; partial funding is visible and not hidden as peer debt. |
| Settlement | Suggest transfers then confirm real transfers | Suggestions create no payment fact. Partial actual transfers reduce outstanding balances; repeated submission cannot duplicate a transfer. |
| Correction | Change a meal after finalization/settlement | New reviewed revision; preserve real restaurant payments and confirmed peer transfers. Show resulting new debts/refunds and require reapproval. |
| Notion | Export reviewed revision asynchronously | Pending/complete/failed status is separate from dining/settlement status. Failed/disconnected reporting does not lose or block the meal. Notion experiment will test this proposal. |

**Proposed states are orthogonal:** extraction/review; allocation/finalization; restaurant funding; peer settlement; external synchronization. A single linear status cannot faithfully represent a fully settled meal whose Notion export failed. A later correction can reopen review and balances without erasing an earlier actual transfer.

## Requirements decision tree

No row below is a silent user decision. Recommendations are defaults for analysis; unresolved preferences remain explicit. The first interview round has been sent; answers will be recorded here.

| ID | Decision and concrete stress case | Proposed disposition / open question |
|---|---|---|
| D01 | Who edits: one organizer or concurrent diners? | **User decision: several diners edit the same meal live.** One-editor recommendation rejected. Validate concurrent writes, revision conflicts, access roles, reconnection and duplicate submissions. |
| D02 | One versus multiple restaurant payers; A pays 7000, B pays 3600 on a 10600 meal | Model multiple contributions independently from consumption. **Proposed scope:** support in initial acceptance model; user can simplify UI later without collapsing domain facts. |
| D03 | One dish shared among three; tiny total leaves a residual sen | Equal/shared weights and deterministic largest remainder. Every sen assigned exactly once; deterministic tie policy shown in experiment. |
| D04 | Three drinks, one person consumes two | Quantity shares are rationals summing to line quantity; derive money from authoritative line amount, not repeatedly multiplied unit price. Modifiers may be standalone priced lines or child labels; never silently count both. |
| D05 | Exact/custom/percentage allocations | Equal, rational weight, quantity, exact percentages and exact sen are distinct modes. Exact amounts must sum exactly; percentages must total exactly 100. Basis-point versus finer rational input precision remains a transport/UI decision before implementation. Invalid input rejected, not normalized into a different promise. |
| D06 | SST 600/service 1000 on a meal; tax printed as included | Prefer reviewed printed amounts; inclusion, eligibility and base explicitly represented. No guessed legal SST rate/base. If rate reconstruction is needed, human chooses the base and confirms result. |
| D07 | Meal-wide service and item-only charges | Default proportional eligible consumption, with explicit equal/custom override. Different charges can have different bases. **Unresolved:** exceptional tip/fee defaults. |
| D08 | RM10 voucher vs RM10 prepaid gift card | **Critical distinction:** restaurant discount reduces consumption/payable; prepaid payment instrument funds the bill and may credit its contributor. **Unresolved:** ownership/gift policy, item eligibility and promotion ordering. Do not treat every voucher as a discount. |
| D09 | Printed cash rounding versus sharing residuals | Cash rounding is a separate signed receipt component, never automatic individual 5-sen rounding. Sharing residuals are internal sen distribution, not a new charge. |
| D10 | Printed total 10600; reviewed components 10599 | Block finalization until corrected or reviewer records a visible justified 1-sen adjustment. Never silently accept a tolerance or fabricate an item/fee. Draft discrepancy is diagnostic, not a payable item. |
| D11 | OCR turns quantity two line total 2000 into unit price 2000 | Preserve printed unit/line evidence; canonical line total authoritative after review. Re-extraction is a new proposal, cannot overwrite approved allocations automatically. |
| D12 | New diner joins after others allocated | Joining does not retroactively join every shared item. Explicitly edit eligible assignments and recalculate; acknowledge changed cents. |
| D13 | Assigned diner leaves | Draft removal must clear/reassign their allocations visibly; no implicit split-everyone fallback. Finalized identities/history cannot simply disappear; amend revision and preserve payment/settlement facts. |
| D14 | A partial peer payment before all debts settle | Confirm exact amount/currency/from/to once; balance updates without changing receipt/consumption. Overpayment must be visible as credit/refund, not discarded. |
| D15 | Receipt corrected after paid: C already sent A 2000 | Preserve transfer; recompute revised net balance and expose any refund/new debt. A correction is not a fictional reversal of cash already exchanged. |
| D16 | Repeated visit/group history, gifts, refunds and cross-meal netting | **Unresolved:** initial scope. Recommend MYR dining meals and explicit transfers first; cross-meal simplification opt-in, refunds/gifting specified before enabling, no automatic FX. |
| D17 | Offline/privacy, native versus browser | **User decision: device or self-hosted OCR only for product and Phase 1; no third-party hosted vision calls.** Self-hosted OCR still transfers images to the controlled server. Browser cannot assume native OCR APIs. |
| D18 | Notion role and editing rights | Evaluate A operational DB, B sync/report, C optional export. **Proposed:** B delivered as optional C; Notion-owned notes may remain editable while amounts originate in reviewed ledger. Not yet final. |
| D19 | Corpus, hosted OCR consent/budget | **User decision: local processing only, no hosted image calls; no private receipt folder.** Exclude direct hosted vision and cloud recovery from executed comparisons. Public historical and clearly synthetic local fixtures only, with rights limits recorded. |

## Reconciliation rules

See [domain model](domain-model.md) for exact equations and executable stress cases. During incomplete review, show missing values and diagnostic discrepancy; do not claim a finalized allocation. When authoritative total is known, display `total = assigned + unassigned + discrepancy` with each nonzero bucket visible. Finalization requires unassigned=0, discrepancy=0, no unknown required amounts, and exact component/item conservation. Funding and settlement are separate gates.

## Interview ledger

Round 1 answered: **several diners edit the same meal live**; **local processing only, no hosted image calls**; **no local receipt folder**. No USD 1 hosted budget was approved. Round 2 answered: **private internet invitation links**; **organizer controls receipt amounts and finalization, diners edit their own assignments**; **future product OCR on device or self-hosted only, no third-party hosted vision**. These replace the one-editor Phase 0 preference. Invitation lifetime/revocation, settlement confirmation authority and retention policies remain open; experiment defaults do not settle those choices.

## Phase 2 entry requirements (draft)

A scoped editor/collaboration/privacy/Notion decision; validated invariant scenarios; representative corpus and honest per-field metrics; feasible OCR path or deliberate manual-first fallback; current Notion behavior verified to the extent claimed; stack comparison based on observed constraints; explicit approval for the proposed next scope. Any missing data/credentials/real-device access must remain a named limitation.


## Live collaboration: added validation requirements

**User decision:** simultaneous diner editing is a product requirement, not a future optional feature. Financial computation remains integer-sen deterministic, but correct arithmetic alone does not prevent lost updates. The disposable concurrency experiment exercised stale revisions, safe distinct-item edits, simultaneous same-item edits, duplicate operations, reconnect/replay, unauthorized mutation, finalization against a changed revision and receipt corrections after settlement.

**Proposals to test, not selected architecture:** a shared authority serializes accepted financial edits; a stream of updates communicates committed revisions. A network broadcast is not a durable ledger. Never silently use last-writer-wins for amounts, allocation ratios or transfers. Offline clients may retain drafts but cannot claim finalization/settlement confirmation until accepted against current state. Person membership, edit permissions and claimed meal share remain separate.


## Confirmed collaboration and privacy target

User confirmed private internet invitation links with meal access checks; organizer controls receipt amounts/charges and finalization while diners edit their own assignments. Invitation possession and participant identity still need a revocable authorization design. Organizer adjustments invalidate stale allocation/finalization revisions; independent diner claims must be reconciled against available item quantities. Device/self-hosted OCR only: no third-party hosted vision even as fallback. A self-hosted local model is allowed conceptually but unmeasured unless explicitly run; manual correction remains the practical fallback.
