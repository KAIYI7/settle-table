# Specification: Contextual Feedback & Viewport Notification Improvement

**Status**: Ready for implementation  
**Date**: 2026-10-23  
**Branch**: `feature/receipt-feedback-polish`  
**Classification**: MEDIUM Risk (UX Enhancement, Viewport Toast, Accessible Status)

---

## 1. Problem Statement & UAT Findings

During hands-on UAT of the receipt review workflow:
1. When an organizer checks *"I confirm totals match the physical bill"* and clicks *"Approve & Seal Receipt"*, they are scrolled down within the Receipt & Charges card.
2. The current `showAlert()` inserts a notification banner into `#alert-container`, which is rendered in standard document flow immediately below `<header class="app-header">`.
3. Because the sticky header stays at the top while content scrolls beneath it, `#alert-container` scrolls completely off-screen. Users working farther down the page cannot see the transient success feedback.
4. Furthermore, the Human Receipt Review section had no persistent in-situ confirmation after approval; the button simply vanished, leaving only a disabled checkbox with no clear indicator of the sealed state.

---

## 2. Technical Architecture & Solutions

### A. Persistent In-Situ Receipt Verification Status
- **Location**: Inside the Human Receipt Review card (`renderReceiptCard` in `settletable/static/app.js`), immediately following the confirmation checkbox.
- **When `reviewConfirmed` is true**:
  - Render a prominent persistent confirmation block: `#receipt-verified-status` (`.receipt-verified-banner`).
  - Contains:
    - Status glyph: `✓`
    - Title: **Receipt Verified & Sealed**
    - Metadata: Physical bill totals verified by participant (e.g. `Alice`) & short receipt digest (e.g. `e8a2b1c4`).
  - Accessibility: `role="status"` and `aria-live="polite"`.
  - Palette: Dark-theme emerald tint (`rgba(16, 185, 129, 0.12)` background, `1px solid var(--accent-emerald)`, `#a7f3d0` text).
- **Authoritative Invariant**:
  - The status reflects the SQLite authority's `snap.review` state.
  - If any subsequent financial mutation resets the review (e.g. adding items or modifying charges), `snap.review` becomes `null` and the section dynamically reverts to "Needs Review" state.

### B. Fixed-Position Viewport Toast Container (`#alert-container`)
- **Positioning**:
  - `position: fixed;`
  - Desktop: `top: calc(64px + env(safe-area-inset-top, 0px));` (floating immediately below the sticky header).
  - Mobile ($< 640\text{px}$): `top: calc(56px + env(safe-area-inset-top, 0px));`
  - `left: 50%; transform: translateX(-50%);`
  - `width: min(calc(100% - 32px), 520px);`
  - `z-index: 1000;` (floating above header and card content).
  - `pointer-events: none;` on the container so non-alert areas pass clicks through seamlessly.
- **Toast Item (`.alert-banner`)**:
  - `pointer-events: auto;`
  - Compact vertical footprint (height $\approx 42\text{px}$–$46\text{px}$).
  - `box-shadow: 0 4px 16px rgba(0, 0, 0, 0.45), 0 1px 3px rgba(0, 0, 0, 0.3);`
  - `backdrop-filter: blur(8px); -webkit-backdrop-filter: blur(8px);`
  - Subtle entrance animation (`toast-in 0.2s cubic-bezier(0.16, 1, 0.3, 1)`).
  - Zero Cumulative Layout Shift (CLS): Because `#alert-container` is fixed, toasts popping in and out cause zero document reflow or scroll jumps.

### C. Enhanced `showAlert()` & Dismissal Semantics
- **Clean Dismissal Path**:
  - Single `dismissAlert()` function that cleans up active timers, DOM nodes, and keyboard event listeners.
- **Duplicate Prevention & Timing**:
  - Avoids stacking identical alert banners or flashing duplicate messages.
  - Automatically times out transient toasts (5s for success/info, persistent for conflict until actioned or closed).
- **Keyboard & Touch Accessibility**:
  - `✕` close button with $\ge 36\text{px}$ touch target, `aria-label="Dismiss notification"`, `title="Dismiss notification (Esc)"`.
  - Global `Escape` key listener active while toast is displayed.
  - ARIA: `role="alert"` + `aria-live="assertive"` for errors/conflicts; `role="status"` + `aria-live="polite"` for success/info.

### D. Server Confirmation & Feedback Guarding
- No premature success feedback: operations (create meal, OCR apply, receipt review, invitations, join approvals, finalization, Notion export) only display success toast after the server returns `200/201` and the updated snapshot is fetched.
- Clear error feedback on failure (`handleApiError`).

---

## 3. Verification Plan

1. **CDP Real-Browser Automated Test**:
   - Scroll page down to center the Human Receipt Review card (verifying `window.scrollY > 200px`).
   - Check "I confirm totals match the physical bill".
   - Click "Approve & Seal Receipt".
   - Assert `window.scrollY` did NOT jump to top.
   - Assert `#receipt-verified-status` is visible in the review card in the DOM.
   - Assert `.alert-banner` is within the current viewport (`rect.top >= 0 && rect.bottom <= window.innerHeight`).
   - Assert pressing `Escape` removes `.alert-banner`.
   - Capture screenshot of scrolled viewport showing both persistent in-situ confirmation and floating toast.
2. **Impeccable Craft Audit**:
   - Run `impeccable detect` on modified CSS and JS.
3. **Full Regression Suite**:
   - Run 182 unit/integration tests with `python -m unittest discover -s tests`.
4. **Independent UI/UX Review**:
   - Delegate visual, interaction, and accessibility review to an independent reviewer subagent.
