# Independent Security and Code Review: User-Acceptance Readiness Verification

**Repository:** `C:\LKY_Project\TabWise`  
**Baseline Commit:** `df0fcdb` (`df0fcdbba595749dcf434372f1f97f1fed9f43b1`)  
**Integrated Head:** `05b79ed` (`05b79ed9a5c898c199ae5dc185e5dc8d1e204b19`)  
**Reviewer:** Independent Security and Code Reviewer Subagent  
**Final Determination:** **GO (Unconditional Pass)**  
**Audit Record Date:** 2026-10-21  

---

## 1. Executive Summary

An independent security, architectural, and code review was conducted on the complete User-Acceptance Readiness changes integrated into `main` against baseline commit `df0fcdb`.

The scope encompasses 12 files modified across commits `d5759a6`, `78f92ad`, `84acc18`, `483c7b8`, and `05b79ed`:
- `settletable/static/app.js` (OCR candidate inline edit-before-accept table, live recalculation without focus loss, validation, acceptance, Server-Side Local Inference wording, `parseSen` negative sign support, and negative cash rounding sign preservation)
- `settletable/notion/exporter.py` (pre-creation title reconciliation re-raising `NotionAuthError`, `NotionValidationError`, `NotionNotFoundError`, and `NotionRateLimitError`)
- `settletable/notion/client.py` (`NotionHttpClient.query_block_children` cursor pagination loop with `max_pages=5` and `page_size=100`)
- `settletable/authority.py` (`record_notion_export_failed` tracking and 60-second timeout recovery in `get_notion_export`)
- `settletable/transport.py` (`allow_sync_export=False` default protecting `?sync=1`, ephemeral background worker thread lifecycle documentation, and granular error code recording in `_bg_export`)
- `tests/test_notion.py` (5 new regression tests verifying sync override protection, failed export recovery, cursor pagination, rate limit error bubbling, and granular background error codes)
- `tools/run_demo.py` & `docs/uat-handover.md` (reconciled Restoran Wan Sheng test meal with exact cent apportionment: Subtotal RM 15.20, Service RM 1.52, BNM Rounding -RM 0.02, Grand Total RM 16.70, Alice RM 13.18, Bob RM 3.52; secret hygiene with zero printed credentials or session links; distinction of 3 OCR testing layers; PR failure investigation and reliable fallback protocol)
- `tools/e2e_browser_test.mjs` (automated genuine browser image upload via `DataTransfer` & HTTP POST, inline correction, and negative cash rounding recalculation)

Both project verification suites executed with 100% pass rates:
1. `python -m unittest discover -s tests -v`: **159 tests passed in 79.911s (OK)**.
2. `node tools/e2e_browser_test.mjs`: **All 9 real browser Chrome CDP test stages passed in 5.2s**.

All 3 previously reported remediations have been verified, and all 5 project acceptance gates achieve an unconditional **PASS**.

---

## 2. Verification of the 3 Remediations

### Remediation 1: Negative BNM Cash Rounding Sign Preservation (`app.js` & `parseSen`) — VERIFIED
- **Implementation in `parseSen`** (`settletable/static/app.js`, lines 26–58):
  - Added `allowNegative = false` parameter.
  - Correctly parses optional leading negative sign before or after currency prefix (`-RM 0.02` or `RM -0.02` or `-0.02`).
  - Throws `Negative amount not allowed` if `isNegative && !allowNegative`, preserving strict validation for standard receipt line items while permitting negative adjustments.
  - Returns signed integer minor units: `isNegative ? -totalSen : totalSen`.
- **Implementation in `syncCandidateInputs`** (`settletable/static/app.js`, lines 1120–1145):
  - Adjustment parsing uses `parseSen(amountInput.value, true)`.
  - For `kind === 'discount'`, forces negative sign `-Math.abs(rawSen)`.
  - For `kind === 'service' || kind === 'tax'`, forces positive sign `Math.abs(rawSen)`.
  - For `kind === 'rounding'`, checks if input string starts with `-`; if so, preserves negative sign `-Math.abs(rawSen)` (e.g. `-0.02` remains `-2 sen`).
- **Live Recalculation**: Subtotal and total dynamically update via DOM text nodes without replacing input elements, preserving input focus and cursor caret during typing.
- **Automated Verification**:
  - `tools/e2e_browser_test.mjs` Stage 4b verifies that an OCR candidate with -RM 0.02 cash rounding recalculates candidate total accurately: RM 27.20 (items) + RM 1.52 (service) - RM 0.02 (rounding) = RM 28.70.

### Remediation 2: `NotionRateLimitError` Re-Raising in Pre-Creation Reconciliation — VERIFIED
- **Implementation in `exporter.py`** (`settletable/notion/exporter.py`, lines 691–711):
  - In `export_finalized_meal`, when checking parent block children for existing pages titled `🍽️ SettleTable: {merchant} ({meal_id})`:
    ```python
    try:
        existing_blocks = client.query_block_children(config.token, clean_parent_id)
        for blk in existing_blocks:
            ...
    except (NotionAuthError, NotionValidationError, NotionNotFoundError, NotionRateLimitError):
        raise
    except Exception:
        pass
    ```
  - `NotionRateLimitError` is explicitly caught and re-raised along with `NotionAuthError`, `NotionValidationError`, and `NotionNotFoundError`.
  - Only non-fatal generic exceptions (e.g. unexpected transport quirks where creation should still be attempted) are suppressed.
