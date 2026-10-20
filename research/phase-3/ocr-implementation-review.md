# Independent Security & Code Review: SettleTable Bounded Local OCR Pipeline (PR #10)

**Target PR / Branch**: PR #10 (`feature/local-ocr-pipeline`, head commit `fb313e53ec0fb931021d859231d2a70a3173d6ed`)  
**Target Codebase**: `C:\LKY_Project\TabWise`  
**Reviewer**: Independent Security & Code Reviewer  
**Overall Determination**: **CONDITIONAL PASS (REMEDIATE WIRE INGRESS CONTENT-TYPE CHECK BEFORE MERGE)**  
**Target Document**: `C:\LKY_Project\TabWise\research\phase-3\ocr-implementation-review.md`

---

## 1. Executive Summary

An independent, objective security and architectural review has been performed on PR #10 (commit `fb313e5`). PR #10 introduces a self-hosted, CPU-bounded local receipt OCR pipeline and wire transport endpoint (`POST /api/meals/{meal_id}/ocr/extract`) for Malaysian dining receipts.

### Key Strengths & Compliant Areas:
1. **Air-Gapped & Strictly Local**: OCR inference executes solely on local CPU (`RapidOcrEngine` / ONNX Runtime). Zero external cloud fallback or network calls. Air-gap test verifies 0 outbound sockets.
2. **Decompression Bomb Protection**: Image dimensions (width, height, total pixels) are parsed directly from raw binary headers (PNG IHDR, JPEG SOF markers, WebP VP8/VP8L/VP8X) and strictly bounded (`<= 4096 x 4096`, `<= 16 MP`) *before* raster decoding.
3. **Malaysian Receipt Invariants**:
   - **The Wan Sheng Rule**: In tax-inclusive receipts, `subtotal_sen` matches `sum(line_items)` (e.g. 600 sen) and `included_tax_sen` is set (34 sen), preserving the critical calculation engine invariant (`item_subtotal == subtotal_sen`).
   - **Statutory Taxes & Adjustments**: SST/GST, service charge, negative discount sen, and BNM rounding (`[-2, +2]` sen) are correctly extracted and categorized.
   - **The Kechara Rule**: Unprinted discrepancies are never fabricated into fake rounding adjustments; missing fields remain `None` and discrepancies route to `"manual_correction"`.
4. **Organizer Authorization & Zero State Mutation**: `POST /ocr/extract` strictly enforces organizer authentication (403 for diners, 401 for unauthenticated). Extraction produces zero database mutations (SQLite hash before and after extraction is 100% byte-identical).
5. **Human Verification Invariant**: Extracted candidates are strictly advisory. The organizer must review draft items, confirm the verification checkbox, and seal the receipt before finalization can proceed.
6. **CI Portability & Test Pass Rate**: 100% of the 135 Python tests pass cleanly without ONNX runtime dependencies via `MockOcrEngine`. The real Headless Chrome CDP browser test passes all 8 stages in 3.2s.
7. **Financial Engine Untouched**: `settletable/calculation.py` is completely untouched. Cryptographic hash domains remain intact.

### Critical Defect Requiring Remediation (Condition for Merge):
- **Wire Endpoint Content-Type vs. Magic Byte Enforcement Gap (`settletable/transport.py:593-601`)**:
  While `settletable.ocr.engine.validate_image_payload` correctly implements a `content_type_mismatch` check, `settletable/transport.py` verifies only that `Content-Type` is in `('image/jpeg', 'image/png', 'image/webp', 'image/jpg')` and **never passes `ct` to `validate_image_payload` or `engine.recognize()`**.
  Consequently, posting a PNG image with `Content-Type: image/jpeg` bypasses MIME validation and returns `HTTP 200 OK` instead of `HTTP 400 invalid_image`. `tests/test_ocr.py` only tested this check in a direct unit test (`TestImageHeaderValidation`), omitting an integration test on the HTTP transport route.

---

## 2. Audit Gate Summary

