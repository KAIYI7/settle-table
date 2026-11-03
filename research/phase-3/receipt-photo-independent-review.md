# Independent Code & Security Review: Receipt Photo Retention & Notion Export

**Repository Working Tree**: `feature/receipt-photo-and-notion-export` vs `origin/main`  
**Reviewer**: Independent Security & Code Review Subagent  
**Status**: **PASS (GO FOR MERGE)**  
**Classification**: HIGH RISK (Financial correctness, access control, disk persistence, binary wire ingress, external integration)

---

## 1. Executive Summary & Merge Recommendation

An independent, rigorous review of the implementation on branch `feature/receipt-photo-and-notion-export` has been completed. The implementation satisfies all 10 remediations from `research/phase-3/receipt-photo-architecture-challenge.md` and fulfills the requirements in `.scratch/receipt-photo-and-notion-export/SPEC.md`.

- **Calculation Immutability**: `settletable/calculation.py` is **100% byte-untouched** (`git diff origin/main -- settletable/calculation.py` is empty).
- **Security & Authorization**: All mutating and read endpoints (`POST /ocr/extract`, `POST /receipt/photo`, `GET /receipt/photo`, `DELETE /receipt/photo`) strictly enforce authenticated organizer authority (returning 401 for unauthenticated requests, 403 for diners or non-members) across both WSGI transport and SQLite authority layers.
- **CSRF & Method Protection**: All mutating routes (`POST`, `DELETE`) strictly require `X-SettleTable-Action: 1` and validate Origin/Referer matching against `self.server_origin`.
- **Filesystem Isolation & Path Traversal Immunity**: Filenames are strictly synthesized as `{safe_meal_id}_{sha256[:16]}.{ext}`, sanitizing all characters outside `[A-Za-z0-9_-]` and preventing Windows Alternate Data Streams (ADS). All disk accesses verify `target_path.is_relative_to(storage_dir.resolve())`. Temporary files are cleaned up reliably in `finally` blocks.
- **Finalized Meal Immutability**: Mutations on finalized meals return HTTP 409 `finalized` inside SQLite `BEGIN IMMEDIATE` transactions, serializing safely against concurrent meal finalization commands.
- **Notion Integration & Block Budget**: Implements Notion's official 2-step single-part file upload API using Python's standard library (`urllib.request`). The compact block budget strictly reserves 6 top-level non-table blocks, ensuring that total page blocks (including nested table rows and the image block) remain $\le 40$ blocks. The UI explicitly guides users through the manual 4-step "Publish to web" workflow and displays a prominent financial data privacy warning.
- **Test Suite Results**:
  - Full project test suite: **249 / 249 tests PASSED** (`python -m unittest discover tests`).
  - Unit & Integration test suite: **17 / 17 tests PASSED** (`python -m unittest tests/test_receipt_photo.py`).
  - Headless Chrome E2E verification: **7 / 7 steps PASSED** (`node tools/verify_receipt_photo_flow.mjs`).

**Final Recommendation**: **GO** for merge into `main`.

---

## 2. Findings by Severity

| Severity | Count | Summary |
|---|:---:|---|
| **BLOCKER** | 0 | None. |
| **HIGH** | 0 | None. |
| **MEDIUM** | 0 | None. |
| **LOW** | 1 | Informational note on idempotency of `DELETE /receipt/photo` when photo does not exist. |

### Detailed Findings

#### [LOW-01] Idempotent DELETE Behavior on Non-Existent Receipt Photo
- **File & Lines**: `settletable/authority.py:1831-1836`, `settletable/transport.py:844-855`
- **Description**: Calling `DELETE /api/meals/{meal_id}/receipt/photo` on a meal where no photo has been uploaded (or where the photo was already deleted) executes `DELETE FROM receipt_photos WHERE meal_id=?` and completes with HTTP 200 `{"ok": true}` rather than returning HTTP 404 `photo_not_found`.
- **Assessment**: This adheres to standard REST and RFC 9110 §9.3.5 idempotent deletion semantics (deleting an already absent resource produces the intended end state without failure). This is safe, expected, and requires no code changes.

---

## 3. Detailed Verification Against Review Axes

### Axis 1: Security & Authorization

1. **Organizer-Only Access Control**:
   - `settletable/transport.py:769-776` (`POST /ocr/extract`):
     - Unauthenticated requests trigger `TransportError('invalid_session', 401)`.
     - Non-organizers trigger `TransportError('forbidden', 403)`.
   - `settletable/transport.py:801-808` (`POST /receipt/photo`):
     - Unauthenticated requests trigger `TransportError('invalid_session', 401)`.
     - Non-organizers trigger `TransportError('forbidden', 403)`.
   - `settletable/transport.py:823-830` (`GET /receipt/photo`):
     - Unauthenticated requests trigger `TransportError('invalid_session', 401)`.
     - Non-organizers trigger `TransportError('forbidden', 403)`.
   - `settletable/transport.py:845-852` (`DELETE /receipt/photo`):
     - Unauthenticated requests trigger `TransportError('invalid_session', 401)`.
     - Non-organizers trigger `TransportError('forbidden', 403)`.
   - **Defense-in-Depth**: Inside `settletable/authority.py` (`store_receipt_photo:1695`, `get_receipt_photo:1781`, `delete_receipt_photo:1823`), `self._authenticate(verifier, meal_id)` and `_require(is_organizer, 'forbidden')` are executed inside the database transaction, preventing any bypass.

