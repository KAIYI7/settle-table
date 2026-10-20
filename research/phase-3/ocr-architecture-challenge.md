# Independent Architecture and Security Challenge: Bounded Local OCR Pipeline

**Target Document**: `C:\LKY_Project\TabWise\.scratch\local-ocr\SPEC.md`  
**Target Component**: `settletable.ocr` and `settletable.transport` (`POST /api/meals/{meal_id}/ocr/extract`)  
**Review Date**: 2026-10-21  
**Reviewer**: Independent Architecture & Security Challenger  
**Determination**: **CONDITIONAL PASS (REVISE SPEC BEFORE IMPLEMENTATION)**

---

## 1. Executive Summary & Determination

The draft specification (`.scratch/local-ocr/SPEC.md`) provides a well-motivated architectural blueprint for introducing local receipt OCR to SettleTable. Its foundational non-negotiables—zero cloud fallback, strictly local/self-hosted execution, advisory proposal generation with zero authoritative database mutation, and mandatory organizer physical verification before receipt sealing—are completely sound and align with SettleTable's privacy and financial integrity mission.

However, an adversarial architecture and domain audit has identified **6 critical defects and operational hazards** across wire handling, memory safety, Malaysian statutory accounting, and CI reproducibility that must be remediated in the specification before code is written:

1. **WSGI Transport Pipeline Incompatibility (Showstopper)**: Currently, `settletable.transport.SettleTableApp._dispatch` unconditionally executes `parse_strict_json(raw_body)` on *every* `POST` request before inspecting the route. Sending raw binary image bytes (`image/jpeg`, `image/png`, `image/webp`) will crash in `parse_strict_json` with `UnicodeDecodeError` / `malformed_json` (400), rendering binary image uploads inoperable.
2. **Decompression Bomb & Memory Exhaustion Hazard**: A 5 MB payload size limit bounds wire bytes, but does **not** bound decompressed pixel memory. A 2 MB compressed PNG/JPEG or sparse image can decompress into a 30,000×30,000 RGB bitmap requiring >2.7 GB of RAM in native OpenCV/PIL/ONNX inference runners, crashing the WSGI process with Out-Of-Memory (OOM). Pixel dimension bounds are completely missing from the spec.
3. **Dual Base64/Binary Wire Transport Flaw**: Allowing `{ "image_base64": "..." }` in JSON for 5 MB images incurs a 33% payload bloat (~6.67 MB), violates the existing 1 MB `MAX_BODY_BYTES` limit, triggers high-overhead byte-by-byte string depth scanning in `_check_nesting_depth` (~6.7M character iterations in Python), and causes multi-megabyte heap duplications.
4. **Malaysian Tax-Inclusive Subtotal Invariant Conflict (The Wan Sheng Defect)**: In Malaysian tax-inclusive receipts, line items are printed with tax included (e.g. Wan Sheng items sum to 600 sen), while the slip prints "Subtotal: 5.66" (net pre-tax) and "GST: 0.34". SettleTable's core domain invariant (`calculation.py:201`) strictly enforces `item_subtotal == meal.subtotal_sen`. If the parser sets `subtotal_sen = 566` based on the printed label, `settletable.calculation.calculate()` will reject the receipt with `subtotal_mismatch`.
5. **Domain Model Mismatch with `settletable.calculation` and `authority`**:
   - `CandidateAdjustment.kind` uses `"service_charge"`, whereas `calculation.py:222` accepts strictly `("tax", "service", "discount", "rounding")`.
   - `CandidateAdjustment` discount amounts are specified as positive sen, whereas `calculation.py:225` strictly requires discounts to be negative sen.
   - `CandidateAdjustment.eligible_item_ids` is typed as non-optional `tuple[str, ...]`; passing an empty tuple `()` triggers `collection_bound` error in `calculation.py:231`.
   - `CandidateAdjustment` omits `label` and `rationale` required by `settletable.authority.ReceiptAdjustment`.
6. **CI Portability & Test Asset Rights Clearance**: The 6 historical Malaysian dining scans from Phase 1 are legally withheld from Git due to unconfirmed redistribution rights (`research/phase-1/ocr-validation.md:3`). A specification mandating that CI run against these raw image files will break on fresh checkouts. CI must run deterministically using pre-recorded token fixtures (`MockOcrEngine`) and fully cleared synthetic images.

**Gate Determination: CONDITIONAL PASS**. The specification is architecturally viable and secure once updated with the remediations detailed below.

---

## 2. Wire Boundary & Parser Limits Challenge