| Gate | Description | Status | Findings & Exact Line Citations |
|---|---|---|---|
| **Gate 1** | Local-Only & Zero Cloud Fallback | **PASS** | `settletable/ocr/engine.py:161-189`<br>`settletable/transport.py:228-233, 609-611`<br>`tests/test_ocr.py:391-400`<br>Pure CPU execution on ONNX Runtime. No cloud fallback. Missing engine raises `OcrUnavailableError` -> HTTP 503 `ocr_unavailable`. Outbound network sockets strictly mocked/blocked (0 connections). |
| **Gate 2** | Safe Binary Ingress & Decompression Protection | **CONDITIONAL** | `settletable/transport.py:384, 393-406, 593-601`<br>`settletable/ocr/engine.py:8-12, 27-84, 86-131`<br>`tests/test_ocr.py:43-98`<br>Route-aware ingress bypasses `parse_strict_json` for `/ocr/extract`. 5 MB limit enforced (HTTP 413). Dimension headers parsed without raster bitmap decompression (`<= 4096 x 4096`, `<= 16 MP`).<br>**DEFECT**: `ct` is not passed to `validate_image_payload` in `transport.py:600`, allowing MIME/magic byte mismatches on the wire. |
| **Gate 3** | Malaysian Receipt Domain & Invariants | **PASS** | `settletable/ocr/parser.py:19-30, 251-263, 279-321, 326-327, 342-349`<br>`tests/test_ocr.py:107-175`<br>Wan Sheng rule verified (`subtotal_sen == 600`, `included_tax_sen == 34`, `adjustments == ()`). Discounts are strictly negative sen. BNM rounding bounded to `[-2, +2]`. Kechara unprinted rounding discrepancy preserved (`rounding_sen is None`, `discrepancy_sen == 2`, `route == "manual_correction"`). |
| **Gate 4** | Organizer Authorization & Zero State Mutation | **PASS** | `settletable/transport.py:586-591`<br>`settletable/static/app.js:568-582, 870-884, 911-937`<br>`tests/test_ocr.py:272-290, 373-390`<br>Non-organizer diners rejected with 403 `forbidden`. Unauthenticated callers rejected with 401 `invalid_session`. SQLite DB SHA-256 is 100% byte-identical before and after OCR call. Mandatory human review checkbox preserved. |
| **Gate 5** | Deterministic CI Portability & Test Coverage | **PASS** | `tests/test_ocr.py:1-404`<br>`tools/e2e_browser_test.mjs:1-463`<br>Ran 135 tests in 74.270s: 100% OK. `MockOcrEngine` uses pure-Python token replay from `tokens.json`. Chrome CDP browser test passes all 8 vertical user journey stages in 3.2s. |
| **Gate 6** | Financial Invariants | **PASS** | `settletable/calculation.py:1-269`<br>`settletable/authority.py:232, 239, 314, 321`<br>`settletable/calculation.py` is completely untouched. Cryptographic hash domains (`settletable-receipt-v1`, `settletable-local-session-v1`, `settletable-invitation-v1`, `settletable-command-v1`) are 100% intact. |

---

## 3. Detailed Audit Findings & Exact Citations

### 3.1 Gate 1: Local-Only & Zero Cloud Fallback (PASS)
- **Engine Protocol & Implementations**:
  - `settletable/ocr/engine.py:134-140` defines `OcrEngine(Protocol)`.
  - `settletable/ocr/engine.py:161-189` defines `RapidOcrEngine`, configured strictly for local CPU inference:
    ```python
    167: self._engine = RapidOCR(params={
    168:     "EngineConfig.onnxruntime.intra_op_num_threads": num_threads,
    169:     "EngineConfig.onnxruntime.inter_op_num_threads": 1,
    170: })
    ```
- **Zero Cloud Fallback**:
  - No external HTTP clients, SDKs (AWS Textract, Google Cloud Vision, Azure, OpenAI), or external API endpoints exist in the package.
  - If `RapidOCR` is missing or fails to initialize, `OcrUnavailableError` is raised (engine.py:172, 174).
- **Transport Error Mapping**:
  - `settletable/transport.py:85` explicitly maps `'ocr_unavailable': 503` in `STATUS_MAP`.
  - In `settletable/transport.py:228-233`:
    ```python
    228: try:
    229:     from settletable.ocr import RapidOcrEngine
    230:     return RapidOcrEngine()
    231: except Exception:
    232:     raise TransportError('ocr_unavailable', 503)
    ```
  - In `settletable/transport.py:609-610`: catches `OcrUnavailableError` and maps to `TransportError('ocr_unavailable', 503)`.
  - Returns `503 Service Unavailable` with `Retry-After: 1` header (`transport.py:290`).