2. **CSRF & Action Header Verification**:
   - `settletable/transport.py:398-429`:
     - Method check covers both `POST` and `DELETE`.
     - Header `X-SettleTable-Action: 1` is strictly required on all mutating requests; missing or invalid headers yield HTTP 400 `missing_action_header`.
     - For browser-context requests (cookie authentication or missing Bearer authorization), `HTTP_ORIGIN` or `HTTP_REFERER` is strictly compared against `self.server_origin`. Mismatches trigger HTTP 403 `origin_mismatch`.
     - `Content-Length` enforcement is route-aware: `DELETE` requests without a body (standard browser `fetch`) are permitted without triggering 411 `missing_content_length`, while `POST` endpoints enforce positive content length.

3. **Filesystem Isolation, Path Traversal & Windows ADS Prevention**:
   - `settletable/authority.py:475-487`: Receipt photos are stored in `<db_dir>/receipt_photos/` or explicit `storage_dir`, completely isolated from static web assets (`settletable/static/`).
   - `settletable/authority.py:1682-1688`:
     - `safe_meal_id = re.sub(r'[^A-Za-z0-9_-]', '_', meal_id)` eliminates all path separators (`/`, `\`) and Windows stream specifiers (`:`).
     - `{ext}` is mapped from an immutable dictionary (`{'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}`).
     - Disk filename is formatted as `{safe_meal_id}_{sha256[:16]}.{ext}`, preventing user-controlled filenames or arbitrary extensions.
   - `settletable/authority.py:1790-1792` & `1839-1841`:
     - Path resolution `target_path = (self.storage_dir / filename).resolve()` strictly validates `target_path.is_relative_to(self.storage_dir.resolve())`. Traversal attempts raise `forbidden`.

4. **Atomic Swaps & Temporary File Cleanup**:
   - `settletable/authority.py:1685-1774`:
     - Image bytes are written to a temporary file `{safe_meal_id}_{sha256[:16]}_{random_token}.tmp`.
     - Inside `BEGIN IMMEDIATE`, SQLite metadata is inserted/updated.
     - On successful commit, `tmp_path.replace(dest_path)` performs an atomic filesystem replace.
     - Any prior photo file with a different hash (`old_filename != filename`) is unlinked.
     - `except AuthorityError`, `except sqlite3.Error`, `except Exception`, and `finally` blocks explicitly ensure `if tmp_path.exists(): tmp_path.unlink()`.
   - `settletable/static/app.js:2750, 2774, 2943, 2981`: Object URLs created via `URL.createObjectURL` are revoked via `URL.revokeObjectURL` on replacement, removal, and request errors.

---

### Axis 2: Financial Correctness & Immutability

1. **Calculation Engine Invariance**:
   - `settletable/calculation.py` remains 100% byte-untouched.
   - Verified that `_receipt_digest(state['receipt'])` and calculation digest do not incorporate or depend on `receipt_photos` table records. Uploading, replacing, or deleting receipt photos causes zero changes to `receipt_digest`.
2. **Finalized Immutability & Race Condition Elimination**:
   - `settletable/authority.py:1694-1702` (`store_receipt_photo`) and `1822-1830` (`delete_receipt_photo`):
     - Both execute under `self._db.execute('BEGIN IMMEDIATE')`.
     - Both inspect `SELECT state FROM meals WHERE id=?` and assert `_require(state.get('calculation') is None, 'finalized')`.
     - If the meal has already been finalized, the operation raises `AuthorityError('finalized')` (HTTP 409).
     - Concurrent `Finalize` commands also acquire `BEGIN IMMEDIATE`, ensuring that finalization and photo mutations are strictly serialized without race conditions.
3. **Database Footprint & Snapshot Isolation**:
   - Raw binary bytes are never inserted into SQLite `meals.state`, audit logs, or snapshots.
   - `DraftSnapshot` (`settletable/authority.py:237-238`) exposes only `has_receipt_photo: bool` and safe metadata (`filename`, `content_type`, `byte_size`, `width`, `height`, `uploaded_at`). The 1MB snapshot size guard is fully respected.

---

### Axis 3: Notion Integration & Block Budget

1. **Official 2-Step File Upload Protocol**:
   - `settletable/notion/client.py:69-80` (`encode_multipart_file`): Encodes multipart payload without third-party libraries using standard `uuid` and bytes concatenation.
   - `settletable/notion/client.py:289-301` (`create_file_upload`): Sends `POST /v1/file_uploads` with `{"mode": "single_part", "filename": ..., "content_type": ...}`.
   - `settletable/notion/client.py:303-356` (`send_file_upload`): Sends `POST /v1/file_uploads/{id}/send` with `multipart/form-data` payload.
   - `settletable/notion/exporter.py:734-752`: The file upload to Notion occurs **prior** to `client.create_page`. If file upload fails, export terminates cleanly without creating an orphaned or empty Notion page.
2. **Compact Block Budget Accounting**:
   - `settletable/notion/exporter.py:314-317`:
     ```python
     used_blocks = (6 if image_block is not None else 5) + 1 + len(apportionment_rows) + 1 + 1
     remaining_item_budget = max(1, MAX_COMPACT_BLOCKS - used_blocks)
     ```
   - When an image block is included, fixed non-table blocks increase from 5 to 6. The available item budget is decremented by 1, preserving the strict invariant:
     `assert count_notion_blocks(blocks) <= 40`
3. **View-Only Sharing Workflow & Consent**:
   - `settletable/static/app.js:2637-2642`: The `[ ] Include original receipt photo in Notion report` checkbox is **default OFF**. If no photo exists, it is disabled.
   - `settletable/static/app.js:2482-2521` (`formatNotionSuccessHtml`): Clearly directs the organizer through Notion's manual 4-step "Publish to web" process (Share $\rightarrow$ Publish $\rightarrow$ Publish to web $\rightarrow$ Allow editing/comments/indexing OFF). SettleTable makes no claim of automatic workspace publishing.
   - A prominent amber privacy warning (`⚠️ Privacy Warning`) alerts the organizer to verify that no credit card PAN or personal phone numbers are exposed on the receipt slip.

---

### Axis 4: Code Quality & User Experience

1. **Zoom / Fullscreen Modal Controller**:
   - `settletable/static/app.js:61-206` (`openReceiptModal`, `closeReceiptModal`, `zoomReceiptModal`, `initReceiptModalEvents`):
     - Supports zoom buttons (zoom in by 1.25x, zoom out by 0.8x, reset to 100%), wheel zoom, and drag-to-pan clamped between 0.5x and 4.0x.
     - Supports mobile touch drag-to-pan (`touchstart`, `touchmove`, `touchend`).
     - Listens for `Escape` key to close the modal.
     - Focus management: focuses the close button upon opening and restores focus to `state.photoModalTrigger` upon closing.
     - Prevents body scrolling while open (`document.body.style.overflow = 'hidden'`).
   - `settletable/static/index.html:38-60`: Modal container includes `role="dialog"`, `aria-modal="true"`, `aria-labelledby="receipt-modal-title"`, and descriptive aria labels on zoom and close buttons.
2. **Validation & Error Handling**:
   - Validates file size $\le 5\text{MB}$ in browser (`app.js:2723`), WSGI transport (`transport.py:445`), image header validator (`engine.py:93`), and authority (`authority.py:1673`).
   - Rejects non-image MIME types and mismatched magic bytes.
   - Image dimensions are validated from binary headers without raster bitmap allocation, rejecting dimension bombs ($>4096\text{px}$ or $>16\text{MP}$).

---

## 4. Verification Artifacts & Test Evidence

1. **Receipt Photo Test Suite** (`tests/test_receipt_photo.py`):
   ```
   Ran 17 tests in 0.944s
   OK
   ```
2. **End-to-End Headless Chrome Flow** (`tools/verify_receipt_photo_flow.mjs`):
   ```
   [1/7] Bootstrapping room via UI in browser...
      ✓ Organizer view loaded
   [2/7] Uploading receipt image to trigger OCR and candidate staging...
      ✓ OCR candidate card displayed
      ✓ Staged source preview bar and Zoom button present
   [3/7] Testing Receipt Photo Fullscreen/Zoom Modal...
      ✓ Zoom modal opened (display: flex)
      ✓ Modal closed via Escape key
   [4/7] Accepting candidate and verifying attached photo card...
      ✓ Attached receipt photo card rendered with complete lifecycle controls
      ✓ Modal opened from card and closed via ✕ button
   [5/7] Reviewing receipt, allocating items, and finalizing meal...
      ✓ Receipt confirmed and sealed
      ✓ Meal finalized and finalized view rendered
   [6/7] Verifying finalized view receipt photo card and Notion photo option...
      ✓ Preserved receipt photo accessible after finalization
      ✓ Notion photo option verified: Default OFF and enabled
   [7/7] Testing Notion export with photo option and view-only sharing guidance...
      ✓ 4-step view-only sharing guidance and privacy warning verified
      ✓ Notion page verified: compact count 9 <= 40, image block attached: file_upload id=33333333-4444-5555-6666-000000000001
   ALL RECEIPT PHOTO E2E TESTS PASSED WITH 100% SUCCESS!
   ```
3. **Full Project Regression Suite**:
   ```
   Ran 249 tests in 85.080s
   OK
   ```

---

## 5. Conclusion

The implementation is robust, thoroughly tested, and adheres strictly to the security, financial, and UX specifications. **GO FOR MERGE**.