### 2.1 5MB Payload Limit vs. Decompression Memory Exhaustion
- **The Issue**: A wire payload limit (`MAX_IMAGE_BYTES = 5,242,880`, 5 MB) protects the socket from unbounded network transfer, but does **not** protect process memory during image decoding.
- **Decompression Bomb Hazard**:
  - Image formats (PNG, JPEG, WebP) use lossless or lossy compression. A specially crafted 500 KB PNG file with high repetition can decompress to dimensions of $20,000 \times 20,000 \times 3$ channels = 1.2 GB of raw uncompressed bitmap in RAM.
  - In Python, `RapidOCR` internally delegates image loading to OpenCV (`cv2.imdecode`) or Pillow (`PIL.Image.open`). When OpenCV or PIL decodes a decompression bomb, it allocates the uncompressed bitmap directly in heap.
  - SettleTable's WSGI server runs as a lightweight, single-process or constrained-thread local service. An uncompressed allocation of 1–3 GB will trigger OS memory thrashing or an immediate OOM crash.
- **Remediation**:
  1. The transport/engine pipeline must enforce strict **image dimension limits** immediately upon parsing the image header, *before* passing the full raster to ONNX Runtime:
     - `MAX_IMAGE_WIDTH = 4096` pixels.
     - `MAX_IMAGE_HEIGHT = 4096` pixels.
     - `MAX_IMAGE_PIXELS = 16_777_216` (16 megapixels).
  2. If an image exceeds these pixel bounds, the server must reject it immediately with HTTP 400 `invalid_image` and detail `image_dimensions_too_large`.

### 2.2 Magic Bytes Verification & Polyglot Rejection
- **The Draft Spec**:
  - JPEG: `\xFF\xD8\xFF`
  - PNG: `\x89PNG\r\n\x1A\n`
  - WebP: `RIFF....WEBP`
- **Challenger Audit**:
  1. **WebP Byte Offsets**: The spec writes `RIFF....WEBP` informally. The exact specification must be:
     `len(payload) >= 12 and payload[:4] == b'RIFF' and payload[8:12] == b'WEBP'`.
     Bytes 4–7 represent the 32-bit little-endian file size; the parser must also verify that the header size does not exceed `len(payload)`.
  2. **PNG Magic Bytes**: Must be exactly 8 bytes: `payload[:8] == b'\x89PNG\r\n\x1a\n'`.
  3. **JPEG Magic Bytes**: Must be at least 3 bytes: `len(payload) >= 3 and payload[:3] == b'\xff\xd8\xff'`.
  4. **Polyglot & Malicious Payload Rejection**:
     - *SVG / HTML / XML*: Modern vector graphics or HTML injection files start with `<?xml`, `<!DOCTYPE`, or `<svg`. These byte sequences are completely distinct from JPEG, PNG, and WebP magic bytes and are strictly rejected at byte 0.
     - *Executable / Script Masquerading*: PHP scripts, shell scripts, and Windows PE (`MZ`) executables are strictly rejected by the magic byte check.
     - *Image Polyglots (e.g. JPEG + HTML comments / EXIF scripts)*: Even if an image file contains malicious HTML/JS within EXIF metadata comments, SettleTable never stores the image, never writes it to disk, and never serves it back as a web asset (`img-src 'self' data:` CSP prevents inline external script execution). The bytes are consumed strictly by in-memory OCR routines and immediately garbage collected.
  5. **Content-Type Header vs. Magic Byte Consistency**:
     - The transport must verify that the `Content-Type` header matches the detected magic bytes:
       - `image/jpeg` $\leftrightarrow$ JPEG magic bytes.
       - `image/png` $\leftrightarrow$ PNG magic bytes.
       - `image/webp` $\leftrightarrow$ WebP magic bytes.
     - Mismatches (e.g. `Content-Type: image/jpeg` with PNG bytes) must be rejected with HTTP 400 `invalid_image`.

### 2.3 Base64 JSON vs. Raw Binary Body in WSGI
- **Current Pipeline Incompatibility (SHOWSTOPPER)**:
  Look at `settletable.transport.SettleTableApp._dispatch` (lines 370–386):
  ```python
  # Read body for POST
  body_data = None
  if method == 'POST':
      ...
      raw_body = wsgi_input.read(length) if wsgi_input else b''
      body_data = parse_strict_json(raw_body) if raw_body else {}
  ```
  `parse_strict_json` decodes `raw_body.decode('utf-8')`. Binary image bytes contain arbitrary byte values (e.g. `0xFF`, `0xD8`) that are invalid UTF-8. The server will raise `TransportError('malformed_json', 400)` before route matching ever takes place!