- **Frontend Fallback**:
  - `settletable/static/app.js:895-896` handles 503 gracefully:
    `showAlert('Local OCR engine unavailable. Please enter items manually.', 'error');`
  - Zero prompt or suggestion to upload to any cloud service.
- **Air-Gap Verification**:
  - `tests/test_ocr.py:391-400` intercepts `socket.socket.connect` with a `RuntimeError` patch; verifies extraction succeeds without opening any network sockets.

---

### 3.2 Gate 2: Safe Binary Ingress & Decompression Protection (CONDITIONAL PASS)
- **Route-Aware Binary Ingress**:
  - `settletable/transport.py:384` detects the route before reading the request body:
    ```python
    384: is_ocr_extract = bool(method == 'POST' and re.fullmatch(r'/api/meals/[A-Za-z0-9_-]+/ocr/extract', path))
    ```
  - `settletable/transport.py:393-395` enforces `MAX_IMAGE_BYTES = 5_242_880` (5 MB) for OCR, while retaining `MAX_BODY_BYTES = 1_048_576` (1 MB) for JSON endpoints. Exceeding 5 MB raises `TransportError('payload_too_large', 413)`.
  - `settletable/transport.py:402-406` stores raw binary in `raw_image_body` and explicitly **bypasses** `parse_strict_json`:
    ```python
    402: if is_ocr_extract:
    403:     raw_image_body = raw_body
    404: else:
    405:     body_data = parse_strict_json(raw_body) if raw_body else {}
    ```
- **Decompression Bomb Protection**:
  - In `settletable/ocr/engine.py:27-84`, `parse_image_dimensions` inspects raw binary headers:
    - PNG: IHDR chunk offset 16–24 (`struct.unpack('>II', data[16:24])`).
    - JPEG: Traverses segment markers searching for SOF0–SOF15 without decoding MCU raster data.
    - WebP: Inspects VP8, VP8L, and VP8X chunks for canvas dimensions.
  - In `settletable/ocr/engine.py:126-130`:
    ```python
    126: if width <= 0 or height <= 0:
    127:     raise InvalidImageError('invalid_dimensions')
    128: if width > MAX_IMAGE_WIDTH or height > MAX_IMAGE_HEIGHT or (width * height) > MAX_IMAGE_PIXELS:
    129:     raise InvalidImageError('image_dimensions_too_large')
    ```
    Bounds `MAX_IMAGE_WIDTH = 4096`, `MAX_IMAGE_HEIGHT = 4096`, `MAX_IMAGE_PIXELS = 16_777_216` (16 MP).
  - Tested in `tests/test_ocr.py:92-97` with a $20,000 \times 20,000$ (400 MP) header.
- **Critical Defect — Wire Content-Type vs Magic Bytes Disconnect**:
  - In `settletable/transport.py:593-601`:
    ```python
    593: ct = environ.get('CONTENT_TYPE', '').split(';')[0].strip().lower()
    594: if ct not in ('image/jpeg', 'image/png', 'image/webp', 'image/jpg'):
    595:     raise TransportError('invalid_image', 400)
    596:
    597: engine = self.get_ocr_engine()
    598: try:
    599:     from settletable.ocr import parse_malaysian_receipt, OcrUnavailableError, InvalidImageError
    600:     lines = engine.recognize(raw_image_body or b'')
    ```
    `ct` is validated against allowed MIME types, but is **never passed** to `validate_image_payload(data, expected_mime=ct)` or `engine.recognize()`.
  - In `settletable/ocr/engine.py:153` (`MockOcrEngine`) and `line 177` (`RapidOcrEngine`):
    `validate_image_payload(image_bytes)` is called with `expected_mime=None`.
  - When `expected_mime` is `None`, lines 107–117 in `engine.py` are skipped entirely.
  - **Empirical Proof**: Sending PNG image bytes with `Content-Type: image/jpeg` to `POST /api/meals/m1/ocr/extract` returns `Status: 200 OK`.
  - **Remediation**:
    In `settletable/transport.py`:
    ```python
    from settletable.ocr import validate_image_payload
    validate_image_payload(raw_image_body or b'', expected_mime=ct)
    ```
    Or pass `expected_mime` to `engine.recognize(raw_image_body or b'', expected_mime=ct)`. Add an integration test in `TestOcrTransportIntegration` verifying that sending PNG bytes with `Content-Type: image/jpeg` produces HTTP 400 `invalid_image`.

