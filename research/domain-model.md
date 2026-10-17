# Dining allocation and settlement recommendation

Status: source-derived recommendation complete; this is a research model, **not an implemented or approved production architecture**. Accessed **2026-10-16**. Facts, inferences/proposals and open questions are separated below. Repository detail and exact revisions: [Spliit](repositories/spliit.md), [SplitPro](repositories/split-pro.md).

## What the references actually prove

| Hypothesis | Evidence and disposition |
|---|---|
| Spliit is a good group/expense/balance reference | **Supported.** Group-local participants, expenses, split weights, reimbursements and derived balances are explicit. Its single payer and expense-level allocation are insufficient for itemized multi-payer dining. |
| SplitPro is necessary for precision | **Rejected as an exclusive claim.** It uses BigInt and broader split types; current Spliit already apportions integer minor units with deterministic largest remainder and conservation tests. SplitPro's UI uses truncated ratios followed by seeded penny assignment; it is not the same algorithm. |
| Combine modules from both unchanged | **Not supported.** Models differ: Spliit persists positive consumption weights and a single payer; SplitPro persists signed net participant amounts and a single payer. Direct composition would duplicate domain truth and create sign/rounding inconsistencies. |
| Proportional receipt charges are already available | **Rejected.** Neither inspected schema has separate item/tax/service/discount entities or proportional charge policy. These require a small explicit dining domain. |
| Greedy settlement always minimizes transaction count | **Not established.** Both produce settlement suggestions; neither inspected algorithm provides an optimality proof. Use deterministic valid suggestions without promising a global optimum. |

