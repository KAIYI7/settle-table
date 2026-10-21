# Independent Security and Code Review: PR #12 (Phase 3 Consolidation)

**Repository:** `C:\LKY_Project\TabWise`  
**Branch:** `feature/phase-3-consolidation`  
**Head Commit:** `de890fadebc8c3fb7f5eb0a1521e947b0f3a3be5`  
**Reviewer:** Independent Security and Code Reviewer Subagent  
**Final Determination:** **GO (Unconditional Pass)**  
**Target Audit File:** `C:\LKY_Project\TabWise\research\phase-3\consolidation-review.md`

---

## Executive Summary

PR #12 consolidates and hardens the Phase 3 capabilities of SettleTable across both the **Local OCR Receipt Pipeline** and the **Bounded Optional Notion Reporting Pipeline**.

The changes in head commit `de890fa` resolve all prior architectural issues:
1. **OCR Staging Boundary & Human Invariant**: The browser now stages candidate proposals in memory (`state.ocrCandidate`) outside SQLite authority state; `ReplaceReceipt` is never called automatically upon upload; and mandatory physical receipt review (`ReviewReceipt`) remains strictly enforced before finalization.
2. **Notion Asynchronous Delivery & Worker Starvation Defense**: `POST /api/meals/{meal_id}/export/notion` runs asynchronously in a background daemon thread by default, returning HTTP `202 Accepted` immediately and preventing WSGI worker starvation for concurrent live diners. Status is pollable via `GET /api/meals/{meal_id}/export/notion`.
3. **Pre-Creation Title Reconciliation & Realistic Delivery Semantics**: The exporter queries parent block children prior to creating a page. If a page with the deterministic title `🍽️ SettleTable: {merchant} ({meal_id})` already exists, it adopts that page and avoids creating duplicate pages on lost responses. Semantics are explicitly documented as *at-least-once with pre-flight reconciliation*.
4. **Notion Free Block Budget Enforcement**: Compact mode strictly bounds total block output to `MAX_COMPACT_BLOCKS = 40` for any meal size (including 25+ diners and 60+ items) using intelligent rollup rows, preserving multi-member Notion Free workspace lifetime block budgets. Full mode (`mode='full'`) remains available for unconstrained breakdowns.
5. **OCR Operational Validation & Demo Mock**: `RapidOcrEngine` gracefully supports both `rapidocr` and `rapidocr_onnxruntime`. `tools/run_demo.py` supports `--mock-ocr` for instant out-of-the-box local evaluation with zero native ML dependencies.
6. **Financial Invariant Integrity**: `settletable/calculation.py` remains 100% untouched. All versioned hash domain separations remain intact. All **154 Python unit tests** and **9 Chrome CDP real browser end-to-end test stages** pass with zero errors.

---

## Audit Against the 5 Consolidation Acceptance Gates

### Gate 1: OCR Review Boundary & Staging — PASS
* **Browser Staging Outside Authoritative SQLite State**: In `settletable/static/app.js` (lines 977–980), extracted candidates are assigned to in-memory state (`state.ocrCandidate = candidate`) and rendered via `updateMealUI()`. No network mutation request is dispatched upon image extraction.
* **Elimination of Automatic `ReplaceReceipt`**: In prior iterations, uploading an image directly invoked `apiCall('/api/meals/${state.mealId}/apply', 'POST', { kind: 'ReplaceReceipt', ... })`. In commit `de890fa`, this call was completely removed from the file upload callback.
* **Route Badges, Confidence Scores, and Verification Notes**: Rendered in `settletable/static/app.js` (lines 561–579):
  - Route badge: `state.ocrCandidate.route === 'manual_correction' ? '⚠️ Needs Correction' : '✓ Ready for Review'`
  - Mean confidence: `Confidence: (state.ocrCandidate.mean_confidence * 100).toFixed(1)%`
  - Verification note: `Verification Note: ${escapeHtml(state.ocrCandidate.issues.join('; '))}`
