# Independent Architecture, Security, Financial-Correctness, and Protocol Challenge: Receipt Photo Retention & Notion Export

**Target Specification**: `.scratch/receipt-photo-and-notion-export/SPEC.md`  
**Target Components**: `settletable.transport`, `settletable.authority`, `settletable.ocr`, and `settletable.notion`  
**Review Date**: 2026-11-03  
**Reviewer**: Independent Architecture, Security & Financial Integrity Challenger (Research Subagent)  
**Determination**: **CONDITIONAL PASS (REVISE SPEC BEFORE IMPLEMENTATION)**

---

## 1. Executive Summary & Determination

The draft specification (`.scratch/receipt-photo-and-notion-export/SPEC.md`) establishes a well-conceived architecture for introducing local receipt photo retention and optional export to Notion. Its core privacy, storage, and financial invariants—keeping binary receipt images strictly off public web routes, out of database blobs, and out of canonical meal snapshot bytes; maintaining SettleTable's calculation engine and SQLite ledger as the sole authority; enforcing organizer-only authority; and leveraging Notion's official 2-step File Upload API rather than third-party hosting—are sound and align with SettleTable's foundational mission.

However, an adversarial architecture, security, and protocol challenge across WSGI transport constraints, Windows filesystem semantics, SQLite concurrency isolation, Notion REST API specifications, and Malaysian dining privacy has identified **10 concrete defects, protocol gaps, and operational hazards** (3 High, 5 Medium, 2 Low-Medium). Most critically:

1. **WSGI Dispatcher Fatal Body Ingestion Collision (Showstopper)**: The spec introduces `POST /api/meals/{meal_id}/receipt/photo` for raw binary image uploads ($\le 5\text{MB}$), but in `settletable.transport.SettleTableApp._dispatch`, non-OCR POST routes unconditionally enforce `MAX_BODY_BYTES = 1,048,576` (1MB) and execute `parse_strict_json(raw_body)`. Any binary upload to `/receipt/photo` will either trigger HTTP 413 `payload_too_large` (>1MB) or crash in `parse_strict_json` with `UnicodeDecodeError` / `malformed_json` (HTTP 400).
2. **Unprotected `DELETE` HTTP Method Boundary & CSRF Bypass**: SettleTable's CSRF Origin/Referer check and mandatory `X-SettleTable-Action: 1` header check are strictly scoped to `if method == 'POST':`. Introducing `DELETE /api/meals/{meal_id}/receipt/photo` without extending these guards allows cross-origin unauthorized photo deletions via ambient cookie authentication.
3. **Compact Block Budget Overflow Assertion Crash in Notion Exporter**: `format_compact_meal_blocks` calculates remaining item rows assuming exactly 5 top-level non-table blocks and caps rows to hit $\le 40$ blocks total. Appending a 6th top-level image block without accounting for it in the item budget calculation causes total blocks to reach 41, triggering an immediate crash on `assert count_notion_blocks(blocks) <= MAX_COMPACT_BLOCKS`.
4. **Filesystem Vulnerabilities on Windows & Path Traversal**: Generating filenames as `{meal_id}_{sha256[:16]}.{ext}` exposes systems to Windows Alternate Data Streams (NTFS ADS) because `_id(meal_id)` permits colons (`:`). Furthermore, storing absolute `file_path` in SQLite introduces arbitrary file read and portability risks if relative traversal is unchecked.
5. **Finalization Concurrency Race Condition**: Performing photo mutations and finalized status checks outside an immediate database write lock creates a race window where a concurrent `Finalize` command can commit between check and write, violating finalized meal immutability.

**Determination**: **CONDITIONAL PASS**. The specification is conceptually and architecturally viable, but must be revised with the concrete remediations detailed below before implementation commences.

---

## 2. Concrete Finding List

