# Independent financial acceptance cases

Prepared 2026-10-16 from the accepted [slice specification](../phase-2/mvp-specification.md), before reading the production implementation or its tests. These are literal expected results and rejection cases for the independent specification review, not implementation-derived test oracles. No claim of execution yet.

## Literal valid cases

| Case | Explicit financial facts | Expected result |
|---|---|---|
| Unequal quantity | Line1001 sen, total quantity3; A claims1, B claims2 | A334/B667. Line remains1001, never3003. |
| Multi-component original base | One line3001 exact A1001/B2000. All scope the original line: discount−101, tax174, service290, rounding1. Authoritative total3365 | Discount A−34/B−67; tax A58/B116; service A97/B193; rounding A0/B1. Final A1122/B2243. Reversing component order has no effect. |
| Tiny full discount | Source ID `item`,1 sen shared equally by A/B; scoped source ID `discount`,−1 sen | Under specified tie rule item A0/B1; discount A0/B−1; final A0/B0. Discount cannot use fresh equal raw quotas. |
| Zero-valued item | Valid participants A/B, explicit equal assignment of0-sen item, subtotal/total0 | Both0; missing or invalid assignment is not excused by zero money. |
| Explicit zero-base override | Zero-sen item; added tax10 with explicit equal A/B split, no item scope; total10 | A5/B5. The explicit choice is modeled, not inferred. |
| Included-tax information | Gross item600 split exact A300/B300; included tax34; printed net observation566 outside canonical gross subtotal; total600 | A300/B300; no added34. |
| Largest-remainder counterexample | Source `paradox`, weights A1500/B1500/C900/D500/E500/F200 |25 sen → A7/B7/C4/D3/E3/F1;26 sen → A8/B8/C5/D2/E2/F1. |
| Decimal text | `12.30`, `12.3`, `0`, `00012.3` |1230,1230,0,1230 sen. |

Tiny tie expectation was independently derived from the *specified* ASCII compact JSON domain-separated digest rule: among A/B, source `item` orders B before A; source `discount` orders A before B. These precomputed facts are literal fixtures, not a second apportionment implementation inside an expected-value function.

## Rejection and metamorphic cases

- Two source lines100 each, A owns the first and B the second. Discounts−100 and−1 both scope the first line; total99. Reject negative final A consumption even though total remains nonnegative and each amount is an integer. No clamp or transfer to B.
- A free item is assigned to A; a separate100-sen item is assigned to B. A tax10 scoping only the free item rejects zero eligible base even though the meal has positive consumption elsewhere. Explicit equal/custom override needs a different valid representation.
- Scope and explicit split together reject; empty/duplicate/foreign scope IDs reject; quantity-mode adjustments reject.
- Negative tax/service, positive discount and unknown adjustment kinds reject. Signed rounding is valid only if all other bounds/final constraints pass.
- Float/bool/None money, float/bool exact amounts, float/bool rational weights, negative weights, negative/zero total quantity, all-zero weights for nonzero money reject.
- Exact shares that miss by1 sen, percent99.99/100.01 totals, quantity overclaims/unassigned quantity reject. Do not normalize into new values.
- Unknown/repeated participant claims reject. Participant may occur on different valid items. Duplicate item IDs, adjustment IDs and an item/adjustment namespace collision reject. IDs with spaces, Unicode lookalikes, leading punctuation or length65 reject rather than normalize.
- Exceed each count/money/normalized-rational/quantity bound; reject finite-list versus required-tuple representation and unknown constructor fields predictably.
- Reorder participant registry, item registry, adjustment registry and per-split shares. Results keyed by IDs remain identical, including per-source sen allocation.
- Attempt to mutate accepted inputs/results; frozen public facts must remain unchanged. No ambient state or file/network effects are part of calculation.
- Decimal parser rejects signs, commas, exponents, leading/trailing whitespace, Unicode digits, a bare decimal point, a trailing dot, more than2 fractional digits, overlong strings and values above the bound. No locale guessing or float roundtrip.

Human review/current persisted revision/permission remain future authority invariants; no pure arithmetic case can establish them.
