# Bounded Local OCR Pipeline Specification

**Version**: 1.1.0  
**Phase**: Phase 3 — Bounded Local OCR Implementation  
**Status**: APPROVED POST-CHALLENGE  
**Authority**: Orchestrator Governance  
**Challenge Reference**: `research/phase-3/ocr-architecture-challenge.md` (CONDITIONAL PASS Remediated)  

---

## 1. Overview & Architectural Boundaries

SettleTable's core mission is deterministic, transparent, cent-conserving bill settlement for dining groups. In Phase 3, following the acceptance of the manual-first browser MVP, this slice introduces **local/self-hosted receipt OCR** to extract item names, quantities, line totals, subtotal, Malaysian statutory taxes, service charges, discounts, and rounding adjustments from receipt photos.

### Mandatory Non-Negotiables:
1. **Local / Self-Hosted Only**: All image processing and OCR inference occurs on the local host / server. Zero cloud calls (no OpenAI, Google Cloud Vision, AWS Textract, Claude, Azure).
2. **Never Cloud Fallback**: If local OCR is unavailable, ambiguous, or low-confidence, execution routes strictly to **manual organizer correction / verification**. Cloud fallback is strictly prohibited.
3. **Advisory Proposal (Never Direct Mutation)**: The OCR endpoint `POST /api/meals/{meal_id}/ocr/extract` generates a candidate receipt proposal (`CandidateReceipt`). It **never** mutates the authoritative meal state or writes to SQLite directly.
4. **Mandatory Human Verification**: Extracted facts are displayed in the Organizer's UI for review and editing. The organizer must physically check the paper/electronic receipt, verify totals, and submit `ReplaceReceipt` followed by `ReviewReceipt`.
5. **No Fact Invention**: Unknown or unprinted fields remain `None`. Never fabricate missing charges, never invent unprinted rounding rows, and never treat unreadable items as zero sen.
6. **Decoupled Live Collaboration**: Live meal collaboration and manual entry continue to function completely independently of OCR engine availability.

---

## 2. Malaysian Dining Receipt Domain & Invariants

Receipts from Malaysian food and beverage establishments reflect statutory requirements under the Sales and Service Tax Act 2018 (SST) and Bank Negara Malaysia (BNM) currency conventions:

### A. Currency & Units
- All monetary amounts are parsed and stored as integer **sen** (1 MYR = 100 sen).
- Negative values represent discounts or downward rounding adjustments.

### B. Charges & Adjustments
1. **Items Subtotal (`subtotal_sen`)**: Sum of all line item amounts (`sum(item.line_sen)`).
2. **Service Tax / SST (`tax_sen`)**: Statutorily 6% on F&B dining under SST 2018 (Group B).
3. **Service Charge (`service_sen`)**: Contractual dining service fee (typically 5% or 10%, labeled `SVC CHG` or `SERVICE CHARGE`). In Malaysian accounting, SST is often calculated on the combined base: $\text{SST} = 6\% \times (\text{Subtotal} + \text{Service Charge})$.
4. **Discounts / Vouchers (`discount_sen`)**: Promotional discounts or member vouchers. In SettleTable domain models (`calculation.py`), discounts must be stored with a **negative** `amount_sen`.
5. **Rounding Adjustment (`rounding_sen`)**: Bank Negara Malaysia 5-sen rounding mechanism for cash / final bills. Strictly restricted to $\{-2, -1, 0, +1, +2\}$ sen. Any parsed rounding $> 2$ sen indicates an OCR misread and flags an issue.
6. **Unprinted Adjustments Rule**: If a receipt components sum differs from the printed total but has **no printed rounding row** (e.g. historical Kechara scan where items sum to 6448 sen and total is 6450 sen), the parser must NOT invent a 2-sen rounding adjustment. `rounding_sen` remains `None`, `discrepancy_sen = 2`, and `route` is forced to `"manual_correction"`.
7. **Grand Total (`total_sen`)**: Final billed amount.

### C. Tax-Inclusive vs. Tax-Exclusive Line Items (The Wan Sheng Rule)
- Receipts labeled `INCLUSIVE OF 6% SST`, `TAX INCL`, or `INCLUSIVE OF GST`:
  - Line items are printed at gross prices (e.g. Wan Sheng items sum to 600 sen).
  - The slip prints a pre-tax summary `"SUBTOTAL: 5.66"`, `"GST: 0.34"`, `"TOTAL: 6.00"`.
  - In `CandidateReceipt`, `subtotal_sen` must equal the exact sum of line items (**600 sen**) to preserve SettleTable's invariant in `settletable.calculation`: `item_subtotal == meal.subtotal_sen`.
  - `included_tax_sen` is set to **34 sen**, `tax_included` is `True`, and no external additive tax adjustment is generated.
  - The pre-tax printed value is preserved in `printed_net_subtotal_sen = 566` for advisory reference.