- **Automated Verification**:
  - `tests/test_notion.py`: `test_reconciliation_bubbles_rate_limit_and_auth_errors` passes.

### Remediation 3: Granular Error Codes in Background Export (`transport.py` `_bg_export`) — VERIFIED
- **Implementation in `transport.py`** (`settletable/transport.py`, lines 770–783):
  - In `_bg_export()`, specific exception handlers record granular error codes to SQLite:
    ```python
    except NotionRateLimitError:
        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_rate_limited')
    except NotionAuthError:
        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_auth_error')
    except (NotionValidationError, NotionNotFoundError):
        bg_auth.record_notion_export_failed(meal_id, rev, 'invalid_input')
    except NotionError:
        bg_auth.record_notion_export_failed(meal_id, rev, 'notion_error')
    except Exception:
        bg_auth.record_notion_export_failed(meal_id, rev, 'unexpected_error')
    ```
  - Synchronous error handling (lines 740–758) similarly calls `authority.record_notion_export_failed(meal_id, rev, code)`.
- **UI Presentation** (`settletable/static/app.js`, lines 1493–1506):
  - Polling handler checks `pollData.export.status === 'failed'`, terminates polling interval, re-enables button, and renders a descriptive error banner with the exact error code: `Export failed: ${errDetail}`.
- **Automated Verification**:
  - `tests/test_notion.py`: `test_async_export_granular_error_codes` forces rate limiting and verifies `export_digest == 'notion_rate_limited'` and `status == 'failed'`.

---

## 3. Comprehensive Evaluation Against the 5 Project Gates

### Gate 1: Invariants & Financial Correctness — PASS
1. **Integer Minor Units**: All monetary calculations, draft items, adjustments, allocations, and Notion exports strictly use integer sen.
2. **Cent Conservation**: Verified across all 159 unit tests and E2E browser tests. `settletable/calculation.py` remains 100% untouched (`git diff df0fcdb HEAD -- settletable/calculation.py` is empty).
3. **Subtotal and Total Invariants**: `subtotal_sen = sum(line_sen)`, `total_sen = subtotal_sen + sum(adjustment_sen)`.
4. **Mandatory Human Verification Gate**: In `settletable/static/app.js` (lines 462, 480), `canFinalize` requires `reviewConfirmed = Boolean(snap.review)`. Finalization remains blocked with `⚠️ Receipt must be verified before finalization.` until the physical checkbox and `ReviewReceipt` command are submitted and sealed with cryptographic digest.
5. **Negative BNM Cash Rounding**: Correctly preserved in candidate staging, draft application, calculation, and UI presentation without sign inversion.

### Gate 2: OCR Boundary & Staging — PASS
1. **Client-Side In-Memory Staging**: In `settletable/static/app.js`, extracted OCR proposals are stored exclusively in `state.ocrCandidate`. Zero database mutation occurs upon upload or candidate editing (`test_zero_state_and_database_mutation` passes).
2. **Explicit Verification & Mutation Boundaries**:
   - `Accept & Apply to Receipt`: Validates positive item line amounts, non-empty labels, and dispatches `ReplaceReceipt` command to SQLite.
   - `Discard`: Clears candidate in memory with zero HTTP mutation requests.
3. **Server-Side Local Inference Demarcation**:
   - UI explicitly displays: `LOCAL RECEIPT OCR SCANNER`, `Server-Side Local Inference`, `Upload a receipt photo ... via local server-side inference (RapidOCR ONNX)`, and `Analyzing receipt via local server-side inference (RapidOCR ONNX)...`.
   - Eliminates all inaccurate or misleading "on-device phone inference" claims.

### Gate 3: Notion Reliability & Pagination — PASS
1. **Cursor Pagination**: `NotionHttpClient.query_block_children` (lines 180–200) queries Notion blocks in increments of `page_size=100`, reading `has_more` and following `next_cursor` up to `max_pages=5` (bounded to 500 child blocks).
2. **Reconciliation Error Bubbling**: Title reconciliation re-raises authentication, validation, resource-not-found, and rate-limiting errors rather than masking them.
3. **Realistic Delivery Semantics**: Explicitly documented in `docs/uat-handover.md` and `settletable/notion/exporter.py` as *at-least-once with pre-creation title reconciliation*.

### Gate 4: Background Processing & Worker Starvation Defense — PASS
1. **Protected Sync Override**:
   - `SettleTableApp` defaults to `allow_sync_export=False` (configured only via `SETTLETABLE_ALLOW_SYNC_EXPORT=1` or constructor argument).
   - In production environments, `?sync=1` is ignored and requests safely dispatch to background daemon threads returning HTTP 202 Accepted (`test_sync_export_override_disabled_by_default` passes).