- **Hazards of Supporting Base64 JSON**:
  - A 5 MB binary image encoded as base64 becomes **6.67 MB**.
  - `parse_strict_json` enforces `MAX_BODY_BYTES = 1,048,576` (1 MB). A 6.67 MB JSON payload triggers HTTP 413 `payload_too_large`.
  - `_check_nesting_depth` scans the entire string character-by-character in Python. Scanning a 6.7 million character string consumes ~200ms of single-threaded CPU time just to count braces!
  - Parsing the JSON allocates: raw bytes (6.7 MB) + decoded unicode text (6.7 MB) + parsed JSON dictionary (6.7 MB) + base64 decoded bytes (5 MB) = **>25 MB heap allocation** for a single request.
- **Architectural Resolution**:
  1. **Deprecate Base64 JSON for OCR**: Standardize strictly on **raw binary image POST** with `Content-Type: image/jpeg`, `image/png`, or `image/webp`. This is native to browser `fetch(url, {method: 'POST', body: file})`.
  2. **Route-Aware Body Ingress in `transport.py`**:
     - Check `PATH_INFO` and `CONTENT_TYPE` before reading the body.
     - For `/api/meals/{meal_id}/ocr/extract`:
       - Enforce `CONTENT_LENGTH` exists and is $\le 5,242,880$ (`MAX_IMAGE_BYTES`).
       - Read binary bytes directly from `wsgi.input`.
       - Do **not** invoke `parse_strict_json`.
     - For all other `POST` routes:
       - Retain strict `MAX_BODY_BYTES = 1,048,576` (1 MB) and `parse_strict_json`.

### 2.4 Status Code Mapping Missing in `STATUS_MAP`
- In `settletable.transport.STATUS_MAP`:
  - `'invalid_image'` is missing (defaults to 400, but should be explicitly mapped).
  - `'ocr_unavailable'` is missing. If raised, `STATUS_MAP.get('ocr_unavailable', 400)` will erroneously return **400 Bad Request** instead of **503 Service Unavailable**!
- **Requirement**: Add `'invalid_image': 400` and `'ocr_unavailable': 503` to `STATUS_MAP`.

---

## 3. Malaysian Receipt Domain & Invariants Challenge

### 3.1 Statutory Taxes (SST 6%/8%) & Service Charge (5%/10%)
- **Malaysian Legal Framework**:
  - Under the Sales and Service Tax Act 2018 (amended March 1, 2024), the general service tax increased from 6% to 8%. However, **Food & Beverage (Group B) was explicitly retained at 6%**.
  - F&B dining receipts in Malaysia almost universally charge **6% Service Tax**.
  - Service Charge is a contractual dining fee (typically 10% for full table service, 5% for fast-casual).
  - **Tax on Service Charge**: In Malaysian tax law, Service Tax is levied on the total taxable service value, which includes the service charge:
    $$\text{Taxable Base} = \text{Items Subtotal} + \text{Service Charge}$$
    $$\text{SST} = 6\% \times (\text{Items Subtotal} + \text{Service Charge})$$
- **The Spec's Reconciliation Formula Flaw**:
  SPEC.md Section 2.C checks:
  $$\text{computed\_total} = \text{subtotal\_sen} + \text{tax\_sen} + \text{service\_sen} - \text{discount\_sen} + \text{rounding\_sen}$$
  While this additive check correctly verifies the arithmetic summation of printed slip rows, the parser must understand that `tax_sen` will reflect the compounded tax, not simply $6\% \times \text{subtotal}$.
- **No Fact Invention Rule**: If the tax percentage or service charge amount is omitted or smudged, the parser must set `tax_sen: None` and `service_sen: None`. It must **never** infer a 6% or 10% rate from subtotal.

### 3.2 The BNM 5-Sen Rounding Mechanism & Unprinted Adjustments
- **Bank Negara Malaysia Rules**:
  - The cash rounding mechanism rounds the final payable amount to the nearest 5 sen.
  - Rounding adjustment amounts are mathematically restricted to $\{-2, -1, 0, +1, +2\}$ sen.
  - Any parsed `rounding_sen` whose absolute value is $> 2$ sen indicates an OCR token misread or a different fee, and must trigger `candidate_receipt_mismatch`.
