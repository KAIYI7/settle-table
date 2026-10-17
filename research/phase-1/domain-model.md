# Phase 1: dining-domain validation

Status: **experiment complete; product policies unresolved**, 2026-10-16. Requirements/technical validation only; no production implementation or approved architecture decision. Start with [prior domain research](../domain-model.md), [Spliit report](../repositories/spliit.md), [SplitPro report](../repositories/split-pro.md), and the vocabulary in [GLOSSARY.md](../../GLOSSARY.md). Product decision prompts are coordinated in [requirements.md](requirements.md).

## Evidence categories

- **Source fact:** previously inspected source with exact revisions; linked reports carry file permalinks and access dates. No upstream source is copied into the experiment.
- **Experiment:** results from disposable Python standard-library arithmetic/state scenarios under [experiments/domain](experiments/domain/), to be recorded with exact inputs, seed, assertions and machine-readable output.
- **Proposal:** candidate dining behavior supported by arithmetic but awaiting product approval.
- **Unresolved:** policy choices cannot be established by source review or successful arithmetic.

## Scope and initial findings

**Source fact:** Spliit `5dac4119f0441cb945756f8c92911de6f312a1a3` demonstrates conserved integer minor-unit allocation with largest remainder; its JavaScript intermediate multiplication still requires bounds. SplitPro `3583568319807e193fbe57085ea9560a2e872b93` uses BigInt storage, signed participant amounts and a single payer. Neither supplies a full receipt-item/charge/multi-payer model. See the two reports above for exact file references.

**Proposal under experiment:** distinguish receipt evidence, consumption allocation, restaurant payer contributions and actual participant settlements. Represent money as integer sen and quantities/weights as exact rational numbers. Reject unresolved discrepancies rather than creating an unexplained balancing amount. Compare charge/voucher policies explicitly instead of guessing the user's preference.

**User confirmed:** several diners edit live over private internet links; organizer controls amounts/finalization, diners their own assignments; device/self-hosted OCR only. **Unresolved:** how joins/leaves change historical claims, whether vouchers are discounts or payment instruments, fee/discount eligibility and base ordering, inclusive charge presentation, settled-meal corrections and sponsorship. The experiment will show consequences of explicit alternatives; passing an invariant does not settle these product choices.

## Executed experiment and reproducibility

**Experiment:** [validate_domain.py](experiments/domain/validate_domain.py) uses only Python standard library (`fractions.Fraction`, integer arithmetic, deterministic SHA256 tie order and seeded `random.Random`). It is an independent disposable scenario runner, **not a copied upstream helper, app module, production abstraction or production test suite**. Its small pure allocation interface accepts signed integer sen, exact weights and a stable component identity and returns conserved integer allocations. State scenarios explicitly supply consumption, restaurant payments and transfer snapshots; no I/O/network side effects occur except writing the result artifact.

- Coordinator reran current script using Python **3.14.6**, seed **20261016**, **3,000** randomized trials.
- **67 concrete scenarios passed**, including integer-input rejection, expected conflict/rejection and policy comparisons.
- **33,000** allocation/settlement assertion groups plus **21,000** multi-item/charge groups passed (**54,000 total**). These are experimental assertions, not production coverage or a proof for every input.
- Current script SHA256 **`112d0c6f73906e49514df214bdf96c8dde34d478bea2e4b8fcd88f3937d814dc`** and result SHA256 **`f49bc1022ce43dad0c77c2ada90ef02fda6e84f3bed79d0cd1b88f4cd5050c50`** recorded in [verification.json](experiments/domain/verification.json). Earlier counts/hashes belonged to the pre-review script; they are superseded after coordinator found and closed unvalidated monetary interfaces and suggestion-state ambiguity.
- Every input/result/rejection is in [results.json](experiments/domain/results.json). Suggestions now carry suggested state; a separate explicit simulation action confirms them before accounting.

From the project root:

```powershell
python research/phase-1/experiments/domain/validate_domain.py --output research/phase-1/experiments/domain/results.json --seed 20261016 --trials 3000
```

**Experiment limits:** synthetic scenarios dominate; only one real historical receipt's arithmetic is manually transcribed here. No accuracy, performance, concurrency, authorization, durability, integration, production-bound overflow or end-user usability claim follows. Python arbitrary integers were deliberately stressed beyond SQL BIGINT/JavaScript bounds (maximum random amount recorded as an exact decimal string); production limits and transport types remain a separate decision. No binary monetary float occurs. Tests do not establish a universal fee/voucher/refund policy or a minimum-transfer optimality proof.

## Behavior coverage and consequences