---

### 3.3 Gate 3: Malaysian Receipt Domain & Invariants (PASS)
- **The Wan Sheng Rule (Tax-Inclusive Pricing)**:
  - In `settletable/ocr/parser.py:254-263`:
    ```python
    254: if tax_included:
    255:     # Wan Sheng rule: subtotal_sen must match sum(line items).
    256:     subtotal_sen = computed_items_subtotal
    257:     if printed_subtotal_sen is not None and printed_subtotal_sen != computed_items_subtotal:
    258:         printed_net_subtotal_sen = printed_subtotal_sen
    259:     included_tax_sen = tax_sen
    260: else:
    261:     subtotal_sen = printed_subtotal_sen if printed_subtotal_sen is not None else computed_items_subtotal
    262:     included_tax_sen = None
    ```
  - For tax-inclusive receipts (`X51008030563.jpg`), items Milo (5.60) + Take Away (0.40) sum to 600 sen.
  - `subtotal_sen` is set to 600 sen (matching line items sum), preserving `settletable.calculation.calculate()` line 201: `if item_subtotal != meal.subtotal_sen: raise CalculationError("subtotal_mismatch")`.
  - `included_tax_sen` is set to 34 sen, `printed_net_subtotal_sen` to 566 sen.
  - No additive tax adjustment is generated (`len(candidate.adjustments) == 0`).
  - `reconciled` is `True`, `discrepancy_sen = 0`, `route = "human_verification"`.
- **Tax-Exclusive & Statutory Adjustments**:
  - `tax_sen`: added as `CandidateAdjustment(kind="tax", amount_sen=tax_sen)` (parser.py:283-290).
  - `service_sen`: added as `CandidateAdjustment(kind="service", amount_sen=service_sen)` (parser.py:293-300).
  - `discount_sen`: added as `CandidateAdjustment(kind="discount", amount_sen=-abs(discount_sen))` (parser.py:303-310). Note: Strictly **negative** sen, conforming to `settletable.calculation` line 225.
- **BNM 5-Sen Rounding Mechanism**:
  - `parser.py:312-320`: `CandidateAdjustment(kind="rounding", amount_sen=rounding_sen)`.
  - `parser.py:326-327`: Enforces that `abs(rounding_sen) <= 2`. If $> 2$, flags `"invalid_rounding_adjustment"`, forcing `route = "manual_correction"`.
- **The Kechara Rule (Zero Fact Invention)**:
  - In `parser.py:161`, `rounding_sen` is populated strictly when an explicit `ROUNDING` line is recognized.
  - For Kechara (`X51006647984.jpg`), items sum to 6448 sen, total is 6450 sen, but no rounding line exists on the slip.
  - `rounding_sen` remains `None`. `discrepancy_sen = 2`. `reconciled = False`.
  - `issues` receives `"candidate_receipt_mismatch"` and `route` is forced to `"manual_correction"` (parser.py:346-349). Zero fake adjustments are fabricated.

---

### 3.4 Gate 4: Organizer Authorization & Zero State Mutation (PASS)
- **Role Enforcement**:
  - In `settletable/transport.py:586-591`:
    ```python
    586: if not active_cred:
    587:     raise TransportError('invalid_session', 401)
    588: meal_id = m_ocr.group(1)
    589: part_id, is_org = authority.authenticate(active_cred, meal_id)
    590: if not is_org:
    591:     raise TransportError('forbidden', 403)
    ```
  - Unauthenticated requests: HTTP 401 `invalid_session`.
  - Diner requests: HTTP 403 `forbidden`.
  - Organizer requests: HTTP 200 OK.
  - Tested in `tests/test_ocr.py:272-290`.
- **Zero State Mutation**:
  - `authority.authenticate()` executes a read-only SQLite query.
  - The OCR pipeline executes entirely in-memory and never calls mutating methods (`authority.apply`, etc.).
  - `tests/test_ocr.py:373-390` verifies that the SQLite database file SHA-256 hash is byte-for-byte identical before and after `POST /ocr/extract`.
- **Mandatory Human Verification in UI**:
  - In `settletable/static/app.js:870-884`, successful OCR extraction populates candidate items into draft state via `ReplaceReceipt`.
  - In `settletable/static/app.js:573-581`, the receipt card displays:
    `"I confirm totals match the physical bill."` (`review-confirm-check`)
  - The `"Approve & Seal Receipt"` button (`review-submit-btn`) is disabled until the organizer manually ticks the checkbox.
  - Sealing computes the cryptographic receipt digest (`ReviewReceipt`).
  - Finalization is blocked until `reviewConfirmed && issues.length === 0` (`app.js:456, 477`).