- **The Kechara Historical Scan Hazard (Unprinted Rounding)**:
  - In `research/phase-1/ocr-validation.md:84`:
    *"Kechara's printed components sum 6448 but final is 6450 without a printed rounding row; do not fabricate a 2-sen adjustment. These are specific review triggers, not tolerance exceptions."*
  - If a receipt has items + tax summing to 6448 sen and a printed total of 6450 sen, but **no printed rounding row**, the parser must NOT invent a `rounding_sen = 2`.
  - Instead, `rounding_sen` remains `None`, `discrepancy_sen = 2`, and the proposal routes strictly to `route: "manual_correction"`. The organizer then decides whether to add a rounding adjustment.

### 3.3 Tax-Inclusive vs. Tax-Exclusive Line Items (The Wan Sheng Defect)
- **The Problem**:
  In Malaysian tax-inclusive dining receipts (such as the Wan Sheng real scan from the research corpus):
  - Line items are printed at gross prices: Milo (B) 5.60, Take Away 0.40. Sum of items = **600 sen**.
  - The receipt prints a summary line: `"SUBTOTAL: 5.66"`, followed by `"GST 6%: 0.34"`, and `"TOTAL: 6.00"`.
  - The printed "SUBTOTAL" represents the net pre-tax figure, NOT the sum of the line items.
- **The Domain Invariant Conflict**:
  - In `settletable.calculation.calculate(meal)`:
    ```python
    item_subtotal = sum(item.line_sen for item in meal.items)
    if item_subtotal != meal.subtotal_sen:
        raise CalculationError("subtotal_mismatch", "subtotal_sen")
    ```
  - SettleTable's calculation engine defines `subtotal_sen` as the exact sum of line item amounts (`600 sen`).
  - If the candidate proposal extracts `subtotal_sen = 566` from the slip's "SUBTOTAL" label, then when the organizer accepts the draft, the authority will throw `CalculationError("subtotal_mismatch")`!
- **Remediation**:
  The specification must distinguish:
  - `items_subtotal_sen`: Always the sum of line items ($600$).
  - `printed_net_subtotal_sen`: The raw slip value printed beside "Subtotal" ($566$).
  - `tax_included`: `True`.
  - In `CandidateReceipt`, `subtotal_sen` must equal `items_subtotal_sen` ($600$), with `tax_sen = 34` and `tax_included = True`, matching `Receipt.included_tax_sen` in `settletable.authority.Receipt`.

### 3.4 Data Model Alignment with SettleTable Authority & Calculation
The schema in SPEC.md Section 3 diverges from the established domain model in `settletable.calculation` and `settletable.authority`:

| SPEC.md Draft (`CandidateAdjustment` / `CandidateItem`) | SettleTable Domain Model (`calculation.py` & `authority.py`) | Defect / Failure Mode |
|---|---|---|
| `kind: "service_charge"` | `kind in ("tax", "service", "discount", "rounding")` | `CalculationError("adjustment_kind")` on apply |
| `amount_sen: int` (positive for discount) | Discount `amount_sen < 0` strictly required (`calculation.py:225`) | `CalculationError("adjustment_sign")` on apply |
| `eligible_item_ids: tuple[str, ...]` (non-null) | `eligible_item_ids: tuple[str, ...] \| None` (empty tuple fails `collection_bound`) | `CalculationError("collection_bound")` on apply |
| Lacks `label: str` and `rationale: str` | `ReceiptAdjustment(id, label, kind, amount_sen, eligible_item_ids, rationale)` | Cannot map candidate to `ReceiptAdjustment` |
| `CandidateItem.name: str` | `ReceiptItem.label: str` | Unnecessary field renaming across layers |
| Lacks `included_tax_sen: int \| None` | `Receipt.included_tax_sen: int \| None` | Missing integer field required by `Receipt` |

---

## 4. Security & Authority Integrity Challenge

### 4.1 Organizer Authorization & Diner Denial of Service
- **Requirement**: `POST /api/meals/{meal_id}/ocr/extract` must be restricted strictly to the meal organizer.
- **Enforcement Mechanism**:
  ```python
  part_id, is_org = authority.authenticate(active_cred, meal_id)
  if not is_org:
      raise TransportError('forbidden', 403)
  ```
- **Security Rationale**:
  - In SettleTable, diners have read access to the meal and write access only to their own claimed quantities (`SetOwnQuantity`). Receipt definition (`ReplaceReceipt`, `ReviewReceipt`) belongs solely to the organizer.
  - OCR inference is CPU-intensive (ONNX Runtime intra-op threads). Allowing non-organizer diners or unauthenticated callers to submit OCR requests creates a high-impact DoS vector where any invited participant could saturate server CPU cores with concurrent image uploads.

