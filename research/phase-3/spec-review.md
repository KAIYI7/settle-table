# Independent financial/specification review

2026-10-16. **PASS for the bounded pure-calculation and money-text-parser slice. No blocking correctness/specification finding identified in this review.** This is advisory evidence for the orchestrator, not transition authority and not approval of a complete MVP or deployment.

## Fixed review scope

Reviewed actual full [production calculation source](https://github.com/KAIYI7/settle-table/blob/af7ba147642b8b8e9a5aee973a95c59d46c38b9a/tabwise/calculation.py), [public-interface tests](../../tests/test_calculation.py), [interface documentation](../../docs/calculation-interface.md), [implementation log](implementation-log.md) and the accepted [C1–C4 specification](../phase-2/mvp-specification.md). Baseline: [review-baseline.json](review-baseline.json).

- `tabwise/calculation.py` SHA256 `4e448475892293ec9f252e1c769ef8b4699c7874c7eeefe8d73d9e16e1ccab3a`.
- `tests/test_calculation.py` SHA256 `70d6dab36179bc2672712b236eea54d0313c85a2fd5a54480e03aefdbefea80c`.

The reviewed implementation has no funding/actual-transfer ledger, authentication, human-review assertion, accepted persisted revision, UI, HTTP, OCR, Notion or storage side effect. Review was against the bounded specification, not an unavailable Git diff. Earlier research code was inspected as counter-evidence; it was not treated as the production oracle.

## Independent executed evidence

[Adversarial cases](adversarial-cases.md) were prepared from the accepted specification before reading production source/tests. A separate disposable [probe runner](independent_probes.py) calls only public interfaces with literal expected results and malformed inputs. Executed against the frozen source: **66 checks passed, zero failed**. [Machine evidence](independent-probes.json) records each disposition and source hash.

The 66 checks are not 66 independent statistical observations or production coverage metrics. They are deliberately targeted functional/metamorphic acceptance cases. The production suite's 15 methods and red/green history are separately recorded by the implementer; this review does not relabel their subcases or claim to have witnessed every earlier TDD step.

Important executed literals:

- A1001/B2000 original item shares, scoped discount−101/tax174/service290/rounding1 → **A1122/B2243**, with independently specified component shares and total3365.
- Equal one-sen source `item` → A0/B1 under the exact accepted digest rule; full scoped `discount` removes B's sen → **A0/B0**, despite a different raw-quota tie order for that adjustment ID.
- Line1001, quantity3 claimed1:2 → **A334/B667**; the line is never multiplied to3003.
- A valid zero-valued item/meal remains0; a nonzero component on zero eligible base rejects, while an explicit equal override produces5/5 for10sen.
- Included tax34 does not turn gross600 into634; amount/subtotal mismatches reject without tolerances.
- Two overlapping discounts that yield a negative individual reject even when the meal's total is still positive.
- Source/component/participant/split-share reordering preserves immutable results; the documented25→26-sen nonmonotonic example remains visible.
- Negative/zero/malformed weights, foreign/repeated identities, scope collisions, conflicting allocation modes, bool/float money, invalid signs and representative bound violations reject through `CalculationError`.
- Decimal text accepts the specified unsigned ASCII grammar and rejects signs, locale separators, Unicode digits, exponents, whitespace, excess precision/length and over-bound money.

## C1–C4 and invariant inspection

| Concern | Source observation and result |
|---|---|
| Charge-base ambiguity | `by_item` is built from completed integer item allocations; every scoped adjustment recomputes its base from that map, not previous adjustments or unrounded quotas. PASS. |
| Negative discount residue | Magnitude is apportioned once using the declared base, then negated. Zero bases have zero quotas and cannot receive a remaining sen: when residue exists, the positive fractional remainders necessarily suffice before zero-remainder rows. Tiny full-discount probe confirms the important case. PASS. |
| Deterministic ties | Exact Fraction remainders precede SHA256 of compact ASCII JSON with the accepted version/domain/source/person fields; final ID tiebreak and sorted output remove input-order dependence. PASS. |
| Split meanings | Equal requires1; exact is integer source magnitude; percent totals100 exactly; quantity is item-only, positive, and conserves the explicit quantity; nonzero all-zero weights reject. PASS. |
| Bounds/types/identities | Exact tuple/model/int/Fraction checks reject bool/mutable or foreign shapes; registries/scopes have finite limits, source IDs share one namespace, rational/count/money bounds are checked. PASS for this typed local interface. |
| Receipt/final conservation | Canonical subtotal and added receipt total are exact hard gates; final participant consumption must be nonnegative, bounded and sum to receipt total. Included tax is informational. PASS. |
| Context/authority | No boolean attempts to prove human review. Documentation states calculation validates supplied mathematical facts only; future authority must establish current revision, review, membership and permission in its atomic operation. PASS for separation of responsibilities. |

## Limits retained for subsequent slices

No test here proves secure invitations, live collaboration, actual settlement confirmation, durable command identity or persisted financial finalization. Those remain later integration/security gates. The earlier suggestion-ID collision does not appear in this production slice because it deliberately implements neither suggestions nor transfers.

The typed Python contract does not supply an untrusted JSON parser/body limiter or labels/reviewer rationale; its documentation correctly assigns those to the later authority/transport layer. An external adapter must enforce limits before building these facts, translate structured errors, and never treat successful calculation as permission to finalize.

Negative/refund/sponsorship, rate reconstruction and compound promotion semantics remain unsupported under the accepted slice. A mathematical calculation passing cannot settle voucher ownership, settlement confirmation/dispute authority or post-settlement consent policies. Modern OCR/device accuracy and raw Notion delivery are unrelated to this slice's arithmetic acceptance and remain unproven.

The orchestrator should review actual artifacts and these results before recording any slice-completion decision. This review identifies no required implementation edit to the pinned snapshot.