* **Explicit Accept & Discard Actions**:
  - `Accept & Apply to Receipt` (`#ocr-accept-btn`, lines 1005–1035): Submits `POST /api/meals/${mealId}/apply` with `kind: 'ReplaceReceipt'`, clears `state.ocrCandidate = null`, reloads snapshot, and notifies the organizer that mandatory physical receipt review is still required before finalization.
  - `Discard` (`#ocr-discard-btn`, lines 1037–1043): Clears `state.ocrCandidate = null` and updates the UI locally without any network or database mutation.
* **Mandatory Physical Receipt Review Strictly Preserved**: In `settletable/static/app.js` lines 462 and 480, `reviewConfirmed = Boolean(snap.review)` is required for `canFinalize`. Finalization remains blocked with warning `⚠️ Receipt must be verified before finalization.` until the physical checkbox and `ReviewReceipt` command are submitted.

### Gate 2: Notion Asynchronous Delivery & Duplicate Page Prevention — PASS
* **Asynchronous Background Execution (HTTP 202 Accepted)**: In `settletable/transport.py` lines 751–783, `POST /api/meals/{meal_id}/export/notion` spawns a background daemon thread `threading.Thread(target=_bg_export, daemon=True)` and returns HTTP `202 Accepted` immediately with status `in_progress`. Live diners' claiming and viewing operations remain unhindered by Notion REST latencies or 429 backoff sleeps.
* **Synchronous Override**: The query parameter `?sync=1` or header `X-SettleTable-Sync-Export: 1` preserves synchronous execution for deterministic automated testing and headless scripts (lines 704–750).
* **Status Polling**: `GET /api/meals/{meal_id}/export/notion` (lines 645–655) permits polling the export state (`not_started`, `in_progress`, `completed`).
* **Pre-Creation Title Reconciliation**: In `settletable/notion/exporter.py` lines 674–701, when exporting under a page parent (`parent_type == "page_id"`), `client.query_block_children(config.token, clean_parent_id)` is queried before `create_page`. If a child page with title `🍽️ SettleTable: {merchant} ({meal_id})` already exists, its `page_id` is adopted and returned with `status: 'already_exported'`, creating 0 duplicate blocks or pages.
* **Documented Delivery Semantics**: Docstring in `settletable/notion/exporter.py` lines 662–663 and `.scratch/notion-reporting/SPEC.md` lines 12–14 explicitly state:
  > *"Delivery Semantics: At-least-once with pre-creation title reconciliation. Does not claim exactly-once delivery across non-transactional REST APIs."*

### Gate 3: Notion Free Block Budget Enforcement — PASS
* **Strict Block Budget Enforcement**: Constant `MAX_COMPACT_BLOCKS = 40` defined in `settletable/notion/exporter.py` line 25.
* **Participant Rollup Boundary**: Lines 198–204 cap individual diner rows at 20 (19 individual + 1 rollup row for "Other diners (N participants)").
* **Dynamic Item Budget Calculation**: Lines 296–306 calculate `used_blocks = 5 + 1 + len(apportionment_rows) + 1 + 1`. The remaining item budget is `remaining_item_budget = max(1, MAX_COMPACT_BLOCKS - used_blocks)`. Items exceeding this budget are rolled up into an "Other receipt items (N items)" row.
* **Mathematical Invariant**: Because `len(apportionment_rows) <= 21`, `used_blocks <= 29`. Thus `remaining_item_budget >= 11`. Total blocks are guaranteed to never exceed 40.
* **Runtime Assertion**: Line 395 enforces `assert count_notion_blocks(blocks) <= MAX_COMPACT_BLOCKS`. Tested with 25 diners and 60 items in `test_large_meal_compact_blocks_bounded_to_40`.
* **Full Mode (`mode='full'`)**: `format_full_meal_blocks` (lines 399–520) outputs all participants and receipt items without rollup when unconstrained exports are requested.
* **Block Counting Accuracy**: `count_notion_blocks` (lines 28–37) accurately counts both top-level blocks and nested `table_row` children.

