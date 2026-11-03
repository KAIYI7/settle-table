# SettleTable Receipt Photo Retention & Notion Export Specification (Remediated)

## 1. Overview & Objective

This specification details the implementation for two approved UX capabilities in SettleTable:
1. **Original Scanned Receipt Photo Display & Retention**: Storing, viewing, zooming, and managing the source receipt image locally with strict organizer authorization, atomic replacement, and finalized meal immutability.
2. **Optional Original-Photo Export to Notion**: Enabling organizers to securely upload and attach the original receipt photo directly to the finalized Notion report via Notion's official File Upload API, accompanied by a verified view-only sharing guide.

All 10 remediations from the independent architecture and security challenge (`research/phase-3/receipt-photo-architecture-challenge.md`) are formally integrated into this specification.

---

## 2. Security, Privacy & Financial Architecture Tenets

### 2.1 Private Local Storage (Zero Public URLs, Zero DB Bloat)
- **Filesystem Isolation**: Binary receipt images are stored in a dedicated private directory (`<db_dir>/receipt_photos/` or configured `storage_dir`), completely isolated from static web assets (`settletable/static/`).
- **No Embedded Bytes in Snapshots or Audit Logs**: Canonical meal snapshots and SQLite `meals.state` enforce a strict 1MB size limit (`len(data) <= 1_048_576`). Images are strictly excluded from meal state, commands, and snapshots. Snapshots expose only lightweight metadata: `has_receipt_photo: bool = False` (or dict with safe metadata).
- **Path Traversal & Windows ADS Immunity (Remediation F-06)**:
  - Filenames on disk are generated as `{safe_meal_id}_{sha256[:16]}.{ext}` where `safe_meal_id = re.sub(r'[^A-Za-z0-9_-]', '_', meal_id)`.
  - `{ext}` is strictly derived from validated MIME format (`{'png': 'png', 'jpeg': 'jpg', 'webp': 'webp'}[detected_fmt]`).
  - SQLite `receipt_photos` stores strictly the relative `filename`, never an absolute path.
  - Serving resolves `target_path = (storage_dir / filename).resolve()` and strictly asserts `target_path.is_relative_to(storage_dir.resolve())`.

### 2.2 Wire Ingestion & Method Boundary Guards (Remediations F-01, F-02)
- **Raw Binary Ingestion for Image Uploads**:
  - `SettleTableApp._dispatch` identifies raw image routes:
    `POST /api/meals/{meal_id}/ocr/extract` and `POST /api/meals/{meal_id}/receipt/photo`.
  - For image routes, ingress bounds allow up to `MAX_IMAGE_BYTES = 5,242,880` (5 MB), bypassing JSON parsing.
  - Non-image POST routes strictly retain `MAX_BODY_BYTES = 1,048,576` (1 MB) and `parse_strict_json`.
- **CSRF & Action Header Guard on `DELETE`**:
  - `method in ('POST', 'DELETE')` enforces strict Origin/Referer verification and `X-SettleTable-Action: 1` header checks.

### 2.3 Access Control & Finalized Immutability (Remediations F-04, F-05)
- **Organizer-Only Authority**:
  - `POST /api/meals/{meal_id}/ocr/extract`: Authenticated organizer only.
  - `POST /api/meals/{meal_id}/receipt/photo`: Authenticated organizer only.
  - `GET /api/meals/{meal_id}/receipt/photo`: Authenticated organizer only (401 for unauthenticated, 403 for diners or non-members).
  - `DELETE /api/meals/{meal_id}/receipt/photo`: Authenticated organizer only.
- **Serving Invariants**:
  - Headers: `Content-Type: <validated_mime>`, `X-Content-Type-Options: nosniff`, `Content-Disposition: inline; filename="receipt.<ext>"`, `Cache-Control: private, no-cache, no-store, must-revalidate`.
- **Finalized Meal Immutability & Race Condition Elimination**:
  - Once finalized (`meals.state.calculation is not None`), `POST` and `DELETE` return HTTP 409 `finalized`.
  - Mutations execute inside SQLite `BEGIN IMMEDIATE` transactions to prevent race conditions against concurrent `Finalize` commands.
  - Organizers retain read-only `GET` access post-finalization for audit and dispute resolution.

### 2.4 Atomic Swap & Lifecycle Cleanup (Remediation F-07)
- New uploads write to `{safe_meal_id}_{sha256[:16]}.tmp` in `storage_dir`.
- Inside `BEGIN IMMEDIATE`, SQLite metadata is updated.
- Upon commit, `.tmp` is atomically renamed to destination.
- Any prior photo file with a different hash is unlinked.
- `finally` block unlinks any remaining `.tmp` file on write or commit failure.
- Meal deletion (`DELETE /api/meals/{meal_id}/receipt/photo`) removes the SQLite row and unlinks the file from disk.