| ID | Severity | Title | Impact | Remediation Summary |
|---|---|---|---|---|
| **F-01** | **HIGH** | WSGI Dispatcher Fatal Body Ingestion Collision on `POST /receipt/photo` | Binary image uploads >1MB trigger 413, and uploads $\le 1\text{MB}$ crash with 400 `malformed_json` | Update dispatcher in `transport.py` to route raw binary image bodies for both `ocr/extract` and `receipt/photo` routes up to `MAX_IMAGE_BYTES` (5MB). |
| **F-02** | **HIGH** | Unprotected `DELETE` HTTP Method Boundary & CSRF Bypass | `DELETE /receipt/photo` lacks `X-SettleTable-Action` and CSRF Origin checks, enabling cross-origin photo deletion | Extend boundary guards in `transport.py` to `if method in ('POST', 'DELETE'):`. |
| **F-03** | **HIGH** | Compact Block Budget Overflow Crash (`41 > 40` blocks) | Exporting meals with receipt photo asserts and crashes with HTTP 500 when items saturate budget | Pass `has_image_block: bool` into `format_compact_meal_blocks` and adjust `used_blocks` base count from 5 to 6. |
| **F-04** | **MEDIUM** | Missing Status Code Mapping for `meal_finalized` | Unmapped error code defaults to HTTP 400 Bad Request instead of HTTP 409 Conflict | Standardize on canonical error code `'finalized'` (already 409 in `STATUS_MAP`), or explicitly register `'meal_finalized': 409`. |
| **F-05** | **MEDIUM** | Concurrency Race Window on Finalize vs Photo Mutation | Photo can be uploaded or deleted concurrently as `Finalize` commits | Wrap all photo mutations in SQLite `BEGIN IMMEDIATE` transactions; verify `meals.state.calculation is None` under the lock. |
| **F-06** | **MEDIUM** | Windows Alternate Data Streams (ADS) & Path Traversal Risks | Colons in `meal_id` trigger NTFS ADS; absolute `file_path` enables path traversal | Sanitize `meal_id` to `[A-Za-z0-9_-]`; hardcode extension from `validate_image_payload`; store only relative filename in SQLite and resolve within `storage_dir`. |
| **F-07** | **MEDIUM** | Missing Atomic Swap & Disk Space Exhaustion / Orphan Leaks | Failed writes corrupt existing photos; crashed uploads leak 5MB chunks on disk | Use atomic staging (`.tmp` -> rename); unlink temporary files in `finally`; enforce total storage directory bounds. |
| **F-08** | **MEDIUM** | Standard-Library Multipart Form Data Encoding Omission | Notion's `/send` endpoint requires `multipart/form-data`; missing standard library spec risks broken payload or third-party deps | Specify a pure-Python `urllib.request` standard-library multipart encoder with sanitized error handling. |
| **F-09** | **LOW-MED** | Notion Photo Upload Failure Policy Undefined | If Notion photo upload fails, silently creating page violates consent; duplicate exports fail title reconciliation | Mandate photo upload precedes `create_page`; fail entire export cleanly if photo upload fails; let unattached Notion uploads expire. |
| **F-10** | **LOW-MED** | View-Only Sharing Guidance Lacks Web Indexing & Data Alerts | Public web sharing without indexing off exposes diner names and receipt payment card info to search engines | Update 4-step guide with explicit instructions to disable Search Engine Indexing and display a sensitive financial data warning. |

---

## 3. Detailed Analysis Across the 6 Dimensions

### Dimension 1: Local Private File Retention vs Public URL Risks

#### 1.1 Directory Traversal Defense
- Sanitize `meal_id` for filesystem paths: `safe_meal_id = re.sub(r'[^A-Za-z0-9_-]', '_', meal_id)`.
- Hardcode `{ext}` strictly from the validated format: `{'png': 'png', 'jpeg': 'jpg', 'webp': 'webp'}[detected_fmt]`.
- Store only the relative filename (`filename`) in SQLite `receipt_photos`.
- Serve files strictly by resolving against `storage_dir`:
  ```python
  target_path = (storage_dir / filename).resolve()
  if not target_path.is_relative_to(storage_dir.resolve()):
      raise TransportError('forbidden', 403)
  ```