---

### 3.5 Gate 5: Deterministic CI Portability & Test Coverage (PASS)
- **CI Dependency Free Replay**:
  - `MockOcrEngine` (`settletable/ocr/engine.py:142-159`) loads pre-recorded tokens from `tests/fixtures/ocr/tokens.json`.
  - Runs in pure Python without ONNX Runtime, OpenCV, or native C wheels.
  - `tests/test_ocr.py` executes 22 tests covering validation, parsing, authorization, and transport in 0.30s.
- **Full Test Suite Execution**:
  - `python -m unittest discover tests`: Ran 135 tests in 74.270s, result: `OK` (100% passing).
- **Chrome CDP Browser Test**:
  - `node tools/e2e_browser_test.mjs`:
    - Spawns isolated Headless Chrome instances for Alice (Organizer) and Bob (Diner).
    - Executes all 8 stages: room creation, receipt entry, review, invite generation, unauthenticated landing inspection, invite redemption, claim overlapping, 409 conflict resolution, finalization, and reload persistence.
    - All 8 stages passed with code 0 in 3.2s.

---

### 3.6 Gate 6: Financial Invariants (PASS)
- **Production Code Isolation**:
  - `git diff fb313e5~1..fb313e5 settletable/calculation.py` is empty.
  - `settletable/calculation.py` was not modified in PR #10.
- **Cryptographic Hash Domains**:
  - `b'settletable-receipt-v1\0'` (`authority.py:314`)
  - `b'settletable-local-session-v1\0'` (`authority.py:232`)
  - `b'settletable-invitation-v1\0'` (`authority.py:239`)
  - `'contract': 'settletable-command-v1'` (`authority.py:321`)
  - All versioned prefix domains remain intact and unchanged.

---

## 4. Secondary Code Polish Items

1. **`eligible_item_ids` Safe Unpacking (`settletable/transport.py:654`)**:
   `tuple(adj.get('eligible_item_ids', ()))` raises `TypeError` if `eligible_item_ids` is `None` (since `None` is returned by `.get()` when the key exists with `null` value).
   Change to: `tuple(adj.get('eligible_item_ids') or ())`.
2. **Residual JavaScript Identifier in Python (`settletable/ocr/parser.py:28`)**:
   `frac = int(parts[1].padend(2, "0") if hasattr(parts[1], "padend") else parts[1].ljust(2, "0")[:2])`
   Clean up to: `frac = int(parts[1].ljust(2, "0")[:2])`.
3. **Frontend MIME Fallback (`settletable/static/app.js:854`)**:
   `headers: { 'Content-Type': file.type || 'image/jpeg' }`
   If `file.type` is blank on a PNG/WebP file, defaulting to `'image/jpeg'` will trigger a mismatch error once Gate 2 remediation is applied. Detect MIME by filename extension if `file.type` is empty.

---

## 5. Formal Recommendation & Action Items

**Determination: CONDITIONAL PASS**

PR #10 is architecturally clean, robustly isolated, and domain-accurate. It can be merged upon applying the following 2-step remediation:

### Action Items Before Merge:
1. **Remediate Transport Wire Validation**:
   In `settletable/transport.py:600`, pass `ct` to `validate_image_payload` prior to engine recognition:
   ```python
   from settletable.ocr import validate_image_payload
   validate_image_payload(raw_image_body or b'', expected_mime=ct)
   ```
2. **Add Missing HTTP Transport Mismatch Test**:
   In `tests/test_ocr.py` under `TestOcrTransportIntegration`:
   ```python
   def test_content_type_mismatch_rejected_400(self):
       headers = {
           'Authorization': f'Bearer {self.org_cred}',
           'X-SettleTable-Action': '1',
           'Content-Type': 'image/jpeg',
       }
       # Send PNG bytes with image/jpeg header
       code, _, body = self._call('POST', '/api/meals/meal-ocr-test/ocr/extract', headers, self.valid_png_bytes)
       self.assertEqual(code, 400)
       data = json.loads(body.decode('utf-8'))
       self.assertEqual(data['error'], 'invalid_image')
   ```