### 2.5 Notion File Upload Architecture & Budget (Remediations F-03, F-08, F-09)
- **Official 2-Step File Upload**:
  1. `POST /v1/file_uploads` (`mode="single_part"`, `filename`, `content_type`) -> `id` (status `pending`).
  2. `POST /v1/file_uploads/{id}/send` with `multipart/form-data` using standard-library `encode_multipart_file` -> status `uploaded`.
  3. Include image block in page `children`:
     ```json
     {
       "object": "block",
       "type": "image",
       "image": {
         "type": "file_upload",
         "file_upload": {
           "id": "<file_upload_id>"
         }
       }
     }
     ```
- **Execution Order & Error Policy**:
  - The photo is uploaded to Notion *before* calling `create_page`. If file upload fails (network error, rate limit, timeout), the export fails cleanly without creating an orphan or incomplete page.
- **Compact Block Budget Protection**:
  - `format_compact_meal_blocks` accounts for the image block in its non-table block count (6 instead of 5), guaranteeing total compact blocks strictly remain $\le 40$ blocks without assertion failure.
- **Default OFF & Explicit Consent**:
  - Checkbox in UI: `[ ] Include original receipt photo in Notion report` (default `False`). Only sent when checked.

### 2.6 View-Only Sharing Workflow & Privacy Alert (Remediation F-10)
- The UI explicitly states that Notion pages created by integrations are private to the workspace by default.
- Guides the organizer through the verified 4-step manual workflow:
  1. Click **Open in Notion**.
  2. Click **Share** (top right) $\rightarrow$ open the **Publish** tab $\rightarrow$ click **Publish to web**.
  3. Set access permissions:
     - **Allow editing**: OFF
     - **Allow comments**: OFF
     - **Search engine indexing**: OFF
  4. Copy web link and share with diners.
- Prominent sensitive financial data warning:
  `"Warning: Attaching the original receipt photo will expose the raw slip to anyone with the link. Confirm the receipt contains no sensitive private details (e.g. credit card PAN, personal phone numbers) before sharing."`

---

## 3. Data Schema & Models

### 3.1 SQLite `receipt_photos` Table
```sql
CREATE TABLE IF NOT EXISTS receipt_photos (
    meal_id TEXT PRIMARY KEY REFERENCES meals(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    uploaded_at REAL NOT NULL,
    uploaded_by TEXT NOT NULL,
    FOREIGN KEY(meal_id, uploaded_by) REFERENCES participants(meal_id, id)
);
```

### 3.2 Notion Client Protocol
```python
class NotionClientProtocol(Protocol):
    ...
    def create_file_upload(self, token: str, filename: str, content_type: str) -> dict[str, Any]:
        ...
    def send_file_upload(self, token: str, file_upload_id: str, file_bytes: bytes, content_type: str) -> dict[str, Any]:
        ...
    def upload_file(self, token: str, filename: str, content_type: str, file_bytes: bytes) -> str:
        ...
```

---

## 4. UI/UX Design

### 4.1 Responsive Preview Layout
- **During OCR Extraction**: Spinner with thumbnail preview if local file is selected via `URL.createObjectURL`.
- **During Candidate Staging**:
  - Desktop ($\ge 768\text{px}$): Dual pane layout / collapsible receipt preview card side-by-side or above candidate editor.
  - Mobile ($< 768\text{px}$): Sticky receipt preview toggle banner and collapsible drawer.
- **Zoom / Fullscreen Modal**:
  - Accessible modal dialog (`role="dialog"`, `aria-modal="true"`) displaying the high-resolution receipt image.
  - Zoom controls: `[ + ] [ - ] [ Reset ]` and pinch/drag pan.
  - Close button and `Escape` key handler. Focus returns to trigger button upon close.
- **After Finalization**:
  - Organizer can view the archived photo anytime via "View Receipt Photo" modal.
  - Replace/Delete buttons hidden/disabled to preserve immutability.

---

## 5. Acceptance Verification Gates
1. **Local Validation Gate**: `validate_image_payload` rejects invalid magic bytes, dimension overflows, or size $>5\text{MB}$ with HTTP 400.
2. **WSGI Binary Routing Gate**: `POST /api/meals/{meal_id}/receipt/photo` accepts raw binary image up to 5MB without JSON parsing or 413.
3. **CSRF & Method Guard Gate**: `DELETE /receipt/photo` enforces `X-SettleTable-Action: 1` and Origin matching.
4. **Access Control Gate**: Unauthenticated -> 401; Diners -> 403; Organizer -> 200.
5. **Finalized Immutability Gate**: `POST` and `DELETE` on finalized meals return 409 `finalized`. `GET` returns 200 raw image bytes to organizer.
6. **Windows Filesystem Safety Gate**: Filenames sanitize colons/dots; traversal attempts outside `storage_dir` fail with 403.
7. **Notion Compact Budget Gate**: Finalized export with `include_receipt_photo=True` produces a valid Notion image block, and total blocks remain $\le 40$ blocks without assertion failure.
8. **Financial Invariant Gate**: Attaching or deleting receipt photos produces 0 changes in `_receipt_digest`, 0 changes in `calculation.py` results, and 0 float drift. Zero secret leakage across all loggers and exception strings.