#### 1.2 Content-Type Spoofing & Polyglot Defense
- `validate_image_payload` strictly checks magic bytes (PNG, JPEG, WebP) and reads dimensions from binary headers.
- When serving `GET /api/meals/{meal_id}/receipt/photo`:
  1. `Content-Type` set strictly from validated record.
  2. `X-Content-Type-Options: nosniff` header sent.
  3. `Content-Disposition: inline; filename="receipt.{ext}"`.
  4. `Cache-Control: private, no-cache, no-store, must-revalidate`.

#### 1.3 File Deletion Semantics on Replace or Delete
- Staged writing to `{safe_meal_id}_{sha256[:16]}.tmp` in `storage_dir`.
- Inside `BEGIN IMMEDIATE`, update metadata in SQLite.
- Commit, rename `.tmp` to final filename, and unlink old file if different.
- In `finally`, unlink any left-over `.tmp` file on failure.

#### 1.4 Disk Space Exhaustion & Quotas
- Exactly one receipt photo per meal in SQLite (`meal_id TEXT PRIMARY KEY`).
- Payload capped at 5 MB.
- Optional directory limit defense.

---

### Dimension 2: Authorization and Boundary Safety

#### 2.1 Route Boundary Matrix
- `POST /api/meals/{id}/ocr/extract`: Authenticated Organizer only (401 unauthenticated, 403 diner).
- `POST /api/meals/{id}/receipt/photo`: Authenticated Organizer only (401 unauthenticated, 403 diner).
- `GET /api/meals/{id}/receipt/photo`: Authenticated Organizer only (401 unauthenticated, 403 diner).
- `DELETE /api/meals/{id}/receipt/photo`: Authenticated Organizer only (401 unauthenticated, 403 diner).

#### 2.2 Wire Boundary Ingestion (Fixing F-01 & F-02)
- Route raw binary image bodies up to `MAX_IMAGE_BYTES` (5MB) for both `ocr/extract` and `receipt/photo`.
- Extend `X-SettleTable-Action: 1` and CSRF origin guards to `if method in ('POST', 'DELETE'):`.

---

### Dimension 3: Finalized Meal Immutability

#### 3.1 Immutability Invariant
- `POST` and `DELETE` on finalized meals return HTTP 409 `finalized`.
- `GET` on finalized meals returns HTTP 200 OK (organizer read-only audit access).
- Mutations wrapped in `BEGIN IMMEDIATE` checking `state['calculation'] is None` under the lock (eliminating F-05).

---

### Dimension 4: Notion File Upload API Protocol Compliance

#### 4.1 Notion API 2-Step Protocol
1. Step 1: `POST /v1/file_uploads` (`mode="single_part"`, `filename`, `content_type`) -> `id` (status `pending`).
2. Step 2: `POST /v1/file_uploads/{id}/send` (`multipart/form-data`) -> status `uploaded`.
3. Step 3: Attach Image Block referencing `file_upload: {"id": id}`.

#### 4.2 Notion Free Plan Limits Alignment
- SettleTable 5MB limit matches Notion Free plan 5MB per-file upload limit.

#### 4.3 Compact Block Budget Invariant (Fixing F-03)
- When image block is included, adjust non-table blocks base count from 5 to 6 in `format_compact_meal_blocks`.
- Enforces total blocks $\le 40$.

#### 4.4 Pure Standard-Library Multipart Form Data Encoder (Fixing F-08)
- `encode_multipart_file` implemented in Python standard library (`urllib.request`).

---

### Dimension 5: View-Only Sharing Workflow

#### 5.1 No False Claims & Accurate Guidance
- Clear notice that exported report is initially private.
- 4-step manual sharing guide with instruction to turn OFF search engine indexing and warnings regarding sensitive receipt data.

---

### Dimension 6: Financial Integrity

- Zero impact on `settletable.calculation`, sen-level math, or `_receipt_digest`.
- Canonical meal snapshots and `meals.state` remain $<100\text{KB}$.