- Receipts labeled `EXCLUDING TAX` or adding SST on top:
  - `tax_included` is `False`.
  - An additive `CandidateAdjustment` with `kind: "tax"` and `amount_sen: tax_sen` is generated.
- Hard Reconciliation Formula:
  $$\text{expected\_total} = \text{subtotal\_sen} + \sum_{a \in \text{adjustments}} a.\text{amount\_sen}$$
  $$\text{discrepancy\_sen} = \text{total\_sen} - \text{expected\_total}$$
  If $\text{discrepancy\_sen} \ne 0$, `candidate_receipt_mismatch` is flagged and `route` is set to `"manual_correction"`.

---

## 3. Data Structures

The data models map cleanly to `settletable.calculation` and `settletable.authority`:

### `OcrLine`
```python
@dataclass(frozen=True)
class OcrLine:
    text: str
    score: float  # Confidence score 0.0 - 1.0
    box: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]]
```

### `CandidateItem`
```python
@dataclass(frozen=True)
class CandidateItem:
    id: str  # Generated unique item id, e.g. "item-1"
    label: str  # Cleaned item description (matches ReceiptItem.label)
    quantity: tuple[int, int]  # (numerator, denominator), e.g. (1, 1) or (2, 1)
    unit_price_sen: int | None
    line_sen: int
```

### `CandidateAdjustment`
```python
@dataclass(frozen=True)
class CandidateAdjustment:
    id: str  # e.g. "adj-tax-1"
    label: str  # e.g. "SST 6%", "Service Charge 10%", "Rounding"
    kind: str  # Strictly one of: "tax", "service", "discount", "rounding"
    amount_sen: int  # Positive for tax/service/round-up; NEGATIVE for discount/round-down
    eligible_item_ids: tuple[str, ...] | None  # Nullable; None indicates whole receipt
    rationale: str  # e.g. "Extracted from receipt slip"
```

### `CandidateReceipt`
```python
@dataclass(frozen=True)
class CandidateReceipt:
    merchant: str | None
    date: str | None  # ISO format "YYYY-MM-DD"
    time: str | None  # "HH:MM:SS"
    items: tuple[CandidateItem, ...]
    subtotal_sen: int | None  # Exact sum of items
    printed_net_subtotal_sen: int | None  # Printed net subtotal if tax-inclusive
    included_tax_sen: int | None  # Tax already inside line items
    tax_sen: int | None  # Total tax amount
    tax_kind: str | None  # "SST", "GST", "TAX"
    tax_included: bool
    service_sen: int | None
    discount_sen: int | None  # Absolute discount amount
    rounding_sen: int | None
    total_sen: int | None
    adjustments: tuple[CandidateAdjustment, ...]
    reconciled: bool
    discrepancy_sen: int
    mean_confidence: float
    issues: tuple[str, ...]
    route: str  # "human_verification" or "manual_correction"
```

---

## 4. OCR Engine Architecture & Image Ingress Safety

### `OcrEngine` Protocol
```python
class OcrEngine(Protocol):
    def recognize(self, image_bytes: bytes) -> list[OcrLine]:
        ...
```

### Engine Implementations:
1. **`RapidOcrEngine`**:
   - Dynamic wrapper around `rapidocr` library on CPU.
   - Initialized with local ONNX models. Configures thread count (`intra_op_num_threads: 4`).
   - If `rapidocr` is not importable, raises `OcrUnavailableError`.
2. **`MockOcrEngine`**:
   - Test harness engine capable of replaying fixed `list[OcrLine]` from JSON token fixtures or pre-configured token dictionaries.
   - Guarantees 100% deterministic test execution in standard CI environments without native ONNX Runtime dependencies.

### Image Header Validation & Decompression Safety
To prevent decompression bombs and memory exhaustion, image dimensions and magic bytes must be inspected directly from the binary header **before** decoding full bitmaps:
- `MAX_IMAGE_BYTES = 5_242_880` (5 MB).
- `MAX_IMAGE_WIDTH = 4096` pixels.
- `MAX_IMAGE_HEIGHT = 4096` pixels.
- `MAX_IMAGE_PIXELS = 16_777_216` (16 megapixels).
- Magic bytes verification:
  - **JPEG**: `len(b) >= 3 and b[:3] == b'\xff\xd8\xff'`
  - **PNG**: `len(b) >= 8 and b[:8] == b'\x89PNG\r\n\x1a\n'`. Dimension parsed from IHDR chunk at offset 16–24.
  - **WebP**: `len(b) >= 12 and b[:4] == b'RIFF' and b[8:12] == b'WEBP'`.

---