### Gate 4: OCR Operational Validation & Local Demo Mock — PASS
* **Dual RapidOCR Packaging Compatibility**: `settletable/ocr/engine.py` lines 165–175 catches `ImportError` from `rapidocr` and imports `rapidocr_onnxruntime`.
* **Zero-Dependency Demo Mock**: `tools/run_demo.py` lines 21 and 36–65 introduces `--mock-ocr` (and `SETTLETABLE_MOCK_OCR=1`), allowing immediate local demonstration using preloaded tokens or Malaysian receipt fixtures without requiring ONNX or ML wheels.
* **Zero Persistence & Air-Gap Compliance**: Image binary data exists solely in memory (`raw_image_body`); no image bytes or files are written to disk or SQLite. `test_airgap_zero_outbound_network_sockets` and `test_air_gap_zero_outbound_network_sockets` verify zero socket calls during mock OCR and Notion test executions.

### Gate 5: Financial Invariants & Invariant Integrity — PASS
* **Calculation Engine Untouched**: `git diff main feature/phase-3-consolidation -- settletable/calculation.py` is empty (0 lines changed).
* **Hash Domains Intact**: Versioned domain separation prefixes (`b'settletable-local-session-v1\0'`, `b'settletable-invitation-v1\0'`, `b'settletable-receipt-v1\0'`, `b'settletable-command-digest-v1\0'`) are unchanged.
* **Test Verification**:
  - `python -m unittest discover -s tests -v`: **154 tests passed in 76.6s (OK)**.
  - `node tools/e2e_browser_test.mjs`: **All 9 real browser Chrome CDP test stages passed**.

---

## Detailed Line-by-Line Code Review

### 1. `settletable/static/app.js`
* **Lines 561–625 (`renderOrganizerSection`)**:
  - Successfully introduces staged candidate UI card (`#ocr-candidate-card`).
  - All dynamic fields (`it.label`, `adj.label`, `state.ocrCandidate.issues`, `state.ocrCandidate.merchant`) are properly passed through `escapeHtml(...)`.
  - Numeric values (`confidence`, `it.quantity`, `formatSen(...)`) are strictly typed or formatted, preventing DOM XSS injection.
  - If draft receipt already contains items, an amber warning displays: `"⚠️ Applying candidate will replace the N existing items on the draft receipt."`
* **Lines 975–985 (`bindEvents` OCR upload listener)**:
  - Discarded previous premature `ReplaceReceipt` dispatch. Replaced with `state.ocrCandidate = candidate; updateMealUI();`.
* **Lines 1005–1043 (`ocrAcceptBtn` and `ocrDiscardBtn`)**:
  - Accept button submits `ReplaceReceipt` over `/api/meals/${mealId}/apply`, resets `state.ocrCandidate = null`, refreshes snapshot, and prompts for human physical verification.
  - Discard button clears candidate state in memory and resets the view without invoking backend APIs.
* **Lines 1218–1270 (Notion Export Async Polling)**:
  - If `POST /api/meals/${mealId}/export/notion` returns `status === 'in_progress'`, renders blue status callout and polls `GET /api/meals/${mealId}/export/notion` every 1000ms up to 30 attempts.
  - On `status === 'completed'` or `'already_exported'`, stops polling, clears spinner, and displays green success banner with escaped Notion URL.

### 2. `settletable/transport.py`
* **Lines 645–655 (`GET /api/meals/{meal_id}/export/notion`)**:
  - Authenticates caller; enforces organizer authorization (`is_org == True`).
  - Returns current export record from `authority.get_notion_export(meal_id, rev)`.
* **Lines 689–701 (In-Progress Concurrency Lease)**:
  - If an export is currently marked `in_progress` and less than 60 seconds have elapsed, returns HTTP 202 with `status: in_progress`, preventing duplicate background workers from being spawned on rapid re-clicks.
