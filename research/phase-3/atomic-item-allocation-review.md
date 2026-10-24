# Independent Code Review: Phase 1 Bounded Backend Atomic Item Allocation (`SetItemAllocations`)

**Target Branch:** `feature/atomic-item-allocation`  
**Commit:** [`0fd0b049dc075af41ca2e1bd121ceefcecee69a8`](https://github.com/KAIYI7/settle-table/commit/0fd0b049dc075af41ca2e1bd121ceefcecee69a8)  
**Reviewer Role:** Senior Backend & Security Code Reviewer (Independent Subagent)  
**Risk Tier:** **HIGH** (Financial correctness, concurrency, atomic claims mutation, access control)  
**Overall Recommendation:** **UNCONDITIONAL PASS / READY FOR MERGE**

---

## Executive Summary

An independent, rigorous review was conducted on the Phase 1 backend implementation of atomic item allocation in SettleTable (`settletable/authority.py` and `settletable/transport.py`), accompanied by test suites (`tests/test_authority.py` and `tests/test_transport.py`) and design specification (`.scratch/atomic-item-allocation/SPEC.md`).

The implementation replaces sequential, prone-to-deadlock item portion modifications and the narrow `SplitItemEqually` design with **`SetItemAllocations`**, an atomic, rational-safe, organizer-authorized command narrowly scoped to an individual `item_id`.

All 189 test methods across the repository pass without defect, including all unit, transport, and security regression suites.

---

## Detailed Evaluation Against HIGH-Risk Governance Criteria

### 1. Architectural Integrity (`SplitItemEqually` vs `SetItemAllocations`)
- **Status:** **PASS**
- **Analysis:**
  - `SplitItemEqually` was inherently inflexible, capable only of uniform $1/N$ partitions and incapable of custom fractions, mixed integer portions, partial allocations, or item claim clearing.
  - Under sequential claims modification, swapping claim ownership on fully allocated items created intermediate capacity deadlocks (`quantity_capacity`), requiring intermediate state exposure or multiple round-trips.
  - `SetItemAllocations` provides a strictly superior, general command that evaluates capacity $\sum \text{quantity} \le \text{item.quantity}$ atomically across the entire new allocation set.
  - **Concurrency Scoping:** The command is narrowly scoped to `item_id`. It only validates and increments `state['item_revisions'][item_id]` and does not require or mutate the revisions of other items. In optimistic concurrency control, concurrent modifications to different receipt items by diners and organizers do not trigger false conflict errors.

### 2. Financial Correctness & Exact Rational Arithmetic
- **Status:** **PASS**
- **Analysis:**
  - Strict enforcement of exact rational arithmetic (`Fraction`) across the entire pipeline.
  - Floating-point representations are strictly forbidden: rejected at the HTTP transport boundary and at the authority validation boundary via `_rational()` (`type(value) in (int, Fraction)`).
  - Rational bounds are strictly clamped: `0 < numerator <= 1_000_000_000`, `denominator <= 1_000_000`, and quantity $\le 1_000_000$.
  - End-to-end integration with `settletable.calculation` preserves exact Hamilton-Hare largest-remainder sen apportionment and zero-drift cent conservation. Verified in `test_set_item_allocations_equal_split_and_largest_remainder_sen`: dividing a 1000 sen item equally across 3 participants yields exactly 333, 333, and 334 sen, summing deterministically to 1000 sen.

### 3. Authorization & Active Membership
- **Status:** **PASS**
- **Analysis:**
  - **Organizer Enforcement:** In `settletable/authority.py:Authority._permission`, `data['kind'] != 'SetOwnQuantity'` strictly requires `bool(organizer)`. Any non-organizer attempting `SetItemAllocations` is rejected with `AuthorityError('forbidden')` (HTTP 403 `forbidden`).
  - **Active Membership Verification:** Each target in `allocations` is queried against SQLite `SELECT active FROM participants WHERE meal_id=? AND id=?`. Non-existent participants or inactive/revoked participants (`active != 1`) trigger `AuthorityError('forbidden')` (HTTP 403 `forbidden`).
  - **Duplicate Prevention:** Target IDs are verified for uniqueness (`len(part_ids) == len(set(part_ids))`). Duplicate participant IDs within a single allocation payload are rejected with `AuthorityError('invalid_input')` (HTTP 400 `invalid_input`).

### 4. Revision Conflict & Idempotency
- **Status:** **PASS**
- **Analysis:**
  - **Item Revision Validation:** `data['expected_item_revision'] == state['item_revisions'][item_id]` is strictly asserted. Stale submissions reject with `item_revision_conflict` (HTTP 409).
  - **Financial Revision Validation:** `data['expected_financial_revision'] == state['financial_revision']` is asserted in `apply()`. Edits based on superseded receipt revisions reject with `financial_revision_conflict` (HTTP 409).
  - **Replay Protection & Idempotency:** Duplicate submissions with matching `(meal_id, actor, command_id)` check `(body, digest)` match and return the cached `AcceptedResult` without re-executing, modifying claims, or incrementing revisions. Reusing a `command_id` with altered parameters correctly raises `command_conflict`.

### 5. Transaction Atomicity & Rollback
- **Status:** **PASS**
- **Analysis:**
  - All operations occur within `BEGIN IMMEDIATE` ... `COMMIT` transaction boundaries in SQLite with WAL mode.
  - Existing claims for `item_id` are purged and replaced in memory before the serialized state update.
  - Failure injection testing (`test_set_item_allocations_rollback_on_failure`) proves that failures occurring prior to or during commit cleanly trigger `self._rollback()`. The database remains intact with zero phantom claims, preserving pre-existing diner claims and revisions.

### 6. Adversarial Boundaries & DoS Protections
- **Status:** **PASS**
- **Analysis:**
  - Allocation list size is capped at 500 (`len(command.allocations) <= 500`), preventing payload explosion and quadratic memory degradation.
  - Zero, negative integers, negative fractions, zero denominators, and quantities exceeding item capacity are rejected.
  - Submitting `allocations=[]` cleanly and deterministically unclaims the item.
  - Commands submitted against finalized meals (`state['calculation'] is not None`) reject with `AuthorityError('finalized')` (HTTP 409).

### 7. Attribution & Explicit Overwrite
- **Status:** **PASS**
- **Analysis:**
  - All newly created claims carry `assigned_by = actor` and `financial_revision = state['financial_revision']`.
  - Diner-facing and organizer-facing snapshots accurately reflect `assigned_by`, allowing the frontend to present clear provenance and overwrite indicators.

---

## Findings Summary Table

| Category | Finding | Severity | Recommendation |
| :--- | :--- | :--- | :--- |
| **Command Design** | `SetItemAllocations` provides a deadlock-free, item-scoped replacement for equal/unequal portioning | **PASS** | Accept as target command pattern |
| **Arithmetic** | Exact `Fraction` with strict bounds; zero float tolerance; largest remainder sen preserved | **PASS** | Accept |
| **Security & Auth** | Organizer-only check, active participant lookup, duplicate target rejection | **PASS** | Accept |
| **Concurrency** | OCC with item-level revision scoping; full replay idempotency | **PASS** | Accept |
| **ACID / Durability** | `BEGIN IMMEDIATE` atomicity; verified clean rollback on failure injection | **PASS** | Accept |
| **Boundaries** | Max 500 allocations, rational bounds, empty clearing supported, finalization lock | **PASS** | Accept |
| **Attribution** | `assigned_by` and `financial_revision` correctly stamped | **PASS** | Accept |

---

## Non-Blocking Advisory for Phase 2 Frontend Integration
- As recorded in `.scratch/atomic-item-allocation/SPEC.md`, Phase 2 frontend integration should implement the Concept C specifications:
  1. Collapsed diner pills with name, avatar/role icon, and portion count (`👑 Alice · 1`).
  2. One-tap assignment chips (`+ Name`) for unassigned diners.
  3. Responsive drawer/bottom-sheet for custom rational fractions with $\ge 44\text{px}$ touch targets.
  4. Explicit warning dialog disclosing affected diner claims prior to batch overwrites.
