# Independent Security and Code Review: SettleTable Browser MVP Fixes (PR #8)

**Target PR / Branch**: PR #8 (`feature/browser-e2e-fixes`, head commit `172d56f`)  
**Target Codebase**: `C:\LKY_Project\TabWise`  
**Reviewer Role**: Independent Security & Code Reviewer  
**Audit Status**: Complete  
**Overall Determination**: **GO (APPROVED FOR MERGE)**  
**Target File for Documentation**: `C:\LKY_Project\TabWise\research\phase-3\browser-e2e-fixes-review.md`

---

### Executive Summary

PR #8 addresses and resolves the core defects identified in the browser MVP interface, specifically around receipt-entry monetary contracts, authoritative calculation display mapping, race condition mitigation in UI polling/mutation refresh, and strict MYR input parsing. It also provides comprehensive end-to-end test harnesses in both Python and real Headless Chrome over the Chrome DevTools Protocol (CDP).

The audit confirms:
1. **Receipt-Entry Contract**: `ReplaceReceipt` in `settletable/static/app.js` now derives `subtotal_sen` and `total_sen` from explicit line items and adjustments. The backend `_receipt_issues` check enforces that neither field is `None` nor mismatched, eliminating the previous blocker where receipt reviews failed with `missing_amount`.
2. **Authoritative Calculation Mapping**: `renderFinalizedCalculation` in `app.js` maps participant totals directly from `calculation.consumption` records (`participant_id -> sen`), resolving the regression where an undefined `calc.lines` structure caused all participant totals to silently display as `RM 0.00`. If records are missing, explicit error warnings (`Amount Missing`) are rendered instead of fabricating zero amounts.
3. **Decoupled Polling & Conflict Recovery**: Background polling (`fetchSnapshot(false)`) and forced mutation/error refreshes (`fetchSnapshot(true)`) are cleanly decoupled. State mutation locks (`state.mutationActive`) are cleared prior to forced snapshot fetches, sequence numbering (`state.pollSeq`) prevents out-of-order network poll clobbering, and HTTP 409 stale conflict responses trigger amber notifications and snapshot reloads.
4. **Strict MYR Input Parsing**: `parseSen` in `app.js` replaces permissive `parseFloat` with strict regex and integer sen math (`whole * 100 + frac`), rejecting malformed characters, non-strings, negative amounts, and out-of-bounds values without floating-point drift.
5. **Real Browser E2E Test Suite**: `tools/e2e_browser_test.mjs` executes an 8-stage vertical test across two isolated Headless Chrome instances with independent user-data directories and cookie jars, confirming organizer meal provisioning, human receipt review, invitation redemption, portion claiming, real-time sync, 409 stale conflict recovery, finalization calculation, and page reload persistence.
6. **Financial Invariants**: `settletable/calculation.py` remains untouched. All cryptographic hash domains in `settletable/authority.py` (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-digest-v1`) are strictly preserved. The full regressive Python test suite (113 tests) and real browser CDP test pass with 100% success.

---

### Audit Gate Determinations

| Gate | Audit Area | Status | Key Citations & Findings |
|---|---|---|---|
| **Gate 1** | Receipt-Entry Contract & Human Verification | **PASS** | `settletable/static/app.js:782-800`<br>`settletable/authority.py:797-818, 896-898`<br>Subtotal and total computed accurately from items & adjustments; prevents zero-fabrication; mandatory human review preserved. |
| **Gate 2** | Authoritative Calculation Display | **PASS** | `settletable/static/app.js:678-741`<br>Maps participant amounts directly from `calc.consumption`; renders explicit `Amount Missing` or `Calculation Data Missing` if data absent; grand total tied to `receipt.total_sen` and consumption sum. |
| **Gate 3** | Mutation Refresh & Conflict Recovery | **PASS** | `settletable/static/app.js:14-15, 159-181, 801-808, 949-963`<br>Decoupled `fetchSnapshot(force)`; `state.mutationActive` cleared before forced snapshot fetch; `pollSeq` guards against out-of-order responses; 409 conflict handled cleanly. |
| **Gate 4** | Strict MYR Input Parsing | **PASS** | `settletable/static/app.js:25-45`<br>`tests/test_browser_mvp_e2e.py:13-29, 132-149`<br>Strict string-only regex `/^[0-9]+(?:\.[0-9]{1,2})?$/`; integer math avoids float drift; rejects negative, empty, non-string, or out-of-bounds amounts. |
| **Gate 5** | Real Browser E2E Test Verification | **PASS** | `tools/e2e_browser_test.mjs:1-361`<br>`tests/test_browser_mvp_e2e.py:197-356`<br>Automated CDP test runs two isolated browser profiles; validates end-to-end flow from room creation to reload persistence; 8/8 stages passed. |
| **Gate 6** | Financial Invariants | **PASS** | `settletable/calculation.py` (untouched)<br>`settletable/authority.py:232, 239, 314, 942`<br>Deterministic calculation engine and versioned domain separation intact; 113/113 Python tests pass. |

---

### Detailed Findings & Code Citations

#### Gate 1: Receipt-Entry Contract & Human Verification
- **Apportionment Facts**:
  In `settletable/static/app.js` (lines 782-800), when the organizer adds an item:
  ```javascript
  782: const subtotalSen = currentItems.reduce((acc, it) => acc + (it.line_sen || 0), 0);
  783: const adjTotal = (snap.receipt?.adjustments || []).reduce((acc, a) => acc + (a.amount_sen || 0), 0);
  784: const totalSen = subtotalSen + adjTotal;
  ...
  793: receipt: {
  794:   items: currentItems,
  795:   subtotal_sen: subtotalSen,
  796:   total_sen: totalSen,
  797:   adjustments: snap.receipt?.adjustments || [],
  798:   included_tax_sen: snap.receipt?.included_tax_sen || 0,
  799: }
  ```
  This satisfies the backend requirement in `settletable/authority.py` (lines 797-818). Previously, omitting `subtotal_sen` or `total_sen` triggered `_receipt_issues()` returning `missing_amount`, which blocked `ReviewReceipt` at line 890-891:
  ```python
  890: issues = self._receipt_issues(state)
  891: _require(not issues, issues[0] if issues else 'receipt_issue')
  ```
- **Display Integrity**:
  Lines 504-518 render `receipt.subtotal_sen` and `receipt.total_sen` in the Organizer card only when valid (`receipt?.subtotal_sen !== null && receipt?.subtotal_sen !== undefined`), preventing the display of unverified or phantom numbers.
- **Mandatory Human Verification**:
  Lines 452-482 and 813-841 enforce that `canFinalize` requires `hasItems && reviewConfirmed && issues.length === 0`. The review checkbox must be manually checked to enable the "Approve & Seal Receipt" button (`ReviewReceipt`), which stores `review` matching `receipt_digest`. The backend at `settletable/authority.py:896-898` independently enforces `review_required` if the review is missing or if receipt edits altered the financial revision.

#### Gate 2: Authoritative Calculation Display
- **Consumption Record Mapping**:
  In `settletable/static/app.js` (lines 678-741), `renderFinalizedCalculation()` replaces the erroneous lookups against non-existent `calc.lines`:
  ```javascript
  689: const consumptionMap = new Map();
  690: for (const entry of calc.consumption) {
  691:   if (entry && entry.participant_id !== undefined && entry.sen !== undefined) {
  692:     consumptionMap.set(entry.participant_id, entry.sen);
  693:   }
  694: }
  ```
- **Zero Fabrication Prevention**:
  If calculation records fail to load, lines 680-687 display an explicit error card (`Calculation Data Missing`). Furthermore, if a participant listed in `snap.participants` is absent from `consumptionMap`, lines 702-708 render `<td class="amount" style="color: var(--accent-rose);">Amount Missing</td>` rather than defaulting to `0` or `RM 0.00`.
- **Grand Total Reconciliation**:
  Lines 696-699 tie `grandTotalSen` directly to `snap.receipt?.total_sen`, falling back to `calc.consumption.reduce((sum, c) => sum + (c.sen ?? 0), 0)`.

#### Gate 3: Mutation Snapshot Refresh & Concurrency Conflict Recovery
- **Decoupled Polling**:
  `settletable/static/app.js` lines 159-181 decouple forced snapshot refreshes from scheduled polling:
  ```javascript
  159: async function fetchSnapshot(force = false) {
  160:   if (!state.mealId) return;
  161:   if (!force && state.mutationActive) return;
  162:   const seq = ++state.pollSeq;
  ...
  165:   if (seq >= state.pollSeq && snap?.ok) {
  166:     state.snapshot = snap;
  ...
  179: function pollSnapshot() {
  180:   return fetchSnapshot(false);
  181: }
  ```
- **State Mutation Flag Lifecycle**:
  In all user action handlers (Add Item: lines 786-809; Review: lines 822-840; Claim: lines 901-919; Finalize: lines 927-944), `state.mutationActive = false` is explicitly set before calling `await fetchSnapshot(true)`, as well as in `catch` and `finally`. This ensures `fetchSnapshot(true)` is never blocked by a lingering mutation lock.
- **Out-of-Order Clobber Guard**:
  `const seq = ++state.pollSeq` and `if (seq >= state.pollSeq && snap?.ok)` ensure that delayed responses from slower background polls cannot overwrite fresher state received from immediate user actions.
- **409 Conflict Recovery**:
  In `handleApiError` (lines 949-963), receiving HTTP 409 or conflict error codes triggers an amber alert banner, marks contested cards (`.contested`), and calls `fetchSnapshot(true)` to re-synchronize item revisions from the server.

#### Gate 4: Strict MYR Input Parsing
- **Zero Floating-Point Drift**:
  Lines 25-45 in `settletable/static/app.js`:
  ```javascript
  25: function parseSen(input) {
  26:   if (typeof input !== 'string') throw new Error('Price must be a string');
  27:   let s = input.trim();
  28:   if (s.toUpperCase().startsWith('RM')) s = s.slice(2).trim();
  29:   if (!s || !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(s)) {
  30:     throw new Error(`Invalid price '${input}'. Enter an amount like 12.50 or RM 12.50`);
  31:   }
  32:   const parts = s.split('.');
  33:   const whole = parseInt(parts[0], 10);
  34:   const fracStr = (parts[1] || '').padEnd(2, '0');
  35:   const frac = parseInt(fracStr, 10);
  36:   const totalSen = whole * 100 + frac;
  37:   if (totalSen < 0 || totalSen > 1_000_000_000) {
  38:     throw new Error('Price out of bounds: maximum RM 10,000,000.00');
  39:   }
  40:   return totalSen;
  41: }
  ```
  Calculations perform pure integer arithmetic (`whole * 100 + frac`). Negative amounts, non-numeric strings, multiple decimals, and values exceeding 1,000,000,000 sen (RM 10,000,000.00) throw explicit errors instead of returning `0`.

#### Gate 5: Real Browser E2E Test Verification
- **Isolated Browser Contexts**:
  `tools/e2e_browser_test.mjs` launches two instances of Google Chrome (`--headless=new`) with separate temporary directories (`--user-data-dir`), ensuring Alice (port 9224) and Bob (port 9225) maintain separate session cookies and DOM environments.
- **Test Execution Flow**:
  1. Spawns local WSGI server on port 8089 via `tools/run_demo.py`.
  2. Creates meal `dinner-e2e` in Organizer Alice's browser.
  3. Adds receipt items ("Burger Set" RM 24.00, "Iced Tea" RM 6.00). Verifies DOM total is RM 30.00.
  4. Completes human receipt review via checkbox and submit button.
  5. Issues diner invitation link for Bob.
  6. Bob navigates to unauthenticated invite URL, reviews details, and clicks "Accept & Join Meal", acquiring diner session cookie.
  7. Bob claims 1 Burger Set. Alice verifies real-time sync. Alice tests stale claim collision (`expected_item_revision: 0`), verifying HTTP 409 rejection and conflict banner. Alice claims remaining items.
  8. Alice finalizes. Both browsers assert exact breakdown: Alice RM 18.00, Bob RM 12.00, Grand Total RM 30.00.
  9. Both pages are reloaded; assertions verify persistence.
- **Verification Run**:
  Executed `node tools\e2e_browser_test.mjs`. All 8 stages passed in ~3.2 seconds.

#### Gate 6: Financial Invariants
- `settletable/calculation.py` remains untouched.
- `settletable/authority.py` preserves all versioned cryptographic domains:
  - Line 232: `b'settletable-local-session-v1\0'`
  - Line 239: `b'settletable-invitation-v1\0'`
  - Line 314: `b'settletable-receipt-v1\0'`
  - Line 942: `b'settletable-command-digest-v1\0'`
- The full test suite of 113 Python unit tests ran with 0 failures:
  - `python -m unittest tests/test_browser_mvp_e2e.py`: 4 tests passed in 0.174s.
  - `python -m unittest discover -s tests`: 113 tests passed in 87.2s.

---

### Ancillary Review Notes

1. **`tools/run_demo.py`**:
   The demonstration server script is lightweight, self-contained, and relies exclusively on Python standard library modules (`wsgiref.simple_server`, `pathlib`, `argparse`, `sys`). It correctly configures allowed host headers (`localhost`, `127.0.0.1`) and origin matching.
2. **Defensive Clock Handling in `authority.py` and `transport.py`**:
   `self._clock = clock if clock is not None else time.time` protects against `None` passed in default configurations or CLI tools.
3. **Read-Only Subagent Policy Compliance**:
   This review was conducted in strict read-only mode without modifying files. The full markdown content above is formatted for preservation at `C:\LKY_Project\TabWise\research\phase-3\browser-e2e-fixes-review.md`.

---

### Final Recommendation

**GO (APPROVED FOR MERGE)**

All 6 acceptance gates have passed with verified automated tests. PR #8 is ready to be merged into `main`.