### 4.2 CSRF Defense & Custom Headers
- **Mandatory Custom Header**: `X-SettleTable-Action: 1` must be enforced on `POST /ocr/extract`.
- **Origin Validation**:
  - For browser clients authenticating via `settletable_session` cookie:
    - Transport must enforce `Origin` header validation against `server_origin`.
    - If `Origin` is missing or null, fallback to `Referer` origin check. If both are missing or mismatched: HTTP 403 `origin_mismatch`.
  - For programmatic clients authenticating via `Authorization: Bearer <token>`:
    - Origin checking is bypassed, but `X-SettleTable-Action: 1` remains strictly required.

### 4.3 Zero Authority State & SQLite Mutation Guarantee
- **The Guarantee**: Calling `POST /ocr/extract` must result in **zero changes** to database state:
  - Zero rows inserted or updated in `meals`, `participants`, `sessions`, `invitations`, or `audit_log`.
  - `meal.revision` and `meal.financial_revision` must remain identical.
  - Active transaction isolation: `authority.authenticate()` executes a read-only query within a transaction. The OCR endpoint must never open a write transaction.
- **Verification Requirement**: The test suite must assert SQLite database hash identity and table row counts before and after extraction requests.

### 4.4 Zero Cloud Fallback & Air-Gap Enforcement
- **Non-Negotiable**: No external cloud calls (AWS Textract, Google Cloud Vision, Azure, OpenAI, Anthropic).
- **Failure Mode Handling**:
  - If `RapidOCR` is not installed or ONNX model fails to load: HTTP 503 `ocr_unavailable`.
  - The UI must cleanly transition to manual organizer entry. It must **never** offer or execute a cloud fallback.
- **Adversarial Test Verification**:
  - In test suites, tests must mock/intercept socket creation (`socket.socket.connect`) and assert that **zero outbound network connections** are attempted during image extraction.

---

## 5. Test Strategy & CI Portability Challenge

### 5.1 CI Portability without Native Heavy Wheels
- **The Issue**: Native ONNX Runtime and RapidOCR wheels are large (several hundred megabytes), have native C/C++ compilation constraints, and may not install cleanly across all host/CI environments (e.g. musl Linux, Python 3.14).
- **The Architecture Solution**:
  - Protocol abstraction: Define `OcrEngine(Protocol)`.
  - Dependency Injection: `SettleTableApp` must accept an optional `ocr_engine: OcrEngine | None` parameter during initialization.
  - Standard CI runs: Execute against `MockOcrEngine`, which replays pre-recorded token fixtures in pure Python with zero native library dependencies.
  - Dedicated ML test job: An optional, explicit CI matrix job installs `rapidocr-onnxruntime` and executes end-to-end inference against synthetic test assets.

### 5.2 Test Asset Provenance & Clearance Constraints
- **The Finding**: As established in `research/phase-1/ocr-validation.md:3` and `research/phase-1/experiments/ocr/README.md:11`, the 6 historical Malaysian dining scans (from SROIE) have unconfirmed redistribution rights and **remain withheld from Git**.
- **Impact on SPEC.md**: SPEC.md Section 7.1 states: *"Test against all 10 permitted test assets (4 synthetic layouts + 6 historical Malaysian dining scans)"*. If tests expect to find raw JPG files for the 6 SROIE receipts in `tests/fixtures/`, tests on a clean clone will fail!
- **Remediation**:
  1. Store the OCR token outputs of the 10 assets as **JSON token fixtures** (`tests/fixtures/ocr/*.tokens.json`). These JSON fixtures contain only bounding boxes, confidence scores, and extracted strings, avoiding copyright issues.
  2. For end-to-end image wire testing, check in **4 programmatically generated synthetic receipt images** created via Pillow (clean, blurred, skewed, modifier-heavy).

### 5.3 Actionable Test Scenarios

The test suite must implement the following deterministic test scenarios:

1. **Wire Boundary Tests**:
   - `test_ocr_rejects_payload_over_5mb`: Send 5,242,881 bytes -> HTTP 413 `payload_too_large`.
   - `test_ocr_rejects_missing_content_length`: Send POST without Content-Length -> HTTP 411 `missing_content_length`.
   - `test_ocr_rejects_non_image_magic_bytes`: Upload SVG, HTML, and binary garbage -> HTTP 400 `invalid_image`.
   - `test_ocr_rejects_content_type_mismatch`: Send JPEG bytes with `Content-Type: image/png` -> HTTP 400 `invalid_image`.
   - `test_ocr_rejects_dimension_bomb`: Submit valid PNG header with $20000 \times 20000$ dimensions -> HTTP 400 `invalid_image`.