2. **Documented Ephemeral Lifecycle**:
   - Clearly documented in `settletable/transport.py` (lines 761–764) and `docs/uat-handover.md` Section 7.3: background worker threads are ephemeral daemon threads, not persistent message brokers; they do not survive process restarts.
3. **60-Second Timeout Recovery**:
   - `Authority.get_notion_export()` automatically converts lingering `in_progress` exports older than 60 seconds to `status='failed'` with `digest='timeout'`, allowing the user or script to re-trigger export cleanly without permanent lockup.
4. **Granular Error Recording**:
   - Both synchronous and asynchronous paths record specific error codes (`notion_rate_limited`, `notion_auth_error`, `invalid_input`, `notion_error`, `unexpected_error`) via `Authority.record_notion_export_failed()`.

### Gate 5: Secret Hygiene, UAT Accuracy & Traceability — PASS
1. **Zero Credential Logging**:
   - `tools/run_demo.py` logs zero session credentials, bearer tokens, or session links to stdout.
   - Session authentication is managed via host-only secure cookies (`HttpOnly; SameSite=Strict; Path=/`), and diner invitation links are generated and copied directly inside the organizer UI.
2. **Reconciled Restoran Wan Sheng Test Meal**:
   - Subtotal: RM 15.20 (Chicken Rice RM 12.00 + Ice Lemon Tea RM 3.20)
   - Service Charge (10%): RM 1.52 (Alice RM 1.20, Bob RM 0.32)
   - BNM Rounding: -RM 0.02 (Alice -RM 0.02, Bob RM 0.00)
   - Grand Total: RM 16.70 (Alice RM 13.18, Bob RM 3.52)
   - Verified that individual shares exactly sum to Grand Total: $13.18 + 3.52 = 16.70$ (0 residue).
3. **Distinction of 3 OCR Testing Layers**:
   - `docs/uat-handover.md` Section 3.3 clearly delineates:
     1. Genuine Image-Upload OCR Testing (binary HTTP POST, header/MIME verification, local server inference).
     2. Mock-Token Extraction (`MockOcrEngine` fixture replay without native ONNX wheels).
     3. Direct JavaScript Candidate Injection (`window.settletable.state.ocrCandidate` for headless UI/DOM testing).
4. **PR Failure Investigation & Governance Fallback Protocol**:
   - `docs/uat-handover.md` Section 8 documents root cause (missing `gh.exe` in Windows environment, private repo with Windows Credential Manager).
   - Establishes the 7-step governance fallback protocol: isolated feature branch -> independent subagent audit -> remediation & regression tests -> local verification (159 unit + real CDP browser) -> traceable `--no-ff` merge -> hosted CI -> durable records.

---

## 4. Test Execution Summary

### 1. Python Unit Test Suite
- Command: `python -m unittest discover -s tests -v`
- Results: **159 tests executed, 159 passed, 0 failures, 0 errors**
- Execution Duration: **79.911s**
- Status: **OK**

### 2. End-to-End Real Browser CDP Suite
- Command: `node tools/e2e_browser_test.mjs`
- Test Harness: Headless Chrome CDP via dual isolated instances (Organizer Alice & Diner Bob)
- Results:
  - [1/8] Local server started on port 8089.
  - [2/8] Organizer and Diner Chrome instances launched.
  - [3/8] Genuine browser image upload via `DataTransfer` & HTTP POST `/api/meals/dinner-e2e/ocr/extract` verified. Candidate card rendered; inline editing tested (price changed to 24.00, subtotal recalculates to RM 27.20); negative cash rounding (-RM 0.02) verified (total recalculates to RM 28.70); candidate discarded cleanly without SQLite mutation.
  - [4/8] Items added (Burger Set RM 24.00, Iced Tea RM 6.00); subtotal & total verified (RM 30.00); Human Receipt Review submitted and verified.
  - [5/8] Invitation URL generated with bearer secret redacted from console (`/invite/[REDACTED]`).
  - [6/8] Diner Bob opened invitation in isolated browser; redeemed token; joined room with diner cookie.
  - [7/8] Item claiming, real-time sync, and HTTP 409 stale conflict rejection verified.
  - [8/8] Meal finalized; exact calculations verified in both browsers (Alice RM 18.00, Bob RM 12.00, Total RM 30.00); page reload persistence verified.
  - [9/9] Organizer Notion export verified (HTTP 202 Accepted -> polling -> completed URL). Diner context verified free of export controls.
- Status: **ALL 9 REAL BROWSER E2E TEST STAGES PASSED SUCCESSFULLY**

---

## 5. Final Recommendation

**Determination: GO (Unconditional Pass)**

The integrated UAT readiness implementation meets all architectural, financial, security, and verification requirements. All 3 previously reported remediations have been verified by dedicated regression tests. All 5 acceptance gates pass without conditions. The codebase is fully ready for stakeholder walkthrough and Phase 4 planning.
