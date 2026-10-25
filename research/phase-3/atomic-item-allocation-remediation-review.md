# Independent Code Review: Remediations on `feature/atomic-item-allocation`

**Pull Request:** #17  
**Commit:** [`92babe200ca1dd7cd6c73d83e678554f1ce727ad`](https://github.com/KAIYI7/settle-table/commit/92babe200ca1dd7cd6c73d83e678554f1ce727ad)  
**Reviewer Role:** Independent Senior Backend & Security Code Reviewer  
**Risk Tier:** **HIGH** (Financial correctness, atomic claims mutation, concurrency & race serialization, provenance integrity)  
**Overall Finding:** **PASS**  
**Recommendation:** **UNCONDITIONAL PASS / READY FOR AUTONOMOUS MERGE**

---

## Executive Summary

An independent, rigorous re-review of the remediations committed in `92babe2` on branch `feature/atomic-item-allocation` has been completed. The inspection evaluated claim provenance preservation, strict transport fraction/type validation, multi-threaded SQLite concurrency under competitive race conditions, and unit/regression test completeness.

All 192 tests in the repository test suite pass cleanly without failures or regressions (`192 tests in 74.51s, OK`). The remediations completely resolve prior findings, preserve financial and provenance invariants, and satisfy all governance criteria for **HIGH**-risk autonomous merge under `AGENTS.md`.

---

## Detailed Evaluation of Remediation Areas

### 1. Claim Provenance Preservation (`settletable/authority.py:Authority._set_item_allocations`)
- **Evaluation:** **PASS**
- **Analysis:**
  - In `_set_item_allocations`, previous claims for `item_id` are indexed by participant: `previous_claims = {c['participant_id']: c for c in state['claims'] if c['item_id'] == item_id}`.
  - When constructing the new claim entries, each allocation is compared against `previous_claims.get(pid)`:
    ```python
    if prev is not None and prev['quantity'] == qty and prev['financial_revision'] == state['financial_revision']:
        assigned_by = prev.get('assigned_by')
    else:
        assigned_by = actor
    ```
  - **Unchanged Diner Claims:** For diner self-claims created via `SetOwnQuantity`, `prev.get('assigned_by')` is `None`. When the organizer includes this diner with an unchanged quantity and financial revision, `assigned_by` remains `None`. Diner self-claim provenance is preserved.
  - **Unchanged Prior Assignee:** If a claim was previously assigned by another organizer, that assigner ID is preserved.
  - **Modified Quantities:** If the organizer adjusts the diner's quantity, `prev['quantity'] == qty` evaluates to `False`, stamping `assigned_by = actor` (the current organizer).
  - **New Allocations:** Any newly introduced participant lacks a previous claim (`prev is None`) and is stamped with `assigned_by = actor`.
  - **Representation Equivalence:** Because all quantities in `data['allocations']` and `state['claims']` pass through `_rational()` to canonical reduced `[numerator, denominator]` pairs, structural equality `prev['quantity'] == qty` is exact and free from representation skew.

### 2. Strict Fraction & Exact Type Validation (`settletable/transport.py:_parse_quantity`)
- **Evaluation:** **PASS**
- **Analysis:**
  - `_parse_quantity(qty, *, allow_none=False)` implements rigorous type and value constraints:
    - Booleans (`True`, `False`, `[True, 2]`, `[1, False]`) are strictly rejected. The implementation uses exact type checks (`type(num) is not int`, `type(qty) is int`), preventing Python's `isinstance(True, int) == True` trap.
    - Zero and negative values (`0`, `-1`, `[-1, 2]`, `[1, -2]`, `[0, 2]`, `[1, 0]`) are rejected with `HTTP 400 invalid_input`.
    - Floating-point representations (`1.5`, `[1.5, 2]`) are rejected at the transport boundary by `parse_strict_json` (`_reject_float` -> `HTTP 400 invalid_number`) and by `_parse_quantity` (`HTTP 400 invalid_input`).
    - Malformed structures (`[]`, `[1]`, `[1, 2, 3]`, `"1"`, `{}`) fail length or type assertions and reject with `HTTP 400 invalid_input`.
  - **Systematic Command Coverage:** `_parse_quantity` is applied across all four quantity-handling transport routes:
    - `ReplaceReceipt`: strictly validates all receipt item quantities (`allow_none=False`).
    - `SetOwnQuantity`: strictly parses quantity, allowing `None` only for explicit claim removals.
    - `AssignParticipantQuantity`: strictly parses quantity, allowing `None` only for unassignment.
    - `SetItemAllocations`: strictly parses every allocation item quantity (`allow_none=False`).

### 3. Concurrency & Multi-Threaded Race Test (`tests/test_authority.py:test_concurrent_race_set_item_allocations_and_set_own_quantity`)
- **Evaluation:** **PASS**
- **Analysis:**
  - **Real Concurrency:** Spawns two independent OS threads (`t_org` and `t_diner`), each initializing a distinct `Authority` instance with an independent SQLite database connection to `self.path`.
  - **Serialization & OCC:** Simulates a race condition between an organizer's `SetItemAllocations` (claiming 2/2 portions) and a diner's `SetOwnQuantity` (claiming 1/2 portions) starting from item revision 1.
  - **Single Winner / Conflict Loser:** Validates `len(results) == 1` and `len(errors) == 1`. The loser cleanly encounters `AuthorityError('item_revision_conflict')` (HTTP 409).
  - **Quantity Conservation & State Integrity:** Asserts that total claimed portions $\le 2$ (the item capacity) and validates that item revision advances to 2.
  - **Clean Rollback & Leak Protection:** Verifies that the failing transaction aborted cleanly without orphan records or partial claims. When the loser retries at revision 2, it is rejected with `quantity_capacity` (since the winner claimed 2/2 portions), verifying that the database remained in an uncorrupted, consistent state.
  - Connection teardown is guaranteed via `finally: auth.close()` across all threads.

### 4. Provenance & Boundary Test Suites (`tests/test_authority.py` & `tests/test_transport.py`)
- **Evaluation:** **PASS**
- **Analysis:**
  - `test_set_item_allocations_preserves_unchanged_diner_claim_provenance`: Tests the complete lifecycle: (1) Diner self-claims 1 portion (`assigned_by=None`); (2) Organizer adds Carol while retaining Diner at 1 portion -> confirms Diner's `assigned_by` remains `None` while Carol is stamped with Organizer; (3) Organizer modifies Diner's portion to 2 -> confirms Diner's `assigned_by` updates to Organizer.
  - `test_transport_strict_fraction_and_boolean_rejections`: Tests a 21-element matrix of invalid inputs across `SetItemAllocations`, `SetOwnQuantity`, `AssignParticipantQuantity`, and `ReplaceReceipt`, verifying HTTP 400 rejections across all routes.

---

## Findings Matrix

| Focus Area | Criterion | Severity | Status |
| :--- | :--- | :--- | :--- |
| **Claim Provenance** | Unchanged diner self-claims preserve `assigned_by = None` | HIGH | **PASS** |
| **Attribution** | Modified quantities & new allocations stamped with organizer actor | HIGH | **PASS** |
| **Input Sanitization** | Exact rejection of `bool`, floats, $\le 0$, malformed fractions | HIGH | **PASS** |
| **Concurrency / OCC** | Multi-threaded SQLite race serialized with OCC revision conflict | HIGH | **PASS** |
| **Financial Conservation** | Quantity capacity strictly conserved; clean transaction rollback | HIGH | **PASS** |
| **Test Completeness** | 192/192 tests pass locally without defect | HIGH | **PASS** |

---

## Autonomous Merge Recommendation

**VERDICT: UNCONDITIONAL PASS / READY FOR MERGE**

The remediations on branch `feature/atomic-item-allocation` (commit `92babe200ca1dd7cd6c73d83e678554f1ce727ad`) fully satisfy the repository's HIGH-risk review and security policies. The PR is approved for autonomous merge into `main` using `--no-ff`.