| Behavior | Experiment evidence | Proposal / unresolved consequence |
|---|---|---|
| Equal shared item | 1000 sen → one 334 and two 333 shares | Deterministic tie identity must be stable across preview/save/export; specific hash policy remains unapproved. |
| Custom rational weights | `1/2:1/3:1/6` of 1000 → 500/333/167 | Weights are ratios; they are not amounts already paid. |
| Rational quantities | Quantity `5/2`, claims `1` and `3/2`, line 2500 → 1000/1500 | Missing/excess quantity is rejected under the full-assignment variant; distinguish quantity claims from freely chosen weights. |
| Percentage/exact amounts | 33.33/33.33/33.34 percent conserves 10000 sen; exact 1+999=1000 accepted | Percentages must sum to 100 exactly; exact amounts must sum exactly. Do not silently normalize invalid exact inputs. Percentage precision choices remain open. |
| Invalid input | Duplicate people, negative weights, noninteger money, extra fractional sen and ambiguous separators rejected | An input/OCR review step must resolve locale/quantity/label ambiguity; no silent trimming or float rounding. |
| Scoped printed SST/service | Food A1000/B2000; drink C1000 excluded; tax180 → A60/B120; service300 → A100/B200 | Scope/base is explicit per charge. The examples do not establish Malaysian tax rates or taxable categories. |
| Targeted discount | B-only discount500 follows B; A-only discount500 changes a fixed300 service split from100/200 to60/240 if using discounted bases | Pre-/post-discount bases can change individual liability even while total is fixed. User must select policy; do not infer from a generic subtotal label. |
| Voucher alternatives | Merchant discount1000 reduces10000 consumption to9000. Prepaid tender1000 keeps10000 consumption and credits its owner as payer | Discount, tender and sponsorship are different economic events. Voucher ownership/benefit remains a product question. |
| Oversized discount/credit | Conservative variant rejects discount1001 against base1000; explicit-credit variant permits net−1 | This is a policy comparison, **not a universal cap**. Never clamp away real refunds/credits. Refund obligations need separate user-approved treatment. |
| Rate versus printed amount | On3000 base with600 discount, illustrative rate1/10 yields300 before discount vs240 after | Preserve a reviewed fixed printed charge when present; deriving missing charges from rates requires explicit base/order. |
| Included tax | Included60 in gross1060 is informational; adding it again fails reconciliation | Keep tax presentation/basis separate from whether it adds to amount due. Historical real example below sharpens this. |
| Printed rounding | Signed±2 sen is a component, separately allocated/conserved | Printed cash rounding is different from distribution residue. Whom it affects remains a fee policy question. |
| Zero base | Positive100 charge on zero eligible consumption rejected; an explicit equal-weight human choice produces50/50 | Do not divide by zero or secretly assign to payer/uploader. A choice of a different base must be explicit. |
| Draft/review gates | Unassigned amounts, wrong canonical subtotal, final-total mismatch and ambiguous unit/line meaning block finalization | Diagnostic discrepancies explain incomplete drafts and never become hidden payable adjustments. |
| Multiple payers | Consumption2120/3180/5300; payer7000/3600/0 → net4880/420/−5300 | Restaurant payments are independent facts; payer need not consume. Incomplete funding is visibly different from fully funded settlement readiness. |
| Partial/full settlement | C→A2000 leaves2880/420/−3300; subsequent suggestions clear all balances | Suggestions are not confirmed transfers. Pending transfers have no confirmed-accounting effect. |
| Duplicate/conflicting transfer | Same immutable confirmation counted once; changed payload with same ID rejected | This validates an idempotent snapshot calculation, not a real transaction/locking design or pending→confirmed persistence flow. |
| Settled correction/reversal | Move100 consumption A←B after fully settled → A owes100, B receives100; reversing confirmed2000 transfer reopens original debt | Preserve actual historical transfers; a proposed correction may reopen settlement. Who approves/receives notifications remains unresolved. |
| Overpayment | Owed100 but transfer101 creates reverse1 debt | Display/correct overpayment explicitly; do not silently discard it. Whether to block it before recording remains open. |
| Join/leave | New D with no claim leaves historical balances unchanged; removal with consumption/payment/transfer history rejected; unused D removable | This is a **history-preserving policy variant**. Current meal membership, historical identity and access rights are distinct. Joining need not imply retroactive equal sharing. |

## Real receipt: printed net subtotal can differ from item-line sum

**Verified visual fact, accessed 2026-10-16:** local SROIE image [X51008030563.jpg](experiments/ocr/data/images/X51008030563.jpg), RESTORAN WAN SHENG, printed date **02-04-2018**, shows:

- Milo quantity2 × unit280 sen = line560 sen.
- Take Away quantity2 × unit20 sen = line40 sen.
- Item-line sum **600 sen**; printed total excluding GST **566 sen**; printed included GST **34 sen**; printed inclusive/final total **600 sen**.

