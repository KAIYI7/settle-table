# SPEC: Scanned Candidate Editor Usability & Mobile Refinements

**Status**: PROPOSED  
**Priority**: High  
**Target Files**:
- `settletable/static/app.js`
- `settletable/static/style.css`
- `tools/e2e_browser_test.mjs`

---

## 1. Problem Statement & PO Feedback

Following the initial Notion-inspired redesign (PR #17), the product owner accepted the visual direction but identified 5 specific usability issues requiring focused refinement:

1. **Floating Estimated Unit Price**:
   - The `@ RM 6.00 ea` caption beneath Line Total when quantity $> 1$ looks disconnected and creates uneven row heights compared to rows with quantity $= 1$.
   - **Resolution**: Remove the floating caption from the receipt items table entirely. Preserve Item Name, Quantity stepper, Line Total, and Remove button in locked, uniform row heights with consistent baseline alignment. Store calculated unit price as an accessible `title` tooltip on the amount wrapper when quantity $> 1$. Preserve authoritative Line Total calculation.

2. **Mobile Navigation Header**:
   - At 375px, the Organizer badge wraps awkwardly across two lines, the participant name is aggressively truncated, and the Leave Room button breaks onto two lines ("Leave\nRoom").
   - **Resolution**: Hide redundant `#nav-home-btn` on mobile (since Brand logo/title already links to Home); add `white-space: nowrap` to buttons and badges; optimize mobile padding/font sizes so brand, identity, refresh icon, and Leave Room button fit on a single clean row with zero horizontal overflow.

3. **Mobile Adjustments Dropdown Readability**:
   - On 375px mobile screens, dropdown options like `Service Charge` and `BNM Rounding` truncate ("Service Cha...").
   - **Resolution**: Change `.ocr-adj-field-details` grid from `1.2fr 1fr` to `minmax(0, 1fr) 110px`. Amount input has fixed 110px width; the `<select>` receives the remaining ~170px width with `font-size: 0.88rem`, cleanly fitting all option labels without truncation while maintaining 44px touch targets.

4. **Simplify Explanatory Text**:
   - Staged description exposes internal architecture: `"Staged in browser memory outside SQLite. Edit any misread items..."`.
   - Redundant hint pill: `"Amounts represent Line Totals (Qty × Unit Price)"`.
   - Technical jargon: `"Signed minor units (e.g. -0.02 BNM rounding)"`.
   - **Resolution**:
     - Candidate description: `"Review scanned items, taxes, or discounts before applying them to the bill."`
     - Remove redundant hint pill next to "Receipt Items" (table header already says "Line Total").
     - Adjustment hint: `"Discounts and rounding as negative (e.g. -0.02)"`.

5. **Avoid Competing Receipt-Editing Flows**:
   - When an OCR candidate is staged, the separate manual `#add-item-form` beneath it remains active and competes with the staged scan.
   - **Resolution**: While `state.ocrCandidate` is active, pause manual `#add-item-form` and render a clear single-flow indicator: `"Staged receipt review in progress. Accept or discard the scanned bill above before adding manual items."`. Disable receipt sealing checkbox until the scan is resolved. Restores manual `#add-item-form` immediately when Accepted or Discarded.

---

## 2. Invariants & Guardrails

- **Zero External Dependencies**: Vanilla ES2022 + CSS variables, zero npm or CDN dependencies.
- **Financial Authority**: Line Total remains authoritative. Integer sen arithmetic in SQLite WAL.
- **WCAG AA Compliance**: Contrast $\ge 4.5:1$ across all text and controls.
- **Touch Targets**: All mobile buttons, steppers, and inputs $\ge 44 \times 44\text{px}$.
- **Impeccable Craft**: 0 mechanical anti-patterns.