Primary source anchors: Spliit [`schema.prisma`](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/prisma/schema.prisma), [`shares.ts`](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/shares.ts), [`balances.ts`](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/balances.ts), [`balances.test.ts`](https://github.com/spliit-app/spliit/blob/5dac4119f0441cb945756f8c92911de6f312a1a3/src/lib/balances.test.ts); SplitPro [`schema.prisma`](https://github.com/oss-apps/split-pro/blob/3583568319807e193fbe57085ea9560a2e872b93/prisma/schema.prisma), [`addStore.ts`](https://github.com/oss-apps/split-pro/blob/3583568319807e193fbe57085ea9560a2e872b93/src/store/addStore.ts), [`BalanceView.sql`](https://github.com/oss-apps/split-pro/blob/3583568319807e193fbe57085ea9560a2e872b93/prisma/views/public/BalanceView.sql), [`simplify.ts`](https://github.com/oss-apps/split-pro/blob/3583568319807e193fbe57085ea9560a2e872b93/src/lib/simplify.ts).

## Proposed domain boundaries

**Proposal:** keep the following independent facts rather than collapsing them into one signed share row. This logical model can map to different approved stacks later.

| Concept | Required responsibility |
|---|---|
| Meal | Stable ID, currency, merchant/date, receipt totals, draft/reviewed/finalized state, revision, group context. Currency is explicit (MYR initially); do not mix currencies in a balance. |
| Participant / Person | A person identity optionally linked to an account or Notion page, plus meal membership/display-name snapshot. Guests can participate without granting editing/Notion credentials. Stable ID, not name, identifies allocations. |
| Receipt / Extraction attempt | Private original image, derived processing image, content hash, raw OCR/text/boxes, engine/version, structured proposal, field provenance and validation issues. OCR output remains proposed until reviewed. |
| Receipt item | Ordered label/raw text, quantity (rational/decimal, not money), printed unit/line amounts, chosen canonical line amount, tax/discount eligibility, extraction references and reviewed status. Preserve observed discrepancies; do not assume quantity × printed unit price must equal line total when unit rounding exists. |
| Item allocation | Item → participant with equal/custom rational weights, quantity shares, percentage or exact money, plus finalized apportioned amount. Allow shared dishes. Track unassigned amounts visibly. No auto-assignment to uploader/payer. |
| Adjustment / charge | Signed fixed amount and kind (SST/tax, service charge, discount, tip, receipt rounding), scope/eligible items/people, allocation basis, optional printed rate and ordering. Printed fixed amounts are authoritative after review. |
| Payment / payer contribution | Meal → participant paid amount, currency, method/reference. Multiple rows/payers. Consumption does not imply payment and payer need not eat. Confirm their sum equals receipt total before closing funding. |
| Settlement | Actual from/to transfer, amount, currency, date, state and idempotency/reference; distinguish suggestion, pending and confirmed. Partial transfers supported. Corrections reverse/amend an event rather than erasing history. |
| Integration mapping / sync event | Internal IDs/revisions → external page IDs, last export hash/status and retry metadata; external synchronization must not define arithmetic. |

**Inference:** a new small shell with these boundaries is easier to reason about than grafting item ownership and multiple payers into either single-payer expense model. Licensed functions may still be adapted after stack selection and attribution review.

## Money and apportionment policy

**Proposal:** use integer minor units end to end (MYR sen) with checked bounds. BigInt/SQL BIGINT is a reasonable default if TypeScript/PostgreSQL is selected; bounded safe integers are also sufficient for ordinary meals if bounds and multiplication are enforced. The key is exact parsing, integer allocation and invariant validation, not the storage type alone. Serialize integer money as decimal strings where JSON cannot represent BigInt. Parse decimal strings exactly; do not route user or OCR amounts through binary float arithmetic. Keep any FX outside the initial MYR meal calculation.

For a positive amount `A` and nonnegative integer/rational weights `wᵢ`:

1. Require at least one positive eligible weight. Exact-amount splits must already sum to `A`; do not silently reinterpret them as ratios.
2. Compute exact quota `A × wᵢ / Σw`; assign integer floors.
3. Give leftover units to largest fractional remainders. Break equal remainders deterministically with a recorded policy using stable allocation IDs plus item/charge ID. Preview, save, export and recalculation must agree.
4. For a negative discount/credit, apportion its absolute amount and negate the results. Use the same declared tie policy; cap scoped discounts when necessary so they do not create unintended negative consumption.
5. Persist policy version and finalized allocations or an auditable snapshot; later engine changes must not silently change settled historical meals.

**Inference:** deterministic largest remainder is more explainable than random penny distribution or rounding every displayed person's total independently. Spliit's current helper demonstrates this conservation principle, but new code should validate legacy/corrupt weights instead of adopting its silent normalization fallback.

Tiny example: RM10.00 shared equally among A/B/C is 1000 sen. Floors are 333/333/333; one residual sen goes to the recorded tie winner, yielding **334/333/333**, exactly 1000. Display RM3.34/RM3.33/RM3.33; do not display three RM3.33 amounts and hide the difference.

## Tax, service, discounts and printed rounding

**Proposal:** default meal-wide adjustments to proportional eligible consumption, with visible policy and override. An item-specific discount follows that item's consumers. A service charge may apply only to designated items; SST may have a different base or already be included. Allocate **each printed fixed adjustment independently**, after identifying its eligibility/base. Preserve item-level and receipt-level discounts separately to avoid double counting.

Do not hard-code a Malaysian tax rate, assume tax includes/excludes service charge, or recompute a printed tax from a guessed base. OCR and review must identify included versus added charges, and preserve any printed rate as supporting information. Where receipt totals conflict, show the discrepancy and require correction/explicit adjustment before finalizing. This is an allocation recommendation, not a tax-compliance determination.

Model explicit printed cash-rounding adjustment separately from the 1-sen residue of allocating a component. If there is no item base (e.g. empty or fully discounted meal), require a human choice of equal/custom recipients rather than divide by zero. Optional alcohol/nonconsumption exclusions need explicit eligibility and review.

## Worked meal with two payers

Illustrative **allocation policy**, not a statement of applicable tax rates: reviewed receipt has item subtotal RM100.00, printed service RM10.00, printed tax/SST RM6.00, receipt discount RM10.00, total RM106.00. All three adjustments use eligible pre-discount item consumption as weights, 20:30:50.

| Participant | Items | Service | Tax/SST | Discount | Owed |
|---|---:|---:|---:|---:|---:|
| A | 20.00 | 2.00 | 1.20 | −2.00 | 21.20 |
| B | 30.00 | 3.00 | 1.80 | −3.00 | 31.80 |
| C | 50.00 | 5.00 | 3.00 | −5.00 | 53.00 |
| Total | **100.00** | **10.00** | **6.00** | **−10.00** | **106.00** |

A pays restaurant RM70.00; B pays RM36.00; C pays zero. Net balance `paid − owed` is A **+48.80**, B **+4.20**, C **−53.00**; sum zero. Suggested transfers: C→A RM48.80 and C→B RM4.20. If C first pays A RM20.00, remaining balances are A +28.80, B +4.20, C −33.00. Consumption/receipt total do not change.

For confirmed settlements, `net = restaurant payments − consumption + settlements sent − settlements received`. A positive net is money to receive; a negative net is money to send. Maintain this convention everywhere, especially Notion exports. Do not treat settlement as another dining consumption expense in spending reports.

## Required invariants and validation gates

**Proposal / future acceptance criteria:**

- Each finalized item's participant allocations sum exactly to its canonical line amount; each charge's allocations sum exactly to its signed amount; no unresolved item remains hidden.
- Canonical subtotal equals the sum of chosen item line amounts, or an explicit reviewed subtotal adjustment explains the difference. Included taxes/discounts must not be added twice.
- Sum of participant consumption equals reviewed final receipt total, including explicit printed rounding; all components and final allocations are integer minor units.
- Restaurant payer contributions equal total before marking funded; participants, payers, item owners and currency must be valid for the meal.
- Sum of net balances is zero when funding reconciles. Confirmed settlements preserve zero sum and reduce the relevant debts; partial/overpayments must be represented explicitly rather than discarded.
- Stable input IDs/revisions yield identical previews, stored calculations and exports regardless of DB row order. Repeated API submissions or Notion retries do not duplicate payments/settlements.
- Server revalidates/recomputes authoritative arithmetic; client validation and LLM schema-valid JSON are insufficient. Reject duplicate participant entries, invalid amount strings, overflow, mismatched revision and unauthorized edits.
- Editing a finalized/settled meal creates an audit-visible revision and recalculates debts; do not present old settlements as automatically void. Sync is revision-aware.

**Fact:** Spliit's randomized conservation/full-settlement tests and SplitPro's real BigInt/database rollback tests are useful test patterns. **Open:** these acceptance criteria have not been implemented or run here.

## Settlement simplification and unresolved decisions

**Proposal:** compute net balances from source facts; offer deterministic greedy matching between debtors and creditors as a small-meal convenience. Keep suggestions separate from actual transfers. Allow users to preserve original payer relationships where socially important; cross-meal/group debt simplification should be opt-in. Do not settle across currencies automatically or claim a globally minimal payment count.

**Open decisions for next phase:** equal versus proportional defaults for exceptional fees/tips; inclusive-tax representation; coupon ownership and discount eligibility; gifting/sponsoring another diner; partial item quantities; whether guest collaboration is live or one-editor; finalized edit rights; original image retention; refunds/negative meals; cross-meal balances; payment confirmation/dispute policy; exact tie-breaking policy and maximum bounds. None prevents completing this research, but each affects implementation acceptance criteria.

### Coordinating precision qualification

Spliit's integer minor-unit storage/conserved allocation should not be described as arbitrary precision: `shares.ts` multiplies JS Numbers. Large operands require safe-integer bounds. The recommended new allocator must check intermediate bounds or use BigInt/rational operations; this qualification does not change its value as a pattern for ordinary bounded meals.