Image SHA256 **`4ebb8257cd1bc9dafb5b40d8c48e8318260ce08fa19cb68dbd86499182412e7c`**. Provenance/license limitations are in [OCR validation](ocr-validation.md); curator source [jsdnrs/ICDAR2019-SROIE](https://huggingface.co/datasets/jsdnrs/ICDAR2019-SROIE). This historical GST example makes **no current SST-rate or tax-compliance claim**. Quantity/unit/line facts were visually checked here, independently of OCR output.

**Experiment:** case `real_2018_wan_sheng_inclusive_gst` retains **canonical gross item subtotal600** and **printed net subtotal566** as separate observations;34 is informational included tax and is not added again. Illustrative equal allocation gives300 each. Incorrectly using566 as the canonical gross item subtotal or multiplying already-complete line totals by quantity is rejected.

**Correction to prior broad wording:** [Phase0 domain research](../domain-model.md) suggested matching chosen item lines to a canonical subtotal but could be read as matching every printed subtotal. The scan disproves that stronger reading. A valid canonical item basis and the receipt's other printed subtotal observations must coexist. A printed net subtotal differing from gross lines is **not automatically an OCR error**.

## Draft equation and finalization gate

**Proposal supported by scenarios:** within one reviewed monetary basis,

`receipt total = assigned consumption + unassigned consumption + diagnostic discrepancy`

For total1060, assigned600 and unassigned400, the discrepancy is60. This indicates incomplete receipt interpretation; it is **not** a payable fee or an amount to allocate invisibly. Finalization requires zero unassigned consumption **and** zero diagnostic discrepancy, plus resolved unit/line/tax inclusion meanings. Known charge allocations count in assigned/unassigned consumption; they must not be omitted and then rediscovered as a mysterious difference. Distinguish a real printed rounding amount from an invented adjustment inserted to force the equation.

**Proposal:** retain raw printed labels/values and selected canonical basis, review issue list and revision identity. Reviewed fixed charge totals, component eligibility and component ordering determine the calculation; the experiment cannot establish their correctness from arbitrary OCR strings.

## Conserved arithmetic does not imply universal fairness

**Experiment counterexample:** largest remainder on weights1500/1500/900/500/500/200 assigns the two500-weight people3 sen each when total25, but2 sen each when total26. Money is conserved and each allocation stays within1 sen of exact quota. Per-person monotonicity is not guaranteed. Stable tie breaking does not eliminate this phenomenon.

**Inference:** avoid promising that a higher total always raises every individual's cost. Splitting/merging line items, changing charge bases, or editing scope can shift residue. Preserve stable component IDs and show revisions and per-component explanations. User-visible fairness, pooled versus per-item rounding and whether to preserve already-confirmed allocation snapshots remain product choices. The experiment establishes conservation for the tested algorithm, not approval of its fairness policy.

## Settlement equation and history

**Proposal supported by scenarios:**

`net = restaurant payer contributions − consumption + confirmed settlements sent − confirmed settlements received`

Positive means to receive; negative means to send. Suggestions do not change net; confirmed transfers do. Total net remains zero for a funded meal; an unfunded meal has a funding discrepancy and should not be presented as fully settled. Actual transfers remain facts after allocation correction, so a previously settled meal may reopen. An amendment/reversal must have explicit identity and history; this runner uses transfer snapshots and does not commit to event sourcing, database schema or immutable storage design.

## Remaining product decisions and next use

**Unresolved:** fee/discount/voucher eligibility and ownership, inclusive/exclusive display, base ordering, special diets/alcohol exclusions, sponsorship, negative-consumption/refund semantics, zero-base fallback, tie policy, pooled versus per-component rounding, membership/edit permissions, confirmation/disputes, settled correction consent, overpayment restrictions, funding incompleteness, currencies and limits. Cross-meal aggregation is unvalidated. None is silently selected by a passing experiment.

The coordinator should derive final requirements from user answers and this evidence before proposing app work. No ADR is created: alternatives remain provisional, and this experiment does not commit an irreversible architecture.


## Live-edit extension

User selected simultaneous diner editing after the arithmetic runner was built. [Collaboration simulation](experiments/collaboration/simulate.py) adds **17 passed checks**, including a real two-thread race (one commit, one stale rejection), distinct-item edits, quantity overclaim prevention, conflicting operation IDs, role/revocation checks, stale organizer finalization, amount-edit re-verification, explicit amendments, and reconnect/out-of-order snapshot handling. [Results](experiments/collaboration/results.json). A last-writer-wins counterexample loses a diner claim.

**Conclusion:** a shared authority must validate accepted financial revisions; broadcasting updates alone cannot establish correctness. Per-item and financial revision checks are one tested proposal, not an approved production protocol. This simulation has no sockets, browser clients, real invitation identities, persistence or Internet latency measurements. Full multi-device collaboration remains a Phase 2 acceptance gate.
