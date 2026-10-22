# Specification: Notion-Inspired Staged Receipt Editor Polish (Finalized)

## 1. Problem Statement & Root Cause Analysis

The staged OCR candidate editor (`state.ocrCandidate`) is a critical human-in-the-loop verification gate before OCR extractions are committed to the authoritative SQLite receipt state.

Visual inspection and critique identified the following defects:
1. **Quantity Control**: Browser default number spinners overlap the numeric input in narrow 65px cells, causing visual crowding and hard-to-click controls.
2. **Adjustments, Taxes & Discounts Section**: Form fields appear in awkward vertical arrangements with inconsistent sizing, nested card clutter, and excessive whitespace. Viewport-only media queries fail because the container width is at most ~736px even on wide desktop displays.
3. **Receipt Items Layout**: Redundant and crowded unit price column cluttering the authoritative line-total field and squashing item names down to ~280px.
4. **Adjustment Classification Investigation**:
   - Investigation across the OCR parser (`settletable/ocr/parser.py`), mock fixtures (`tools/run_demo.py`, `tests/fixtures/ocr/tokens.json`), and candidate models (`settletable/ocr/models.py`) confirms that the backend parser strictly categorizes `SERVICE CHARGE` -> `kind="service"` and `label="Service Charge"`.
   - The screenshot discrepancy occurred during manual user testing when the category dropdown was switched to `SST / Tax`, leaving the label unchanged as `Service Charge`.
   - We maintain explicit organizer authority: do not silently alter financial data, but if an adjustment label matches a known default ("Service Charge", "SST Tax", "Discount", "Rounding Adjustment"), switching the category will intuitively update the default label placeholder/value.
5. **Visual Hierarchy & Contrast**:
   - Nested cards in the adjustments section violate Impeccable craft floor rules.
   - Light-theme pastel badges (`#fef3c7`, `#d1fae5`, `#fffbeb`) clash with SettleTable's dark slate palette (`#0f172a`, `#1e293b`).
   - Secondary captions using `--text-dim` (`#64748b`) fail WCAG AA with a 3.1:1 contrast ratio.

---

## 2. Finalized Design & Architectural Decisions

### A. Quantity Stepper Component (`.ocr-qty-stepper`)
- Structured inline control group: `[ - ] [ Value ] [ + ]`
- Spinners disabled via CSS:
  ```css
  input[type=number].ocr-edit-item-qty::-webkit-inner-spin-button,
  input[type=number].ocr-edit-item-qty::-webkit-outer-spin-button {
    -webkit-appearance: none;
    margin: 0;
  }
  input[type=number].ocr-edit-item-qty {
    -moz-appearance: textfield;
  }
  ```
- **Structure**:
  ```html
  <div class="ocr-qty-stepper" role="group" aria-label="Item quantity">
    <button type="button" class="ocr-qty-btn ocr-qty-dec" data-idx="${idx}" aria-label="Decrease quantity" ${qtyVal <= 1 ? 'disabled aria-disabled="true"' : ''}>−</button>
    <input type="number" id="ocr-item-qty-${idx}" class="ocr-edit-item-qty form-input" data-idx="${idx}" min="1" step="1" value="${qtyVal}" inputmode="numeric" />
    <button type="button" class="ocr-qty-btn ocr-qty-inc" data-idx="${idx}" aria-label="Increase quantity">+</button>
  </div>
  ```
- **Dimensions & Touch Targets**:
  - Desktop table: `104px` wide, `36px` height (`30px button | 44px input | 30px button`).
  - Mobile card: `116px` wide, `44px` height (`38px button | 40px input | 38px button`). Full 44px mobile touch envelope.
- **Keyboard & Validation**:
  - Typing allowed directly: do not clamp intermediate keystrokes on `input` (avoids clearing backspaces).
  - On `blur`: clamp to integer $\ge 1$. Update minus button disabled state.
  - Native Up/Down arrow keys increment/decrement.

### B. Adjustments Section (`#ocr-cand-adjustments-list`)
- **No Nested Cards**: Remove the inner card container. Use a subtle hairline section separator (`border-top: 1px solid var(--border-subtle); margin-top: 18px; padding-top: 14px;`).
- **Container-Aware Layout via CSS Container Queries**:
  ```css
  .ocr-candidate-card {
    container-type: inline-size;
    container-name: ocrCard;
  }
  ```
- **Desktop 1-Row Grid (`@container ocrCard (min-width: 520px)`)**:
  - Grid template: `1fr 140px 120px 36px` with micro-headers (`LABEL`, `TYPE`, `AMOUNT`, ``).
  - Row styling: subtle `background: rgba(255, 255, 255, 0.02); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 6px 10px;`.
- **Mobile 2-Line Stacked Card (`@container ocrCard (max-width: 519px)`)**:
  - Line 1: `[ Label Input (flex: 1) ] [ Delete Button (44px) ]`
  - Line 2: `[ Kind Selector (flex: 1.2) ] [ Currency Group RM + Amount (flex: 1) ]`
  - Eliminates horizontal overflow; maintains 44px touch targets.
- **Ghost Delete Button**:
  - Minimal ghost button: `background: transparent; border: 1px solid transparent; color: var(--text-dim)`.
  - Turns soft rose on `:hover` / `:focus-visible` (`background: rgba(244, 63, 94, 0.15); color: var(--accent-rose)`).
- **Currency Prefix**:
  - Dedicated static prefix `.ocr-currency-prefix` (`RM`) in `--text-muted`.

### C. Receipt Items Consistency & Unit Price Handling
- **Abolish Dedicated Unit Price Column**:
  - Desktop table columns: `[ Item Name (1fr, ~390px) ] [ Qty (104px) ] [ Line Total (RM) (120px) ] [ Delete (36px) ]`.
  - Increases item name column width by ~40%, preventing unwanted text truncation.
- **Inline Secondary Caption**:
  - Unit price is rendered as a secondary helper directly under the Line Total input:
    `<div class="ocr-item-unit-hint ocr-cand-item-unit" data-idx="${idx}">@ RM ${(unitSen/100).toFixed(2)} ea</div>`
  - **Conditional Visibility**: Visible **only when `qty > 1`**. Hidden when `qty === 1` to eliminate visual noise.
- **Structural Symmetry**:
  - Both Items and Adjustments follow a consistent mental model across desktop and mobile.

### D. Dark Theme Visual Hierarchy & Impeccable Craft Floor
- **Dark-Theme Alpha Badges**:
  - Needs Correction: `background: rgba(245, 158, 11, 0.15); color: #fde68a; border: 1px solid rgba(245, 158, 11, 0.3)`.
  - Ready for Review: `background: rgba(16, 185, 129, 0.15); color: #a7f3d0; border: 1px solid rgba(16, 185, 129, 0.3)`.
  - Verification note: `background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.25); color: #fde68a`.
- **Contrast Floor**:
  - Elevate secondary captions from `--text-dim` (`#64748b`, 3.1:1) to `--text-muted` (`#94a3b8`, 5.7:1) to strictly comply with WCAG AA ($\ge 4.5:1$).
- **Tabular Figures**:
  - Enforce `font-variant-numeric: tabular-nums` across monetary amounts, stepper inputs, and totals to avoid layout jitter during live calculations.