2. **Security & Authorization Tests**:
   - `test_ocr_requires_organizer`: Request with valid diner credential -> HTTP 403 `forbidden`.
   - `test_ocr_rejects_unauthenticated`: Request with invalid/missing session -> HTTP 401 `invalid_session`.
   - `test_ocr_enforces_csrf_action_header`: POST without `X-SettleTable-Action: 1` -> HTTP 400 `missing_action_header`.
   - `test_ocr_enforces_csrf_origin_for_cookies`: POST with cookie and mismatched Origin -> HTTP 403 `origin_mismatch`.
   - `test_ocr_guarantees_zero_state_mutation`: Capture DB hash, meal revision, and row counts before and after OCR; verify exact identity.
   - `test_ocr_air_gap_zero_outbound_sockets`: Mock socket connection; verify zero network attempts.
3. **Malaysian Domain Parser Tests**:
   - `test_parse_tax_inclusive_receipt`: Parse Wan Sheng tokens; verify `subtotal_sen == sum(items) == 600`, `tax_sen == 34`, `tax_included == True`, `reconciled == True`.
   - `test_parse_tax_exclusive_receipt`: Parse subtotal 10000, SST 600, service 1000, total 11600; verify exact matching.
   - `test_parse_bnm_rounding_adjustment`: Verify rounding values $\in \{-2, -1, 0, +1, +2\}$ sen; verify out-of-bound rounding flags issue.
   - `test_parse_unprinted_rounding_flagged`: Parse Kechara tokens (items sum 6448, total 6450, no rounding row); assert `rounding_sen is None`, `discrepancy_sen == 2`, `route == "manual_correction"`.
   - `test_parse_rejects_discount_over_base`: Candidate with discount exceeding subtotal flags issue.
4. **Engine & Fallback Tests**:
   - `test_ocr_unavailable_returns_503`: When engine is `None` or raises `OcrUnavailableError` -> HTTP 503 `ocr_unavailable`.
   - `test_mock_engine_replay`: Verify `MockOcrEngine` deterministically yields configured `OcrLine` tokens.

---

## 6. Remediation Checklist for SPEC.md

Before proceeding to implementation, update `.scratch/local-ocr/SPEC.md` with the following changes:

- [ ] **Section 2.C**: Clarify that for tax-inclusive receipts, `subtotal_sen` in `CandidateReceipt` represents the sum of line items (`items_subtotal_sen`), and `tax_sen` represents the included tax amount (`included_tax_sen`), avoiding the `subtotal_mismatch` domain conflict.
- [ ] **Section 2.B**: Clarify that BNM rounding adjustments are strictly $\pm 1$ or $\pm 2$ sen, and that unprinted rounding discrepancies must NEVER be synthesized as fake rounding items.
- [ ] **Section 3 (`CandidateAdjustment`)**:
  - Rename `kind: "service_charge"` to `kind: "service"`.
  - Specify `amount_sen` for discounts as negative sen to match `settletable.calculation`.
  - Change `eligible_item_ids: tuple[str, ...] | None` (nullable).
  - Add `label: str` and `rationale: str` fields to enable direct mapping to `ReceiptAdjustment`.
- [ ] **Section 3 (`CandidateItem`)**: Rename `name` to `label` for consistency with `settletable.authority.ReceiptItem`.
- [ ] **Section 5 (Transport & Wire)**:
  - Deprecate/remove Base64 JSON support; standardize on raw binary image POST with `Content-Type: image/jpeg`, `image/png`, or `image/webp`.
  - Document the requirement to add `'invalid_image': 400` and `'ocr_unavailable': 503` to `settletable.transport.STATUS_MAP`.
  - Specify maximum image dimensions: `MAX_IMAGE_WIDTH = 4096`, `MAX_IMAGE_HEIGHT = 4096`, `MAX_IMAGE_PIXELS = 16_777_216`.
  - Specify exact byte slice definitions for magic bytes validation.
- [ ] **Section 4 & 7 (Testing & CI)**:
  - Specify that `SettleTableApp` accepts an injectable `ocr_engine: OcrEngine | None`.
  - Clarify that CI tests rely on JSON token fixtures and 4 cleared synthetic images, not withheld raw SROIE scans.
