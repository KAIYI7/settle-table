# Financial calculation interface

`settletable.calculation` is a pure Python standard-library module. It calculates **supplied facts**, not authority to finalize: it cannot prove human review, identity, access or current persisted revisions. No `reviewed=True` switch substitutes for that future authoritative operation. It performs no file/network/database operation and has no payer/settlement behavior.

## Public seams

- `calculate(Meal) -> Calculation`, or `CalculationError` with stable `code` and fact `path`.
- `parse_money(str) -> int`: unsigned ASCII decimal MYR text to sen, exactly; e.g. `"12.30" -> 1230`. No signs, separators, exponent, whitespace or more than two fractional digits.

Frozen slotted dataclasses carry the input/output vocabulary. Constructors reject unknown fields; `calculate` validates field values and rejects mutable collections. Constructing a dataclass alone is not validation. Untrusted JSON/HTTP adapters must enforce their own body/schema limits before creating these Python facts.

```python
from settletable.calculation import Meal, Item, Split, Share, calculate

meal = Meal(
    participants=("A", "B"),
    items=(Item("dish", 1001, Split("quantity", (
        Share("A", 1), Share("B", 2))), quantity=3),),
    subtotal_sen=1001,
    total_sen=1001,
)
result = calculate(meal)  # consumption: A334, B667; line total is not multiplied again
```

`Meal` fields are `participants`, `items`, `subtotal_sen`, `total_sen`, optional `adjustments=()` and `included_tax_sen=0`. `Item` carries `id`, `line_sen`, `split`, `quantity=1`. `Split` carries `mode` and a tuple of `Share(participant_id, value)`. Modes are `equal` (explicit weight1), `weights`, `percent` (sum100), `exact` (integer sen summing to source magnitude), and item-only `quantity` (positive claims summing exactly to item quantity). A zero-value line still needs a valid nonempty assignment. A zero-value weights split may have an all-zero base; a nonzero source may not.

`Adjustment(id, kind, amount_sen, eligible_item_ids=None, split=None)` has **exactly one** nonempty unique item scope or explicit split. `tax`/`service` are nonnegative; `discount` nonpositive; printed `rounding` signed. Scoped components use the original already-rounded item allocations, unchanged by other adjustments. Zero-base participants receive zero. A scoped discount cannot exceed its eligible item base; an explicit discount cannot exceed canonical subtotal. Final negative consumption rejects, including overlapping discounts. Included tax is bounded informational data and is never added again. Refunds/credits/sponsorship, payment instruments, compounding and rate reconstruction are unsupported.

`Calculation` contains immutable tuples `items`, `adjustments` and `consumption`. Each source is `SourceAllocation(source_id, shares)`; each share/consumption row is `PersonAmount(participant_id, sen)`. Source and participant rows sort by exact stable ID. Item/explicit-split output rows contain their listed participants; scoped-adjustment rows include every registered participant, including zeros. Final consumption includes everyone. No display labels or arbitrary JSON live in the financial facts.

## Determinism and constraints

Accepted technical contract: [MVP C1–C4](../research/phase-2/mvp-specification.md). IDs are case-sensitive ASCII `[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}`. Item and adjustment IDs share one unique namespace. All collections are exact finite tuples: ≤100 participants, ≤500 items, ≤100 adjustments. Monetary magnitudes and final totals/subtotals/consumption are ≤1,000,000,000 sen; amounts are exact Python `int`, never `bool`. Rationals are exact `int` or `Fraction`, normalized absolute numerator ≤1,000,000,000 and denominator ≤1,000,000. Item quantity is positive and ≤1,000,000. Decimal text is ≤16 characters. These are abuse bounds, not ordinary bill estimates.

Largest remainder uses exact quotas. Ties sort by the ascending SHA-256 bytes of compact ASCII JSON `["tabwise-apportion-v1", source_id, participant_id]`, then participant ID. Signed negative adjustments apportion magnitude first and negate. Input order cannot select a residual recipient. Conservation/determinism do not imply individual monotonicity: the documented 25→26-sen paradox remains valid.

Calculation rejects subtotal mismatch, receipt-total mismatch, malformed/foreign/duplicate identities, incomplete splits, invalid scope/signs, bounds and negative final consumption. It never silently adds a balancing line, changes percentages, rounds each person to 5 sen or clamps a negative liability. Labels and reviewer rationale for visible receipt adjustments belong to the later authoritative layer.

Run `python -m unittest discover -s tests -v` from the project root. Current runtime evidence and limitations: [implementation log](../research/phase-3/implementation-log.md). No package/deployment/framework scaffold or external dependency is required for this slice.
