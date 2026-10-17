# Independent first-slice specification review

2026-10-16. Inspected [MVP specification](mvp-specification.md), [architecture decision](architecture-decision.md), [glossary](../../GLOSSARY.md), and the existing Phase 1 financial experiment. This is advisory review, not transition authority or an assessment that the whole MVP is ready.

**Disposition: CONDITIONAL PASS for the pure financial calculation slice.** Its runtime and interface can be selected independently of HTTP, UI, OCR, ledger persistence and Notion. Close the narrow contract clarifications below before treating the specification/tests as the production calculation contract. These are reversible engineering decisions for the orchestrator; none requires routine phase permission.

## Material clarifications before implementation acceptance

### C1 — Fix the exact proportional base and component ordering

The phrase “derive each eligible diner's base from reviewed item consumption” should explicitly mean **sum that person's already-apportioned integer item shares across eligible items**. Do not silently switch to raw pre-rounding rational item quotas. Declare whether adjustments use those original item shares unchanged by earlier adjustments; if that is the first-slice choice, components are independent printed amounts and input ordering cannot change results. Pre-/post-discount or tax-on-service bases remain unsupported unless explicitly modeled later.

New local adversarial probe against the existing Phase 1 `apportion()` (no runner/results changed):

```json
{
  "item_id": "item",
  "discount_id": "discount",
  "rounded_item_sen": {"A": 1, "B": 0},
  "incorrect_raw_quota_discount_sen": {"A": 0, "B": -1},
  "incorrect_final_sen": {"A": 1, "B": -1},
  "correct_rounded_base_discount_sen": {"A": -1, "B": 0},
  "correct_final_sen": {"A": 0, "B": 0}
}
```

A one-sen item split equally has only one residual sen. Reusing equal *raw* quotas for its full discount permits a different component-specific tie winner and creates an unsupported negative consumption. The rounded base assigns the discount to the person who actually received the item sen. Conservation alone would not detect the bad semantic result because A1+B−1 still sums to zero.

**Acceptance:** a fully discounted one-sen shared item returns both people zero; exclude zero-base participants from residual allocation; multiple independently scoped discounts cannot leave a negative final participant consumption. Reject unsupported negative results rather than changing the allocation method silently.

### C2 — Specify the deterministic tie contract

“Stable participant IDs with a component-specific deterministic order” gives a direction but not a reproducible contract. Select and document one rule before expected-value fixtures: for example, descending fractional remainder then a specified digest over unambiguous stable component/participant identity, with an explicit final ID tiebreak. Reject malformed IDs rather than silently normalizing distinct submitted IDs into one identity. Reordering participants/items/components must not change a result keyed by the same identities.

There is no requirement to copy the experiment's SHA256 rule. If it is retained, state encoding/domain separation and preserve IDs across amount edits. This is an engineering determinism decision, not a promise of fairness or monotonicity.

### C3 — Make validation bounds and invalid split behavior concrete

The specification correctly requires limits but leaves every value deferred. Record actual conservative limits in the contract/constants before implementation acceptance: amounts and aggregate totals, participant/item/component counts, ID/label/input lengths, rational numerator/denominator or decimal precision, and percentage/quantity bounds. Validate types and bounds before constructing large Fractions or iterating untrusted collections. Reject booleans wherever an integer is required.

Explicitly reject **negative weights**, all-zero weighted/equal-eligible bases for nonzero amounts, repeated participants within one split, foreign/duplicate scope IDs, unknown split modes and unexpected fields that could be misinterpreted. A participant may legitimately appear on several items; uniqueness rules must be per participant registry and per individual split, not globally across all allocation rows.

Distinguish a zero-value item from a missing amount. Define zero-total behavior with at least one valid participant and complete explicit assignments. Document whether ID namespaces are separate or item/adjustment IDs must also be mutually unique; preserve enough identity to identify the financial source of every residual sen.

### C4 — Clarify signed component semantics and unsupported bases

If component kinds are tax/service/discount/rounding, define the accepted sign matrix and the explicit-split representation. For the proposed nonnegative first slice, positive merchant discounts, unsupported refund-like negative tax/service, and discounts beyond their declared eligible base should not acquire meaning merely because the final meal total remains nonnegative. Printed rounding may be signed. If the design intentionally uses a generic signed adjustment instead, label that clearly and require its reviewed meaning at the authority layer.

Every component needs one unambiguous allocation mode: proportional eligible item shares **or** explicit exact/equal/custom allocation. Do not accept contradictory scope and override fields or default a zero-base component to “everyone.” An explicit override does not waive the nonnegative final-consumption restriction.

## Reviewer/context invariant: keep the correct responsibility

The pure calculator cannot prove that a human reviewed receipt evidence, that the caller is organizer, or that its input is the current persisted revision. Do not add a `reviewed=true` field and claim that it establishes any of those facts.

The specification already assigns atomic current revision, access, no unresolved issues, human verification and final reconciliation to the future authority. Keep that explicit: calculation establishes mathematical validity of supplied facts; authority establishes accepted/reviewed contextual validity. A caller can calculate a draft preview without being allowed to finalize it. Missing required monetary/model facts must still reject at the calculation interface.

**Integration acceptance, later slice:** stale or unreviewed financial data cannot finalize even if the pure calculation succeeds; a current reviewed revision cannot finalize with a calculator rejection. These are later authority gates and do not block implementing the isolated calculator after C1–C4 are specified.

## What is already well supported

- Python standard library is sufficient for exact integer/Fraction calculation and tests; no frontend/server framework choice is necessary for this slice.
- Included tax and canonical versus printed subtotal are correctly separated; quantities do not multiply complete line totals again.
- Consumption, restaurant funding, confirmed actual transfers and reporting are separate facts. The first calculation slice appropriately excludes settlement identity and policy rather than hiding them inside arithmetic.
- Exact percentages and sen splits reject mismatches rather than silently normalizing. Final reconciliation has zero tolerance.
- Independent expected-value tests, malformed-input tests and preserved largest-remainder counterexamples are expressly required. Do not reconstruct the production algorithm inside the test oracle.
- The specification retains the full collaborative product objective while gating later capabilities; a calculator is explicitly not the entire MVP.

## Suggested acceptance examples after clarification

1. One-sen equal item and full scoped discount → all zero, regardless of different component IDs and input order.
2. Weighted 1001 sen at 1:2 →334/667; exact allocations/per-item shares/components all reconcile independently.
3. Scoped charge excludes people with zero eligible rounded item consumption, including zero-money shares from tiny items.
4. Reversed participant/item/component input sequences preserve results by stable IDs.
5. Two individually plausible overlapping discounts that make one final consumption negative reject; no clamp or redistribution.
6. Empty/duplicate/foreign IDs, negative/all-zero weights, bool money/quantities, oversized rational inputs and extra conflicting mode fields reject predictably.
7. Included-tax gross600/net566/tax34 remains600; unexplained1-sen receipt mismatch rejects.

After these contract details are recorded and reviewed, isolated implementation can proceed without phone hardware, OCR quality claims, Notion credentials or public deployment. This review supplies evidence to the main orchestrator; it does not authorize the transition itself.