## 5. Wire Transport Interface: `POST /api/meals/{meal_id}/ocr/extract`

### Request Boundary:
- **Method**: `POST`
- **Route**: `/api/meals/{meal_id}/ocr/extract`
- **Headers**:
  - `X-SettleTable-Action: 1` (Mandatory CSRF protection)
  - `Content-Type: image/jpeg` | `image/png` | `image/webp` (Raw binary POST only; Base64 JSON is deprecated/rejected)
  - Cookie: `settletable_session=<cred>` (or `Authorization: Bearer <cred>`)
- **Body**: Raw binary image bytes (up to 5 MB).

### Transport Ingress Architecture in `settletable/transport.py`:
- In `_dispatch()`, route matching for `/api/meals/{meal_id}/ocr/extract` must occur **before** reading request bodies:
  - If route is `POST /ocr/extract`:
    - Enforce `CONTENT_LENGTH` exists and is $\le 5,242,880$.
    - Verify `CONTENT_TYPE` is one of `image/jpeg`, `image/png`, `image/webp`.
    - Read binary bytes directly from `wsgi.input`.
    - Do **not** call `parse_strict_json(raw_body)`!
  - For all other `POST` routes:
    - Retain strict 1 MB limit and `parse_strict_json`.

### Status Codes in `STATUS_MAP`:
- `'invalid_image': 400`
- `'ocr_unavailable': 503`

### Security Gates:
1. **Organizer Authorization**:
   - Caller must possess valid session credentials for the meal.
   - Caller must be the **organizer** (`is_organizer == True`).
   - Diners receive HTTP 403 `forbidden`.
   - Unauthenticated callers receive HTTP 401 `invalid_session`.
2. **Magic Byte Verification**: Payload must match declared `Content-Type`. Non-image files (HTML, SVG, PHP, executables) rejected with HTTP 400 `invalid_image`.
3. **Decompression Bounds**: Images $> 4096 \times 4096$ rejected with HTTP 400 `invalid_image`.
4. **Zero State Mutation**: Database rows, meal revisions, and participant states remain 100% unchanged.
5. **Air-Gap / Zero Network Socket Outbound**: Engine executes strictly local CPU computation with zero external network attempts.

---

## 6. Frontend Integration (`settletable/static/`)

1. **Upload / Scan Control**:
   - In the Organizer's Receipt card, add a file picker and button:
     - `<input type="file" id="receipt-file-input" accept="image/jpeg,image/png,image/webp" capture="environment" style="display:none;">`
     - `<button id="scan-receipt-btn" class="btn btn-secondary">📷 Scan Receipt Image</button>`
2. **Client-Side Flow**:
   - Selecting a photo triggers raw binary `fetch('/api/meals/' + state.mealId + '/ocr/extract', { method: 'POST', headers: { 'Content-Type': file.type, 'X-SettleTable-Action': '1' }, body: file })`.
   - Shows a clean progress spinner: `"Analyzing receipt photo locally..."`.
   - On success:
     - Populates candidate items and adjustments into the draft receipt state.
     - If `route === 'manual_correction'` or issues exist, displays an advisory banner highlighting discrepancies.
     - Enables the organizer to inspect, add, edit, or delete items before physically verifying and sealing the receipt.
3. **Mandatory Human Verification Preserved**:
   - The organizer must still check the review checkbox and click **"Approve & Seal Receipt"**, which executes the cryptographic receipt digest attestation.

---

## 7. Testing & CI Portability Strategy

1. **Pure-Python Deterministic CI Suite**:
   - Unit tests under `tests/test_ocr.py` test image magic byte validation, dimension parsing, Malaysian layout parsing, tax-inclusive Wan Sheng handling, BNM rounding rules, and issue detection using `MockOcrEngine` and JSON token fixtures (`tests/fixtures/ocr/*.tokens.json`).
   - Standard GitHub Actions `ubuntu-24.04` runs 100% of these tests with zero added dependencies and zero native wheel requirements.
2. **Integration & Adversarial Tests**:
   - Diner authorization rejection (403 `forbidden`).
   - Unauthenticated rejection (401 `invalid_session`).
   - Wire limit rejection (>5MB returns 413 `payload_too_large`).
   - Non-image rejection (SVG, HTML, text return 400 `invalid_image`).
   - Decompression bomb header rejection (400 `invalid_image`).
   - Database zero-mutation assertion (SQLite SHA-256 identical before and after extraction).
   - Air-gap assertion: mock socket connection verifies 0 outbound sockets.
3. **End-to-End Image Tests**:
   - 4 synthetic receipt images (`synthetic_clear.png`, `synthetic_faded.png`, `synthetic_perspective.png`, `synthetic_tilt_shadow.png`) in `tests/fixtures/ocr/` test binary image ingestion.
