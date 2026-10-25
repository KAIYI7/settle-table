# Specification: Phase 1 Bounded Backend Atomic Item Allocation (`SetItemAllocations`)

## 1. Executive Summary & Architectural Challenge

### 1.1 Context
In the organizer allocation prototype evaluation for SettleTable, Concept C (Unified Expandable Hybrid) was approved by the Product Owner as the target organizer allocation architecture.
Before enabling Concept C in the production browser frontend, Phase 1 requires implementing and hardening the backend atomic item-allocation command.

### 1.2 Pre-Implementation Challenge: `SplitItemEqually` vs `SetItemAllocations`
The preliminary exploration suggested a specialized command `SplitItemEqually`. However, an independent architectural evaluation reveals severe structural limitations with `SplitItemEqually`:

1. **Inflexibility (Only N-way Equal Splits)**:
   `SplitItemEqually` only supports distributing an item's entire quantity equally across $N$ diners ($1/N$ each). It cannot represent:
   - Unequal portions (e.g. Alice takes 1 whole portion; Bob and Carol split the 2nd portion $1/2$ each).
   - Partial allocations (e.g. allocating only 1 portion out of 3, leaving 2 unassigned).
   - Explicit zeroing/clearing of an item's claims.
2. **Intermediate Capacity Deadlock**:
   Under the previous sequential `AssignParticipantQuantity` model, changing allocations on a fully claimed item (e.g. transferring Alice's 1 portion to Bob) required multiple independent network requests. If Bob's assignment was processed before Alice's removal, the server rejected it with `quantity_capacity` because the item temporarily exceeded capacity. If Alice's removal succeeded but Bob's assignment failed due to network disruption, the item was left partially claimed.
3. **Command Surface Bloat**:
   Adding `SplitItemEqually` would still require a second atomic command for custom fractions or multi-person editing in the expanded drawer.

### 1.3 Selected Architecture: `SetItemAllocations`
We adopt **`SetItemAllocations`**, a narrowly scoped atomic item-allocation replacement command:
- **Scope**: Scoped to exactly one `item_id`. It does not lock or conflict with claims on other items, preserving item-level concurrency across diners and organizers.
- **Atomicity**: Replaces all existing claims on `item_id` with the provided allocation list within a single SQLite transaction.
- **Generality**: Naturally handles:
  - Equal splits: client computes rational fraction $\frac{\text{item.quantity}}{N}$ and submits for all selected diners.
  - Custom fractions: arbitrary rational fractions (e.g. $[1, 2]$, $[1, 3]$).
  - Whole portions: mixed integer and fractional allocations.
  - Full reset: submitting `allocations = []` clears all claims on `item_id`.
- **Zero Deadlock**: Evaluates total capacity $\sum \text{quantity} \le \text{item.quantity}$ atomically in one check against the entire new allocation set.

---

## 2. Command Contract & Wire Schema

### 2.1 Python Dataclasses (`settletable.authority`)
```python
@dataclass(frozen=True, slots=True)
class AllocationSpec:
    participant_id: str
    quantity: int | Fraction


@dataclass(frozen=True, slots=True)
class SetItemAllocations:
    command_id: str
    item_id: str
    allocations: tuple[AllocationSpec, ...]
    expected_item_revision: int
    expected_financial_revision: int
```

### 2.2 Wire JSON Protocol (`POST /api/meals/{meal_id}/apply`)
```json
{
  "command_id": "c_alloc_7f3b89",
  "kind": "SetItemAllocations",
  "item_id": "item_truffle_fries",
  "allocations": [
    {"participant_id": "part_alice", "quantity": 1},
    {"participant_id": "part_bob", "quantity": [1, 2]},
    {"participant_id": "part_carol", "quantity": [1, 2]}
  ],
  "expected_item_revision": 2,
  "expected_financial_revision": 1
}
```

- `quantity`: Encoded as a positive integer (e.g. `1`) or an exact two-element rational pair `[numerator, denominator]` (e.g. `[1, 3]`). Floating-point numbers are strictly rejected with HTTP 400 `invalid_input`.
- `allocations`: Tuple/list of `AllocationSpec` objects or dicts. Empty list `[]` is valid and removes all claims from `item_id`.

---

## 3. Invariants & Domain Semantics

1. **Authorization**:
   - Strictly organizer-only. Verified via `_permission`: if caller is not the meal organizer, rejected with `AuthorityError('forbidden')` (HTTP 403).
2. **Active Participant Validation**:
   - Every `participant_id` in `allocations` is queried against SQLite `participants` table (`meal_id=? AND id=?`).
   - If any participant is non-existent or inactive (`active != 1`), command is rejected with `AuthorityError('forbidden')` (HTTP 403).
3. **Duplicate Participant Prevention**:
   - Duplicate `participant_id`s within `allocations` are strictly rejected with `AuthorityError('invalid_input')` (HTTP 400).
4. **Strict Rational Positivity & Exact Integer Types**:
   - Each allocation quantity must be a strict integer or `Fraction` $> 0$ with `numerator <= 1_000_000_000` and `denominator <= 1_000_000`.
   - Booleans (e.g. `true`, `false`, `[true, 2]`, `[1, false]`), floating-point values, zero, negative quantities, or non-rational types are strictly rejected with HTTP 400 (`invalid_input` or `invalid_number`).
5. **Capacity Verification**:
   - Sum of all allocated quantities $\sum_{a} \text{quantity}_a$ must be $\le \text{item.quantity}$.
   - If sum exceeds item capacity, rejected with `AuthorityError('quantity_capacity')` (HTTP 400).
6. **Revision & Conflict Handling**:
   - Target `item_id` must exist in `state['item_revisions']`; unknown items reject with `AuthorityError('unknown_item')` (HTTP 404).
   - `expected_item_revision` must strictly match `state['item_revisions'][item_id]`; stale edits reject with `AuthorityError('item_revision_conflict')` (HTTP 409).
   - `expected_financial_revision` must strictly match `state['financial_revision']`; stale edits reject with `AuthorityError('financial_revision_conflict')` (HTTP 409).
7. **Finalization Protection**:
   - If the meal has already been finalized (`state['calculation'] is not None`), rejected with `AuthorityError('finalized')` (HTTP 409).
8. **Claim Attribution & Provenance Preservation**:
   - Unchanged claims (matching participant, quantity, and current financial revision) preserve their original provenance (`assigned_by = prev.assigned_by`, e.g. `None` for diner-authored claims).
   - Newly allocated claims or claims with modified quantities are attributed to the current organizer (`assigned_by = actor`).
   - Claims are stamped with `financial_revision = state['financial_revision']`.
     - `quantity`: `spec.quantity`
     - `financial_revision`: `state['financial_revision']`
     - `assigned_by`: `actor` (organizer participant ID)
9. **Revision Advancements**:
   - `state['item_revisions'][item_id] += 1`
   - `state['revision'] += 1`
   - `state['financial_revision']` remains unchanged (receipt amounts did not change).
10. **Atomicity & Transaction Rollback**:
    - All database updates and state modifications occur inside `BEGIN IMMEDIATE` ... `COMMIT`.
    - Any failure (domain error or SQLite failure) triggers `self._rollback()`, ensuring zero partial claims or corrupted states.
11. **Idempotency & Replay Protection**:
    - Duplicate command submissions with the same `(command_id, actor, meal_id)` return the cached `AcceptedResult` without re-executing or incrementing revisions.
12. **Result Wire Contract**:
    - Returns `AcceptedResult` where `changed_claims` contains the updated list of active claims for `item_id`.

---

## 4. Phase 2 Future Frontend Requirements (Recorded for UI Implementation)

The following UI requirements identified during the Concept C prototype review are recorded for the subsequent frontend phase:
1. **Collapsed Diner Pills Redesign**:
   - Redesign selected diner pills with clear hierarchy: avatar/icon (e.g. `👑` or `🍽️`), participant name, and quantity badge.
   - Example format: `👑 Alice · 1` and `🍽️ Bob · 1`.
   - Remove cramped embedded `−` / `+` micro-buttons from collapsed cards.
2. **Direct One-Tap Assignment**:
   - Unassigned diners appear as clickable affordances (`+ Name`) for immediate 1-click portion assignment.
3. **Dedicated Editing Affordance**:
   - Detailed adjustments (multiple portions, custom fractions, removing diners) are managed via the expanded drawer (desktop) or mobile bottom sheet (mobile).
4. **Touch Ergonomics & Responsiveness**:
   - Minimum 44px touch targets on mobile viewports.
   - Fix horizontal overflow in mobile bottom sheet's per-diner stepper controls at 375px.
5. **Explicit Overwrite Disclosure**:
   - When an organizer uses equal split or replaces allocations that affect existing diner claims, the UI must explicitly disclose affected assignments before confirmation.