* **Lines 751–783 (Background Export Dispatch)**:
  - Spawns a daemon thread with its own thread-local authority instance (`bg_auth = self.get_authority()`), ensuring zero cross-thread SQLite connection sharing.
  - Cleans up connection in `finally: self.close()`.
  - Handles completion or failure cleanly by updating SQLite `notion_exports` table (`record_notion_export_completed` or `clear_notion_export`).

### 3. `settletable/notion/exporter.py`
* **Lines 28–37 (`count_notion_blocks`)**:
  - Accurately recurses into table blocks: `count += len(tbl.get("children", []))` + 1 for the table block itself.
* **Lines 198–204 & 296–306 (Intelligent Rollup Logic)**:
  - Mathematically bounds total compact blocks to `<= 40`.
  - Aggregates base and adjustment shares for rolled-up diners and items.
* **Lines 674–701 (Pre-Creation Title Reconciliation)**:
  - Safely handles parent block children lookup. If title matches `🍽️ SettleTable: {merchant} ({meal_id})`, returns existing `page_id` and short-circuits page creation.

### 4. `settletable/notion/client.py`
* **Lines 271–282 (`MockNotionClient.create_page`)**:
  - Accurately appends a `child_page` block to the parent page's block list, correctly mirroring official Notion API behavior and allowing realistic testing of pre-creation title reconciliation in air-gapped environments.

### 5. `settletable/ocr/engine.py`
* **Lines 165–178 (`RapidOcrEngine.__init__`)**:
  - Implements resilient import fallback between `rapidocr` and `rapidocr_onnxruntime`.
  - Image header decoding (`validate_image_payload`, lines 86–132) checks magic bytes for PNG, JPEG, and WebP, and strictly rejects dimension bombs (>4096px or >16MP) and payloads exceeding 5MB before any raster allocation.

### 6. `tools/run_demo.py` & `tools/e2e_browser_test.mjs`
* **`tools/run_demo.py` (lines 36–65)**: Adds `--mock-ocr` flag to instantiate `MockOcrEngine`, using `tests/fixtures/ocr/tokens.json` or fallback Malaysian receipt tokens.
* **`tools/e2e_browser_test.mjs` (lines 284–306)**: Validates Stage 3 OCR Candidate staging card rendering and discard boundary in headless Chrome CDP.

---

## Severity Assessment Table

| Issue / Check | Severity | Status | Verification / Citation |
|---|---|---|---|
| Premature `ReplaceReceipt` on file upload | HIGH (historical) | **RESOLVED** | `settletable/static/app.js` lines 975–985 |
| WSGI worker starvation during Notion latency | HIGH (historical) | **RESOLVED** | `settletable/transport.py` lines 751–783 (202 Accepted) |
| Duplicate Notion pages on network failure/retry | MEDIUM (historical) | **RESOLVED** | `settletable/notion/exporter.py` lines 674–701 |
| Free workspace 1,000 block budget exhaustion | MEDIUM (historical) | **RESOLVED** | `settletable/notion/exporter.py` lines 25, 198–204, 296–306 |
| RapidOCR package import mismatch | LOW (historical) | **RESOLVED** | `settletable/ocr/engine.py` lines 165–178 |
| `settletable/calculation.py` financial stability | CRITICAL | **VERIFIED CLEAN** | 0 diff against main |
| SQLite thread safety in async Notion exporter | HIGH | **VERIFIED CLEAN** | `self._local` thread-local authority isolated per daemon thread |
| XSS in staged OCR candidate DOM rendering | MEDIUM | **VERIFIED CLEAN** | `settletable/static/app.js` lines 561–625 (`escapeHtml` enforced) |

---

## Final Review Recommendation: GO

**Recommendation: GO (Unconditional Pass)**

PR #12 satisfies all 5 consolidation gates with full test and browser E2E verification. All 154 unit tests and 9 real browser CDP test stages pass.
The autonomous PR review criteria under `AGENTS.md` are completely met. PR #12 is ready for merge into `main`.
