/**
 * SettleTable Mobile-Friendly Single-Page Application
 * Zero external dependencies, pure vanilla ES2022.
 */

// --- Global Utilities & State ---
const state = {
  mealId: null,
  snapshot: null,
  currentUserId: null,
  isOrganizer: false,
  loading: false,
  pollTimer: null,
  pollSeq: 0,
  mutationActive: false,
  allocationConflictPending: false,
  issuedTokens: {},
  ocrCandidate: null,
  localPhotoUrl: null,
  photoModalZoom: 1,
  photoModalPan: { x: 0, y: 0 },
  photoModalDragging: false,
  photoModalDragStart: { x: 0, y: 0 },
  photoModalTrigger: null,
  notionParentId: '',
  notionToken: '',
  notionExport: null,
  notionPollTimer: null,
  paymentSimulations: new Map(),
  paymentBusy: new Set(),
  paymentReadSeq: new Map(),
  paymentTimers: new Map(),
  paymentEpoch: 0,
  allocationTargetId: null,
  expandedHybridItemIds: new Set(),
  activeMobileSheetItemId: null,
  selectedSplitDiners: new Map(),
  publicConfig: null,
  turnstileWidgetId: undefined,
  emergencyRecoveryUrl: null,
  emergencyRecoveryMealId: null,
};

// The allocation sheet is rebuilt on each snapshot, so retain descriptors rather
// than references to DOM nodes that will be replaced.
let sheetTrigger = null;
const sheetFocusableSelector = 'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';
function focusDescriptor(element) {
  if (!element) return null;
  return ['data-action', 'data-item', 'data-target', 'data-frac', 'data-step', 'id']
    .map(name => [name, element.getAttribute(name)]);
}
function findDescribedElement(root, descriptor) {
  if (!descriptor) return null;
  return [...root.querySelectorAll(sheetFocusableSelector)].find(el =>
    descriptor.every(([name, value]) => el.getAttribute(name) === value));
}
function sheetFocusables(sheet) {
  return [...sheet.querySelectorAll(sheetFocusableSelector)].filter(el => el.getClientRects().length);
}
function closeMobileSheet() {
  state.activeMobileSheetItemId = null;
  updateMealUI();
}

// --- Fullscreen / Zoom Receipt Photo Modal Controller ---
let receiptModalInitialized = false;

function openReceiptModal(src, triggerEl) {
  if (!src) return;
  state.photoModalTrigger = triggerEl || document.activeElement;
  state.photoModalZoom = 1;
  state.photoModalPan = { x: 0, y: 0 };
  state.photoModalDragging = false;

  const modal = document.getElementById('receipt-modal');
  const img = document.getElementById('receipt-modal-img');
  const zoomLevel = document.getElementById('receipt-zoom-level');
  const closeBtn = document.getElementById('receipt-modal-close');

  if (modal && img) {
    img.src = src;
    img.style.transform = 'translate(0px, 0px) scale(1)';
    if (zoomLevel) zoomLevel.textContent = '100%';
    modal.style.display = 'flex';
    document.body.style.overflow = 'hidden';
    if (closeBtn) closeBtn.focus();
  }
}

function closeReceiptModal() {
  const modal = document.getElementById('receipt-modal');
  if (!modal || modal.style.display === 'none') return;
  modal.style.display = 'none';
  document.body.style.overflow = '';
  state.photoModalDragging = false;

  if (state.photoModalTrigger && typeof state.photoModalTrigger.focus === 'function') {
    state.photoModalTrigger.focus();
  }
  state.photoModalTrigger = null;
}

function updateReceiptModalTransform() {
  const img = document.getElementById('receipt-modal-img');
  const zoomLevel = document.getElementById('receipt-zoom-level');
  if (img) {
    img.style.transform = `translate(${state.photoModalPan.x}px, ${state.photoModalPan.y}px) scale(${state.photoModalZoom})`;
  }
  if (zoomLevel) {
    zoomLevel.textContent = `${Math.round(state.photoModalZoom * 100)}%`;
  }
}

function zoomReceiptModal(factor, reset = false) {
  if (reset) {
    state.photoModalZoom = 1;
    state.photoModalPan = { x: 0, y: 0 };
  } else {
    state.photoModalZoom = Math.min(4.0, Math.max(0.5, state.photoModalZoom * factor));
  }
  updateReceiptModalTransform();
}

function initReceiptModalEvents() {
  if (receiptModalInitialized) return;
  receiptModalInitialized = true;

  const modal = document.getElementById('receipt-modal');
  const backdrop = document.getElementById('receipt-modal-backdrop');
  const closeBtn = document.getElementById('receipt-modal-close');
  const zoomIn = document.getElementById('receipt-zoom-in');
  const zoomOut = document.getElementById('receipt-zoom-out');
  const zoomReset = document.getElementById('receipt-zoom-reset');
  const viewport = document.getElementById('receipt-modal-viewport');

  if (closeBtn) closeBtn.addEventListener('click', closeReceiptModal);
  if (backdrop) backdrop.addEventListener('click', closeReceiptModal);
  if (zoomIn) zoomIn.addEventListener('click', () => zoomReceiptModal(1.25));
  if (zoomOut) zoomOut.addEventListener('click', () => zoomReceiptModal(0.8));
  if (zoomReset) zoomReset.addEventListener('click', () => zoomReceiptModal(1, true));

  if (viewport) {
    // Wheel zoom
    viewport.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.15 : 0.85;
      zoomReceiptModal(factor);
    }, { passive: false });

    // Mouse drag pan
    viewport.addEventListener('mousedown', (e) => {
      if (e.target.closest('button')) return;
      e.preventDefault();
      state.photoModalDragging = true;
      state.photoModalDragStart = {
        x: e.clientX - state.photoModalPan.x,
        y: e.clientY - state.photoModalPan.y,
      };
      viewport.classList.add('is-dragging');
    });

    window.addEventListener('mousemove', (e) => {
      if (!state.photoModalDragging) return;
      state.photoModalPan = {
        x: e.clientX - state.photoModalDragStart.x,
        y: e.clientY - state.photoModalDragStart.y,
      };
      updateReceiptModalTransform();
    });

    window.addEventListener('mouseup', () => {
      if (state.photoModalDragging) {
        state.photoModalDragging = false;
        if (viewport) viewport.classList.remove('is-dragging');
      }
    });

    // Touch support for mobile pan
    viewport.addEventListener('touchstart', (e) => {
      if (e.touches && e.touches.length === 1) {
        state.photoModalDragging = true;
        state.photoModalDragStart = {
          x: e.touches[0].clientX - state.photoModalPan.x,
          y: e.touches[0].clientY - state.photoModalPan.y,
        };
      }
    }, { passive: true });

    viewport.addEventListener('touchmove', (e) => {
      if (!state.photoModalDragging || !e.touches || e.touches.length !== 1) return;
      e.preventDefault();
      state.photoModalPan = {
        x: e.touches[0].clientX - state.photoModalDragStart.x,
        y: e.touches[0].clientY - state.photoModalDragStart.y,
      };
      updateReceiptModalTransform();
    }, { passive: false });

    viewport.addEventListener('touchend', () => {
      state.photoModalDragging = false;
    });
  }

  // Escape key listener
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal && modal.style.display !== 'none') {
      closeReceiptModal();
    }
  });
}

function freshReceiptItemId(items, adjustments) {
  const occupied = new Set([...items, ...adjustments].map(source => source.id));
  let id;
  do { id = `item-${crypto.randomUUID()}`; } while (occupied.has(id));
  return id;
}

function gcd(a, b) {
  a = Math.abs(a);
  b = Math.abs(b);
  while (b) {
    const t = b;
    b = a % b;
    a = t;
  }
  return a || 1;
}

function makeReducedFraction(num, den) {
  if (den === 0) return 0;
  if (num % den === 0) {
    return num / den;
  }
  const g = gcd(num, den);
  return [num / g, den / g];
}

function toRat(q) {
  if (Array.isArray(q)) {
    return [q[0], q[1] || 1];
  }
  const n = parseInt(q, 10) || 0;
  return [n, 1];
}

function addFractions(q1, q2) {
  const [n1, d1] = toRat(q1);
  const [n2, d2] = toRat(q2);
  const num = n1 * d2 + n2 * d1;
  const den = d1 * d2;
  return makeReducedFraction(num, den);
}

function subtractFractions(q1, q2) {
  const [n1, d1] = toRat(q1);
  const [n2, d2] = toRat(q2);
  const num = n1 * d2 - n2 * d1;
  const den = d1 * d2;
  if (num <= 0) return 0;
  return makeReducedFraction(num, den);
}

function ratToNum(q) {
  if (Array.isArray(q)) {
    return q[1] ? q[0] / q[1] : 0;
  }
  return typeof q === 'number' ? q : 0;
}

function formatRat(q) {
  if (Array.isArray(q)) {
    if (q[1] === 1) return `${q[0]}`;
    if (q[0] === 1 && q[1] === 2) return '½';
    if (q[0] === 1 && q[1] === 3) return '⅓';
    if (q[0] === 2 && q[1] === 3) return '⅔';
    if (q[0] === 1 && q[1] === 4) return '¼';
    if (q[0] === 3 && q[1] === 4) return '¾';
    return `${q[0]}/${q[1]}`;
  }
  return `${q}`;
}

// Pure-JS SHA-256 for synchronous tie-breaking matching Python hashlib.sha256
function sha256Hex(ascii) {
  function rightRotate(value, amount) {
    return (value >>> amount) | (value << (32 - amount));
  }
  const words = [];
  const asciiBitLength = ascii.length * 8;
  let hash = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ];
  const k = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
  ];

  for (let i = 0; i < ascii.length; i++) {
    words[i >> 2] |= (ascii.charCodeAt(i) & 0xff) << (24 - (i % 4) * 8);
  }
  words[asciiBitLength >> 5] |= 0x80 << (24 - (asciiBitLength % 32));
  words[(((asciiBitLength + 64) >> 9) << 4) + 15] = asciiBitLength;

  for (let i = 0; i < words.length; i += 16) {
    const w = [];
    for (let j = 0; j < 16; j++) w[j] = words[i + j] || 0;
    for (let j = 16; j < 64; j++) {
      const s0 = rightRotate(w[j - 15], 7) ^ rightRotate(w[j - 15], 18) ^ (w[j - 15] >>> 3);
      const s1 = rightRotate(w[j - 2], 17) ^ rightRotate(w[j - 2], 19) ^ (w[j - 2] >>> 10);
      w[j] = (w[j - 16] + s0 + w[j - 7] + s1) | 0;
    }

    let [a, b, c, d, e, f, g, h] = hash;
    for (let j = 0; j < 64; j++) {
      const s1 = rightRotate(e, 6) ^ rightRotate(e, 11) ^ rightRotate(e, 25);
      const ch = (e & f) ^ ((~e) & g);
      const temp1 = (h + s1 + ch + k[j] + w[j]) | 0;
      const s0 = rightRotate(a, 2) ^ rightRotate(a, 13) ^ rightRotate(a, 22);
      const maj = (a & b) ^ (a & c) ^ (b & c);
      const temp2 = (s0 + maj) | 0;

      h = g;
      g = f;
      f = e;
      e = (d + temp1) | 0;
      d = c;
      c = b;
      b = a;
      a = (temp1 + temp2) | 0;
    }

    hash[0] = (hash[0] + a) | 0;
    hash[1] = (hash[1] + b) | 0;
    hash[2] = (hash[2] + c) | 0;
    hash[3] = (hash[3] + d) | 0;
    hash[4] = (hash[4] + e) | 0;
    hash[5] = (hash[5] + f) | 0;
    hash[6] = (hash[6] + g) | 0;
    hash[7] = (hash[7] + h) | 0;
  }

  let result = '';
  for (let i = 0; i < 8; i++) {
    for (let j = 3; j >= 0; j--) {
      const b = (hash[i] >> (j * 8)) & 0xff;
      result += (b < 16 ? '0' : '') + b.toString(16);
    }
  }
  return result;
}

/**
 * Apportions an item's base amount (lineSen) deterministically among claimants
 * using the Largest Remainder (Hamilton-Hare) method with SHA-256 tie-breaker,
 * exactly matching the backend calculator (_apportion in calculation.py).
 */
function apportionItemBase(lineSen, claims, itemId, itemTotalQty) {
  const result = new Map();
  if (!lineSen || lineSen <= 0) {
    if (Array.isArray(claims)) {
      for (const c of claims) result.set(c.participant_id, 0);
    }
    return result;
  }

  const [totN, totD] = toRat(itemTotalQty);
  const totalQtyRat = { n: BigInt(totN), d: BigInt(totD) };
  if (totalQtyRat.n <= 0n) return result;

  let sumClaimed = { n: 0n, d: 1n };
  const participants = [];
  if (Array.isArray(claims)) {
    for (const c of claims) {
      const [n, d] = toRat(c.quantity);
      if (n > 0) {
        const weight = { n: BigInt(n), d: BigInt(d) };
        participants.push({ id: c.participant_id, weight });
        const num = sumClaimed.n * weight.d + weight.n * sumClaimed.d;
        const den = sumClaimed.d * weight.d;
        sumClaimed = { n: num, d: den };
      } else {
        result.set(c.participant_id, 0);
      }
    }
  }

  if (participants.length === 0) {
    return result;
  }

  const unassignedNum = totalQtyRat.n * sumClaimed.d - sumClaimed.n * totalQtyRat.d;
  const unassignedDen = totalQtyRat.d * sumClaimed.d;

  const weights = [...participants];
  if (unassignedNum > 0n) {
    weights.push({ id: '__unassigned__', weight: { n: unassignedNum, d: unassignedDen } });
  }

  const quotas = [];
  let floorSum = 0;
  for (const w of weights) {
    const num = BigInt(lineSen) * w.weight.n * totalQtyRat.d;
    const den = w.weight.d * totalQtyRat.n;
    const floor = Number(num / den);
    const remNum = num % den;
    floorSum += floor;
    quotas.push({
      id: w.id,
      floor,
      remNum,
      remDen: den,
      hash: sha256Hex(JSON.stringify(['tabwise-apportion-v1', itemId, w.id]))
    });
  }

  const remainderCents = lineSen - floorSum;
  quotas.sort((a, b) => {
    const crossA = a.remNum * b.remDen;
    const crossB = b.remNum * a.remDen;
    if (crossA > crossB) return -1;
    if (crossA < crossB) return 1;
    if (a.hash < b.hash) return -1;
    if (a.hash > b.hash) return 1;
    return a.id < b.id ? -1 : 1;
  });

  for (let i = 0; i < remainderCents && i < quotas.length; i++) {
    quotas[i].floor += 1;
  }

  for (const q of quotas) {
    if (q.id !== '__unassigned__') {
      result.set(q.id, q.floor);
    }
  }
  return result;
}

function formatSen(sen) {
  if (sen === null || sen === undefined) return 'RM 0.00';
  const val = Number(sen) / 100;
  return `RM ${val.toFixed(2)}`;
}

function formatOcrIssue(issue, cand) {
  if (issue === 'candidate_receipt_mismatch') {
    const printedTotal = cand && cand.total_sen != null ? formatSen(cand.total_sen) : 'unknown';
    const adjSum = ((cand && cand.adjustments) || []).reduce((acc, a) => acc + (a.amount_sen || 0), 0);
    const computedTotal = ((cand && cand.subtotal_sen) || 0) + adjSum;
    const diff = cand && cand.discrepancy_sen != null ? formatSen(Math.abs(cand.discrepancy_sen)) : '0';
    return `Charges mismatch: Sum of extracted items + adjustments (${formatSen(computedTotal)}) does not reconcile with printed bill total (${printedTotal}) [Discrepancy: ${diff}]. Please verify items or adjustments.`;
  }
  if (issue === 'low_confidence') return 'Low scan confidence (< 85%). Please verify item names and prices carefully.';
  if (issue === 'unidentified_items') return 'Some item descriptions could not be clearly identified.';
  if (issue === 'missing_items') return 'No receipt items recognized from photo.';
  if (issue === 'missing_receipt_total') return 'Printed total could not be determined.';
  if (issue === 'invalid_rounding_adjustment') return 'Extracted rounding adjustment exceeds standard BNM 5-sen guidelines.';
  return issue;
}

function parseSen(input, allowNegative = false) {
  if (typeof input !== 'string') {
    throw new Error('Price must be a string');
  }
  let s = input.trim();
  let isNegative = false;
  if (s.startsWith('-')) {
    isNegative = true;
    s = s.slice(1).trim();
  }
  if (s.toUpperCase().startsWith('RM')) {
    s = s.slice(2).trim();
  }
  if (s.startsWith('-')) {
    isNegative = true;
    s = s.slice(1).trim();
  }
  if (!s || !/^[0-9]+(?:\.[0-9]{1,2})?$/.test(s)) {
    throw new Error(`Invalid price '${input}'. Enter an amount like 12.50 or RM 12.50`);
  }
  if (isNegative && !allowNegative) {
    throw new Error(`Negative amount not allowed for '${input}'`);
  }
  const parts = s.split('.');
  const whole = parseInt(parts[0], 10);
  const fracStr = (parts[1] || '').padEnd(2, '0');
  const frac = parseInt(fracStr, 10);
  const totalSen = whole * 100 + frac;
  if (totalSen < 0 || totalSen > 1_000_000_000) {
    throw new Error('Price out of bounds: maximum RM 10,000,000.00');
  }
  return isNegative ? -totalSen : totalSen;
}

function escapeHtml(str) {
  if (str === null || str === undefined) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function extractNotionUuid(val) {
  if (!val || typeof val !== 'string') return null;
  const trimmed = val.trim();
  const hyphenMatch = trimmed.match(/\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b/);
  if (hyphenMatch) return hyphenMatch[1].toLowerCase();

  const hexMatch = trimmed.match(/([0-9a-fA-F]{32})/);
  if (hexMatch) {
    const h = hexMatch[1].toLowerCase();
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
  }
  return null;
}

let alertTimer = null;
let alertKeyHandler = null;

function syncHeaderHeight() {
  const header = document.querySelector('.app-header');
  if (header) {
    const height = Math.ceil(header.getBoundingClientRect().height);
    if (height > 0) {
      document.documentElement.style.setProperty('--app-header-height', `${height}px`);
    }
  }
}

function syncAlertContainerPlacement() {
  const container = document.getElementById('alert-container');
  const hasBottomSheet = Boolean(state?.activeMobileSheetItemId && window.innerWidth < 768);
  if (container) {
    container.classList.toggle('alert-container-top', hasBottomSheet);
  }
  document.body.classList.toggle('has-bottom-sheet', hasBottomSheet);
}

function dismissAlert() {
  if (alertTimer) {
    clearTimeout(alertTimer);
    alertTimer = null;
  }
  if (alertKeyHandler) {
    window.removeEventListener('keydown', alertKeyHandler);
    alertKeyHandler = null;
  }
  const container = document.getElementById('alert-container');
  if (container) {
    container.innerHTML = '';
  }
  syncAlertContainerPlacement();
}

/**
 * Smoothly scrolls the viewport to a target workflow section and sets focus
 * for keyboard and assistive-technology users without duplicate scroll jumps.
 * Clears the sticky header via CSS scroll-margin-top.
 * Respects prefers-reduced-motion.
 *
 * @param {string|HTMLElement} target - Section ID or element to scroll into view
 * @param {string|HTMLElement} [focusTarget] - Specific element to focus
 */
function navigateToWorkflowSection(target, focusTarget = null) {
  const elem = typeof target === 'string' ? document.getElementById(target) : target;
  if (!elem) return;

  const prefersReduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const behavior = prefersReduced ? 'auto' : 'smooth';

  elem.scrollIntoView({ behavior, block: 'start' });

  // Programmatic focus management
  let toFocus = null;
  if (focusTarget) {
    toFocus = typeof focusTarget === 'string' ? document.getElementById(focusTarget) : focusTarget;
  }
  if (!toFocus) {
    toFocus = elem.querySelector('[tabindex="-1"], input:not([disabled]), button:not([disabled]), h3, .card-title') || elem;
  }

  if (toFocus && typeof toFocus.focus === 'function') {
    if (!toFocus.hasAttribute('tabindex') && !['INPUT', 'BUTTON', 'A', 'SELECT', 'TEXTAREA'].includes(toFocus.tagName)) {
      toFocus.setAttribute('tabindex', '-1');
    }
    try {
      toFocus.focus({ preventScroll: true });
    } catch {
      toFocus.focus();
    }
  }
}

/**
 * Determines the next workflow destination from the authoritative refreshed snapshot
 * after a successful Approve & Seal Receipt action:
 * - If any paid items still need allocation, navigate to Item Allocation.
 * - Complimentary RM0.00 items are ignored when determining allocation completeness.
 * - If all paid items are fully allocated and finalization is available, navigate to Seal & Finalize Meal.
 * - If other blocking issues exist, navigate to and highlight the actionable warning.
 */
function navigateAfterReceiptReview() {
  const snap = state.snapshot;
  if (!snap) return;

  const receipt = snap.receipt;
  const items = receipt?.items || [];
  const issues = snap.issues || [];
  const reviewConfirmed = Boolean(snap.review);

  // 1. Paid items allocation check (complimentary RM0.00 items are ignored)
  const paidItems = items.filter(it => it.line_sen > 0);
  const hasUnallocatedPaidItem = paidItems.some(it => {
    const claims = (snap.claims || []).filter(c => c.item_id === it.id && c.financial_revision === snap.financial_revision);
    const totalClaimedRat = claims.reduce((acc, c) => addFractions(acc, c.quantity), 0);
    const totalClaimed = ratToNum(totalClaimedRat);
    const itemTotalQty = ratToNum(it.quantity);
    return Math.abs(totalClaimed - itemTotalQty) >= 0.0001;
  });

  const hasClaimIssues = issues.includes('incomplete_quantity') || issues.includes('pending_claim');
  const needsAllocation = (paidItems.length > 0 && hasUnallocatedPaidItem) || hasClaimIssues;

  if (needsAllocation) {
    navigateToWorkflowSection('allocation-section', 'allocation-heading');
    return;
  }

  // 2. All paid items are allocated (or receipt is complimentary-only). Check finalization availability.
  const hasItems = items.length > 0;
  const canFinalize = hasItems && reviewConfirmed && issues.length === 0;

  if (canFinalize) {
    navigateToWorkflowSection('finalize-section', 'finalize-btn');
    return;
  }

  // 3. Other blocking issues exist (e.g. issues in issues array, or no items)
  const warningEl = document.querySelector('.finalize-warning');
  if (warningEl) {
    if (!warningEl.hasAttribute('tabindex')) warningEl.setAttribute('tabindex', '-1');
    navigateToWorkflowSection('finalize-section', warningEl);
  } else {
    navigateToWorkflowSection('finalize-section', 'finalize-heading');
  }
}

function showAlert(message, type = 'error', dismissible = true) {
  syncHeaderHeight();
  syncAlertContainerPlacement();
  const container = document.getElementById('alert-container');
  if (!container) return;

  // Prevent duplicate flash if identical message & type are already showing
  const existingMsg = container.querySelector('.alert-message')?.textContent;
  const existingDiv = container.querySelector('.alert-banner');
  if (existingDiv && existingMsg === message && existingDiv.classList.contains(`alert-${type}`)) {
    if (type !== 'conflict') {
      if (alertTimer) clearTimeout(alertTimer);
      alertTimer = setTimeout(dismissAlert, 5000);
    }
    return;
  }

  dismissAlert();

  const div = document.createElement('div');
  div.className = `alert-banner alert-${type}`;
  div.setAttribute('role', type === 'error' || type === 'conflict' ? 'alert' : 'status');
  div.setAttribute('aria-live', type === 'error' || type === 'conflict' ? 'assertive' : 'polite');

  const msgSpan = document.createElement('span');
  msgSpan.className = 'alert-message';
  msgSpan.textContent = message;
  div.appendChild(msgSpan);

  if (dismissible) {
    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'alert-close-btn';
    closeBtn.setAttribute('aria-label', 'Dismiss notification');
    closeBtn.setAttribute('title', 'Dismiss notification (Esc)');
    closeBtn.textContent = '✕';
    closeBtn.addEventListener('click', dismissAlert);
    div.appendChild(closeBtn);

    alertKeyHandler = (e) => {
      if (e.key === 'Escape') {
        dismissAlert();
      }
    };
    window.addEventListener('keydown', alertKeyHandler);
  }

  container.appendChild(div);

  if (type !== 'conflict') {
    alertTimer = setTimeout(() => {
      dismissAlert();
    }, 5000);
  }
}

function clearAlerts() {
  dismissAlert();
}

// --- API Layer ---
async function apiCall(endpoint, method = 'GET', body = null, extraHeaders = {}) {
  const headers = Object.assign({}, extraHeaders);
  if (method === 'POST' || method === 'DELETE') {
    headers['X-SettleTable-Action'] = '1';
    if (body !== null && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
  }

  const opts = {
    method,
    headers,
    credentials: 'same-origin',
  };
  if (body !== null) {
    opts.body = JSON.stringify(body);
  }

  try {
    const res = await fetch(endpoint, opts);
    const data = await res.json().catch(() => null);

    if (!res.ok) {
      const err = new Error(data?.error || `HTTP ${res.status}`);
      err.status = res.status;
      err.code = data?.error || 'unknown_error';
      throw err;
    }
    return data;
  } catch (err) {
    throw err;
  }
}

// --- Router ---
let joinPollTimer = null;

function clearJoinPolling() {
  if (joinPollTimer) {
    clearInterval(joinPollTimer);
    joinPollTimer = null;
  }
}

function route() {
  clearAlerts();
  clearJoinPolling();
  const path = window.location.pathname;
  const hash = window.location.hash;

  // 0. If user explicitly requested home hash (#/ or #/welcome), prioritize home over path-based landing
  if (hash === '#/' || hash === '#/welcome') {
    if (path !== '/') {
      window.history.replaceState(null, '', '/#/');
    }
    renderWelcome();
    return;
  }

  // 0b. If user explicitly navigated to a hash route while on a path-based landing, prioritize hash and normalize path
  if (hash.startsWith('#/meal/')) {
    const mealId = hash.replace('#/meal/', '').trim();
    if (mealId) {
      if (path !== '/') {
        window.history.replaceState(null, '', `/#/meal/${mealId}`);
      }
      loadMeal(mealId);
      return;
    }
  }

  if (hash.startsWith('#/invite/')) {
    const token = hash.replace('#/invite/', '').trim();
    if (token) {
      if (path !== '/') {
        window.history.replaceState(null, '', `/#/invite/${token}`);
      }
      renderInviteLanding(token);
      return;
    }
  }

  if (hash.startsWith('#/claim-organizer/') || hash.startsWith('#/claim/')) {
    const token = hash.replace(/^#\/(?:claim-organizer|claim)\//, '').trim();
    if (token) {
      if (path !== '/') {
        window.history.replaceState(null, '', `/#/claim/${token}`);
      }
      renderOrganizerClaimLanding(token);
      return;
    }
  }

  if (hash.startsWith('#/join/')) {
    const mealId = hash.replace('#/join/', '').trim();
    if (mealId) {
      if (path !== '/') {
        window.history.replaceState(null, '', `/#/join/${mealId}`);
      }
      renderGeneralJoinLanding(mealId);
      return;
    }
  }

  // 1. Check path for invitation landing /invite/{token}
  const inviteMatch = path.match(/^\/invite\/([A-Za-z0-9_-]{43})$/);
  if (inviteMatch) {
    renderInviteLanding(inviteMatch[1]);
    return;
  }

  // 1b. Check path for organizer claim landing /(claim-organizer|claim)/{token}
  const claimMatch = path.match(/^\/(?:claim-organizer|claim)\/([A-Za-z0-9_-]{43})$/);
  if (claimMatch) {
    renderOrganizerClaimLanding(claimMatch[1]);
    return;
  }

  // 1c. Check path for general meal join landing /join/{mealId}
  const joinMatch = path.match(/^\/join\/([A-Za-z0-9_-]+)$/);
  if (joinMatch) {
    renderGeneralJoinLanding(joinMatch[1]);
    return;
  }

  renderWelcome();
}

window.addEventListener('hashchange', () => {
  syncHeaderHeight();
  route();
});
window.addEventListener('DOMContentLoaded', () => {
  syncHeaderHeight();
  document.querySelectorAll('.brand-link, #nav-home-btn').forEach((link) => {
    link.addEventListener('click', (e) => {
      clearJoinPolling();
      if (window.location.pathname !== '/' || (window.location.hash !== '#/' && window.location.hash !== '')) {
        e.preventDefault();
        window.history.replaceState(null, '', '/#/');
        renderWelcome();
      }
    });
  });
  route();
});
window.addEventListener('beforeunload', () => {
  if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
    URL.revokeObjectURL(state.localPhotoUrl);
  }
});
window.addEventListener('resize', () => {
  syncHeaderHeight();
  syncAlertContainerPlacement();
});
window.addEventListener('keydown', (e) => {
  const sheet = document.getElementById('hybrid-bottom-sheet');
  if (sheet && e.key === 'Tab') {
    const controls = sheetFocusables(sheet);
    const index = controls.indexOf(document.activeElement);
    if (!controls.length) {
      e.preventDefault();
      sheet.focus();
    } else if (index < 0 || (e.shiftKey && index === 0) || (!e.shiftKey && index === controls.length - 1)) {
      e.preventDefault();
      controls[e.shiftKey ? controls.length - 1 : 0].focus();
    }
  }
  if (e.key === 'Escape') {
    if (state.activeMobileSheetItemId) {
      closeMobileSheet();
    } else if (state.expandedHybridItemIds && state.expandedHybridItemIds.size > 0) {
      state.expandedHybridItemIds.clear();
      updateMealUI();
    }
  }
});

document.addEventListener('focusin', (e) => {
  const sheet = document.getElementById('hybrid-bottom-sheet');
  if (sheet && !sheet.contains(e.target)) {
    (sheetFocusables(sheet)[0] || sheet).focus();
  }
});

// Document visibility to pause polling
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    stopPolling();
    clearSimulationTimers();
  } else if (state.mealId && !state.pollTimer) {
    startPolling();
    for (const [id, value] of state.paymentSimulations) {
      if (['PENDING', 'REQUEST_UNKNOWN'].includes(value.state)) scheduleSimulationReads(id);
    }
  }
});

function startPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  state.pollTimer = setInterval(pollSnapshot, 3000);
}

function stopPolling() {
  if (state.pollTimer) {
    clearInterval(state.pollTimer);
    state.pollTimer = null;
  }
  if (state.notionPollTimer) {
    clearInterval(state.notionPollTimer);
    state.notionPollTimer = null;
  }
}

function pollNotionExportStatus(onDone) {
  if (state.notionPollTimer) {
    clearInterval(state.notionPollTimer);
    state.notionPollTimer = null;
  }
  let pollAttempts = 0;
  state.notionPollTimer = setInterval(async () => {
    pollAttempts++;
    try {
      const pollRes = await fetch(`/api/meals/${state.mealId}/export/notion`);
      const pollData = await pollRes.json();
      if (pollData.ok && pollData.export && (pollData.export.status === 'completed' || pollData.export.status === 'already_exported')) {
        clearInterval(state.notionPollTimer);
        state.notionPollTimer = null;
        state.notionExport = pollData.export;
        updateMealUI();
        showAlert('Report exported to Notion successfully!', 'success');
        if (onDone) onDone(true);
      } else if (pollData.ok && pollData.export && pollData.export.status === 'failed') {
        clearInterval(state.notionPollTimer);
        state.notionPollTimer = null;
        state.notionExport = pollData.export;
        updateMealUI();
        const errDetail = pollData.export.export_digest || 'notion_error';
        showAlert(`Notion export failed: ${errDetail}`, 'error');
        if (onDone) onDone(false);
      } else if (pollAttempts >= 70) {
        clearInterval(state.notionPollTimer);
        state.notionPollTimer = null;
        if (onDone) onDone(false);
        showAlert('Notion export is taking longer than expected. Please check back shortly.', 'conflict');
      }
    } catch {
      clearInterval(state.notionPollTimer);
      state.notionPollTimer = null;
      if (onDone) onDone(false);
      showAlert('Failed to poll Notion export status.', 'error');
    }
  }, 1000);
}

async function fetchSnapshot(force = false) {
  if (!state.mealId) return;
  if (!force && state.mutationActive) return;
  const seq = ++state.pollSeq;
  try {
    const snap = await apiCall(`/api/meals/${state.mealId}/snapshot`);
    if (seq >= state.pollSeq && snap?.ok) {
      const prevSnap = state.snapshot;
      const prevRev = prevSnap ? prevSnap.revision : -1;
      const prevFinRev = prevSnap ? prevSnap.financial_revision : -1;
      const prevFinalized = prevSnap ? prevSnap.finalized : null;
      const prevUser = state.currentUserId;
      const prevIsOrg = state.isOrganizer;

      state.snapshot = snap;
      state.currentUserId = snap.current_participant_id;
      state.isOrganizer = snap.is_organizer;

      const prevJrJson = JSON.stringify(prevSnap?.join_requests || []);
      const currJrJson = JSON.stringify(snap.join_requests || []);
      const prevInvJson = JSON.stringify(prevSnap?.invitations || []);
      const currInvJson = JSON.stringify(snap.invitations || []);

      const hasChanged = !prevSnap 
        || snap.revision !== prevRev 
        || snap.financial_revision !== prevFinRev
        || snap.finalized !== prevFinalized
        || snap.current_participant_id !== prevUser
        || snap.is_organizer !== prevIsOrg
        || prevJrJson !== currJrJson
        || prevInvJson !== currInvJson;

      if (force || hasChanged) {
        updateMealUI();
        if (snap.finalized && !prevFinalized) loadSimulationReads(snap);
      }
      if (state.allocationConflictPending) {
        state.allocationConflictPending = false;
        showAlert('⚠️ Allocation Conflict: Latest state reloaded. Review the allocations before trying again.', 'conflict');
      }
      return true;
    }
    if (seq === state.pollSeq && state.allocationConflictPending) {
      showAlert('⚠️ Allocation Conflict: Refresh failed. Check your connection or session, close Details / Split if open, then use the refresh button to retry.', 'conflict');
    }
    return false;
  } catch (err) {
    if (seq === state.pollSeq) {
      if (err.status === 401) stopPolling();
      if (state.allocationConflictPending) {
        showAlert('⚠️ Allocation Conflict: Refresh failed. Check your connection or session, close Details / Split if open, then use the refresh button to retry.', 'conflict');
      } else if (err.status === 401) {
        showAlert('Session expired. Please rejoin or request a new invite.', 'error');
      }
    }
    return false;
  }
}

function pollSnapshot() {
  return fetchSnapshot(false);
}

// --- View 1: Welcome Screen ---
async function handleLeaveRoom() {
  const mealId = state.mealId || 'the room';
  try {
    await apiCall('/api/session/clear', 'POST', {});
  } catch (err) {
    console.warn('Session clear error:', err);
  }
  stopPolling();
  resetSimulationView();
  if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
    URL.revokeObjectURL(state.localPhotoUrl);
  }
  state.localPhotoUrl = null;
  state.mealId = null;
  state.snapshot = null;
  state.allocationConflictPending = false;
  state.currentUserId = null;
  state.isOrganizer = false;
  state.ocrCandidate = null;
  state.notionParentId = '';
  state.notionToken = '';
  state.notionExport = null;
  state.allocationTargetId = null;
  state.expandedHybridItemIds.clear();
  state.activeMobileSheetItemId = null;
  state.selectedSplitDiners.clear();
  const headerStatus = document.getElementById('header-user-status');
  if (headerStatus) headerStatus.innerHTML = '';
  syncHeaderHeight();
  if (window.location.hash === '#/') {
    renderWelcome();
  } else {
    window.location.hash = '#/';
  }
  setTimeout(() => {
    showAlert(`You have left ${mealId} and exited your session. Session cookie cleared.`, 'info');
  }, 50);
}

// --- Local Storage & Recent Meals Registry ---
function getRecentMeals() {
  try {
    const raw = localStorage.getItem('settletable_recent_meals');
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function saveRecentMeal(meal) {
  try {
    let meals = getRecentMeals();
    meals = meals.filter(m => m.meal_id !== meal.meal_id);
    meals.unshift(meal);
    if (meals.length > 10) meals = meals.slice(0, 10);
    localStorage.setItem('settletable_recent_meals', JSON.stringify(meals));
  } catch (err) {
    console.warn('Failed to save recent meal', err);
  }
}

function removeRecentMeal(mealId) {
  try {
    let meals = getRecentMeals();
    meals = meals.filter(m => m.meal_id !== mealId);
    localStorage.setItem('settletable_recent_meals', JSON.stringify(meals));
  } catch (err) {
    console.warn('Failed to remove recent meal', err);
  }
  renderWelcome();
}

function loadTurnstileScript() {
  if (window.turnstile || document.getElementById('cf-turnstile-script')) {
    return Promise.resolve();
  }
  return new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.id = 'cf-turnstile-script';
    s.src = 'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit';
    s.async = true;
    s.defer = true;
    s.onload = () => resolve();
    s.onerror = (e) => reject(new Error('Failed to load Turnstile script'));
    document.head.appendChild(s);
  });
}

async function renderWelcome() {
  stopPolling();
  state.mealId = null;
  state.snapshot = null;
  state.currentUserId = null;
  state.isOrganizer = false;
  const headerStatus = document.getElementById('header-user-status');
  if (headerStatus) headerStatus.innerHTML = '';
  syncHeaderHeight();

  // Load public config
  if (!state.publicConfig) {
    try {
      const cfg = await apiCall('/api/public-config');
      if (cfg?.ok) {
        state.publicConfig = cfg;
      }
    } catch {
      state.publicConfig = { public_creation_enabled: false };
    }
  }

  const isCreationEnabled = Boolean(state.publicConfig?.public_creation_enabled);
  const sitekey = state.publicConfig?.turnstile_sitekey;
  const recentMeals = getRecentMeals();

  const app = document.getElementById('app');

  let createSectionHtml = '';
  if (isCreationEnabled) {
    createSectionHtml = `
      <div class="card">
        <h2 class="card-title">Create a Meal Room</h2>
        <p class="card-desc">Set up a private room in seconds. You will receive an organizer link to manage items and invite diners.</p>
        
        <form id="create-meal-form">
          <div class="form-group">
            <label for="create-meal-id">Meal Name / Title</label>
            <input type="text" id="create-meal-id" placeholder="e.g. Friday Hai Di Lao" required maxlength="60">
            <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 4px;">A secure, private room URL will be generated automatically.</div>
          </div>
          
          <div class="form-group">
            <label for="create-org-name">Your Name (Organizer)</label>
            <input type="text" id="create-org-name" placeholder="e.g. Alice" required maxlength="40">
          </div>

          <div class="form-group">
            <label for="create-diners">Diners (Optional, comma-separated)</label>
            <input type="text" id="create-diners" placeholder="e.g. Bob, Charlie, Dave" maxlength="200">
            <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 4px;">You can also invite diners after creating the room.</div>
          </div>

          ${sitekey ? `<div class="form-group"><div id="turnstile-container" style="min-height: 65px; display: flex; align-items: center;"></div></div>` : ''}

          <button type="submit" id="create-meal-submit-btn" class="btn btn-primary btn-block">🚀 Create Private Meal Room</button>
        </form>
      </div>
    `;
  } else {
    createSectionHtml = `
      <div class="card" style="border-left: 4px solid var(--accent-indigo, #6366f1);">
        <h2 class="card-title" style="color: var(--text-heading);">Host Administrative Mode</h2>
        <p class="card-desc">Public self-service meal room creation is currently disabled on this server.</p>
        <div class="alert alert-info" style="margin: 0; font-size: 0.85rem; line-height: 1.45;">
          If you have been invited to an existing meal, enter the room ID below or click the invitation link provided by your meal organizer.
        </div>
      </div>
    `;
  }

  let recentMealsHtml = '';
  if (recentMeals.length > 0) {
    const rows = recentMeals.map(m => {
      const isOrg = m.role === 'organizer';
      const badgeClass = isOrg ? 'badge-organizer' : 'badge-diner';
      const roleText = isOrg ? 'Organizer' : 'Diner';
      const dateStr = m.created_at ? new Date(m.created_at).toLocaleDateString() : '';
      return `
        <div class="recent-meal-row">
          <div class="recent-meal-info">
            <div class="recent-meal-title-line">
              <span>${escapeHtml(m.title || m.meal_id)}</span>
              <span class="badge ${badgeClass}">${roleText}</span>
            </div>
            <div class="recent-meal-meta">${escapeHtml(m.meal_id)}${dateStr ? ` &bull; ${dateStr}` : ''}</div>
          </div>
          <div class="recent-meal-actions">
            <button type="button" class="btn btn-secondary btn-sm recent-meal-open-btn" data-meal="${escapeHtml(m.meal_id)}">Open Room</button>
            <button type="button" class="btn-remove-recent" data-remove="${escapeHtml(m.meal_id)}" title="Remove from device list" aria-label="Remove ${escapeHtml(m.title || m.meal_id)} from list">✕</button>
          </div>
        </div>
      `;
    }).join('');

    recentMealsHtml = `
      <div class="card" id="recent-meals-card">
        <h2 class="card-title">Recent Meals on this Device</h2>
        <p class="card-desc">Quickly return to meals created or joined on this browser.</p>
        <div class="recent-meals-list">
          ${rows}
        </div>
        <p style="font-size: 0.8rem; color: var(--text-muted); margin: 10px 0 0 0; line-height: 1.4;">
          Rooms open automatically on this device. SettleTable requires no accounts or passwords.
        </p>
      </div>
    `;
  }

  app.innerHTML = `
    ${createSectionHtml}
    ${recentMealsHtml}
    <div class="card">
      <h2 class="card-title">Open Existing Meal</h2>
      <form id="open-meal-form">
        <div class="form-group">
          <label for="open-meal-id">Meal ID</label>
          <input type="text" id="open-meal-id" placeholder="e.g. friday-hotpot-a8f2k9b4c1" required>
        </div>
        <button type="submit" class="btn btn-secondary btn-block">Enter Meal Room</button>
      </form>
    </div>

    <div style="text-align: center; margin-top: 16px;">
      <button id="welcome-clear-session-btn" class="btn btn-secondary btn-sm" style="font-size: 0.85rem; color: var(--text-muted);" title="Clear current session cookie">
        Log Out / Clear Active Session
      </button>
    </div>
  `;

  // Attach event listeners
  document.getElementById('welcome-clear-session-btn')?.addEventListener('click', handleLeaveRoom);

  // Recent meals actions
  document.querySelectorAll('.recent-meal-open-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const mealId = btn.getAttribute('data-meal');
      if (mealId) window.location.hash = `#/meal/${mealId}`;
    });
  });

  document.querySelectorAll('.btn-remove-recent').forEach(btn => {
    btn.addEventListener('click', () => {
      const mealId = btn.getAttribute('data-remove');
      if (mealId) removeRecentMeal(mealId);
    });
  });

  document.getElementById('open-meal-form')?.addEventListener('submit', (e) => {
    e.preventDefault();
    const mealId = document.getElementById('open-meal-id').value.trim();
    if (mealId) {
      window.location.hash = `#/meal/${mealId}`;
    }
  });

  // Render Turnstile widget if enabled and container exists
  if (isCreationEnabled && sitekey) {
    loadTurnstileScript().then(() => {
      if (window.turnstile && document.getElementById('turnstile-container')) {
        try {
          state.turnstileWidgetId = window.turnstile.render('#turnstile-container', {
            sitekey: sitekey,
            action: 'public_create_meal',
            theme: 'dark',
          });
        } catch (err) {
          console.warn('Failed to render Turnstile widget:', err);
        }
      }
    }).catch(err => {
      console.warn('Turnstile script failed to load:', err);
    });
  }

  // Handle Create Meal submission
  document.getElementById('create-meal-form')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = (document.getElementById('create-meal-id')?.value || '').trim();
    const customMealId = title || null;
    const orgName = document.getElementById('create-org-name').value.trim();
    const dinersRaw = document.getElementById('create-diners').value.trim();

    let diners = [];
    if (dinersRaw) {
      diners = dinersRaw.split(',').map(d => d.trim()).filter(Boolean);
    }

    let turnstileToken = null;
    if (window.turnstile && state.turnstileWidgetId !== undefined) {
      turnstileToken = window.turnstile.getResponse(state.turnstileWidgetId);
      if (!turnstileToken && sitekey) {
        showAlert('Please complete the anti-abuse verification before creating your room.', 'error');
        return;
      }
    }

    let idempotencyKey;
    if (window.crypto && window.crypto.getRandomValues) {
      const bytes = new Uint8Array(16);
      window.crypto.getRandomValues(bytes);
      idempotencyKey = 'idemp-' + Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
    } else {
      idempotencyKey = 'idem-' + Math.random().toString(36).substring(2) + Date.now().toString(36);
    }

    const submitBtn = document.getElementById('create-meal-submit-btn');
    try {
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = 'Creating private room...';
      }
      showAlert('Creating your private meal room...', 'info');

      const payload = {
        meal_title: title,
        organizer_name: orgName,
        diners: diners,
        turnstile_token: turnstileToken,
        idempotency_key: idempotencyKey,
        custom_meal_id: customMealId,
      };

      const res = await apiCall('/api/meals/public-create', 'POST', payload);
      if (res?.ok && res.meal_id) {
        saveRecentMeal({
          meal_id: res.meal_id,
          title: res.meal_title || title,
          role: 'organizer',
          created_at: Date.now(),
        });
        if (res.organizer_claim?.claim_url) {
          state.emergencyRecoveryUrl = res.organizer_claim.claim_url;
          state.emergencyRecoveryMealId = res.meal_id;
        }
        showAlert('Meal room created! Establishing your organizer session...', 'success');
        window.location.hash = `#/meal/${res.meal_id}`;
      } else {
        throw new Error(res?.error || 'Unknown error');
      }
    } catch (err) {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.textContent = '🚀 Create Private Meal Room';
      }
      if (window.turnstile && state.turnstileWidgetId !== undefined) {
        try { window.turnstile.reset(state.turnstileWidgetId); } catch {}
      }
      let msg = err.message || '';
      if (msg.includes('rate_limit_exceeded')) {
        msg = 'Too many rooms created recently. Please wait a moment before trying again.';
      } else if (msg.includes('capacity_exceeded')) {
        msg = 'Server room capacity reached. Please contact the administrator.';
      } else if (msg.includes('public_creation_disabled')) {
        msg = 'Public self-service meal creation is currently disabled by the host administrator.';
      } else if (msg.includes('turnstile_verification_failed') || msg.includes('turnstile_token_reused')) {
        msg = 'Anti-bot verification failed or expired. Please solve the challenge again.';
      } else if (msg.includes('ambiguous_participant_name')) {
        msg = 'Participant names must be distinct. Two diners cannot share the same name.';
      }
      showAlert(`Failed to create meal: ${msg}`, 'error');
    }
  });
}

// --- View 2: Invitation Landing Screen ---
async function renderInviteLanding(token) {
  stopPolling();
  document.getElementById('header-user-status').innerHTML = '';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Verifying invitation token...</p>
    </div>
  `;

  try {
    // Send token strictly in request body to POST /api/invitations/inspect to prevent token exposure in access logs
    const inspection = await apiCall('/api/invitations/inspect', 'POST', { invitation_token: token });
    if (!inspection?.ok || !inspection.valid) {
      const reasonMap = {
        expired: 'This invitation has expired.',
        consumed: 'This invitation was already used.',
        revoked: 'This invitation was revoked by the organizer.',
        not_found: 'Invitation not found. Please check your link.',
        invalid_token: 'Invalid invitation link format.',
      };
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title" style="color: var(--accent-rose)">Invitation Invalid</h2>
          <p class="card-desc">${reasonMap[inspection?.reason] || 'This link cannot be redeemed.'}</p>
          <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
        </div>
      `;
      return;
    }

    // Valid invitation card
    app.innerHTML = `
      <div class="card">
        <h2 class="card-title">You're Invited to Dine!</h2>
        <p class="card-desc">Join meal <strong>${escapeHtml(inspection.meal_id)}</strong> to view the bill and claim your portion.</p>
        
        <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
          <div style="font-size: 0.85rem; color: var(--text-muted);">Joining as:</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #a7f3d0;">${escapeHtml(inspection.participant_name)}</div>
        </div>

        <div class="alert alert-conflict" style="margin-bottom: 20px; font-size: 0.85rem; line-height: 1.45;">
          <div>
            <strong>⚠️ Same-Browser Profile Notice:</strong><br>
            Accepting this invitation will assign this browser window to <strong>${escapeHtml(inspection.participant_name)} (Diner)</strong>.
            If you are the Organizer testing this meal in the same browser, this will <strong>replace your Organizer session</strong>.
            <div style="margin-top: 6px; color: #fef08a;">
              💡 <em>To test diner claiming while keeping your Organizer view open, copy this link and open it in a <strong>Private / Incognito window</strong> or a separate browser profile.</em>
            </div>
          </div>
        </div>

        <button id="redeem-btn" class="btn btn-success btn-block" style="font-size: 1.05rem; margin-bottom: 10px;">
          Accept & Join Meal
        </button>

        <a href="#/" class="btn btn-secondary btn-block">Cancel & Return to Home</a>
      </div>
    `;

    document.getElementById('redeem-btn').addEventListener('click', async () => {
      try {
        const btn = document.getElementById('redeem-btn');
        btn.disabled = true;
        btn.textContent = 'Joining...';
        
        // Send token strictly in request body to prevent URL logging in reverse proxy / Gunicorn access logs
        const redeemRes = await apiCall(`/api/meals/${inspection.meal_id}/invitations/redeem`, 'POST', { invitation_token: token });
        if (redeemRes?.ok) {
          // Sanitize URL immediately so refreshing doesn't re-trigger consumed token
          window.history.replaceState(null, '', `/#/meal/${inspection.meal_id}`);
          loadMeal(inspection.meal_id);
        }
      } catch (err) {
        showAlert(`Failed to join: ${err.message}`, 'error');
        document.getElementById('redeem-btn').disabled = false;
        document.getElementById('redeem-btn').textContent = 'Accept & Join Meal';
      }
    });

  } catch (err) {
    app.innerHTML = `
      <div class="card">
        <h2 class="card-title" style="color: var(--accent-rose)">Network Error</h2>
        <p class="card-desc">Could not connect to SettleTable server. ${escapeHtml(err.message)}</p>
        <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
      </div>
    `;
  }
}

// --- View 2-org: Organizer Claim & Recovery Landing Screen ---
async function renderOrganizerClaimLanding(token) {
  stopPolling();
  document.getElementById('header-user-status').innerHTML = '';
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Verifying organizer token...</p>
    </div>
  `;

  try {
    // Send token strictly in request body to POST /api/organizer-claims/inspect to prevent token exposure in access logs
    const inspection = await apiCall('/api/organizer-claims/inspect', 'POST', { claim_token: token });
    if (!inspection?.ok || !inspection.valid) {
      const reasonMap = {
        expired: 'This organizer setup / recovery link has expired.',
        consumed: 'This link has already been used to activate an organizer session.',
        revoked: 'This link was replaced or revoked by a newer recovery request.',
        not_found: 'Organizer link not found. Please verify the URL or ask the host administrator to run recovery.',
        invalid_token: 'Invalid organizer link format.',
      };
      app.innerHTML = `
        <div class="card" style="max-width: 500px; margin: 40px auto;">
          <h2 class="card-title" style="color: var(--accent-rose)">Organizer Link Invalid</h2>
          <p class="card-desc">${reasonMap[inspection?.reason] || 'This link cannot be redeemed.'}</p>
          <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
        </div>
      `;
      return;
    }

    // Valid organizer claim card
    app.innerHTML = `
      <div class="card" style="max-width: 500px; margin: 40px auto;">
        <h2 class="card-title">Organizer Access Setup</h2>
        <p class="card-desc">Activate your organizer session for meal <strong>${escapeHtml(inspection.meal_id)}</strong>.</p>
        
        <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
          <div style="font-size: 0.85rem; color: var(--text-muted);">Organizer:</div>
          <div style="font-size: 1.25rem; font-weight: 700; color: #a7f3d0;">${escapeHtml(inspection.organizer_name || 'Organizer')}</div>
        </div>

        <div class="alert alert-info" style="margin-bottom: 20px; font-size: 0.85rem; line-height: 1.45;">
          <div>
            <strong>🔑 Organizer Browser Activation:</strong><br>
            Activating will establish an authenticated Organizer session on this browser.
            Your session is stored in an encrypted, secure browser cookie.
          </div>
        </div>

        <button id="claim-org-btn" class="btn btn-success btn-block" style="font-size: 1.05rem; margin-bottom: 10px;">
          Activate Organizer Session
        </button>

        <a href="#/" class="btn btn-secondary btn-block">Cancel & Return to Home</a>
      </div>
    `;

    document.getElementById('claim-org-btn').addEventListener('click', async () => {
      const btn = document.getElementById('claim-org-btn');
      btn.disabled = true;
      btn.textContent = 'Activating session...';
      try {
        // Send token strictly in request body to prevent URL logging in reverse proxy / Gunicorn access logs
        const res = await apiCall(`/api/meals/${inspection.meal_id}/organizer-claims/claim`, 'POST', { claim_token: token });
        if (res?.ok) {
          window.history.replaceState(null, '', `/#/meal/${inspection.meal_id}`);
          loadMeal(inspection.meal_id);
        }
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Activate Organizer Session';
        showAlert(`Failed to activate organizer session: ${err.message}`, 'error');
      }
    });

  } catch (err) {
    app.innerHTML = `
      <div class="card" style="max-width: 500px; margin: 40px auto;">
        <h2 class="card-title" style="color: var(--accent-rose)">Network Error</h2>
        <p class="card-desc">Could not connect to SettleTable server. ${escapeHtml(err.message)}</p>
        <a href="#/" class="btn btn-secondary btn-block">Go to Home</a>
      </div>
    `;
  }
}

// --- View 2b: General Table Join Landing ---
async function renderGeneralJoinLanding(mealId, infoMessage = null) {
  clearJoinPolling();
  const app = document.getElementById('app');

  app.innerHTML = `
    <div class="card" style="max-width: 500px; margin: 40px auto;">
      <h2 class="card-title">Join Dining Table</h2>
      <p class="card-desc">Request to join meal room <strong>${escapeHtml(mealId)}</strong></p>

      ${infoMessage ? `<div class="alert alert-info" style="margin-bottom: 16px;">${escapeHtml(infoMessage)}</div>` : ''}

      <div style="margin-bottom: 20px;">
        <label for="join-name-input" style="display: block; font-size: 0.85rem; font-weight: 600; margin-bottom: 6px; color: var(--text-heading);">
          Your Name at the Table
        </label>
        <input id="join-name-input" type="text" placeholder="e.g. Charlie" class="input" style="width: 100%; box-sizing: border-box; font-size: 1rem; padding: 10px 12px;" />
        <div style="font-size: 0.8rem; color: var(--text-dim); margin-top: 4px;">
          Enter your name as added by the table organizer. The organizer will approve your access.
        </div>
      </div>

      <div class="alert alert-conflict" style="margin-bottom: 20px; font-size: 0.85rem; line-height: 1.45;">
        <div>
          <strong>⚠️ Same-Browser Profile Notice:</strong><br>
          Joining will assign this browser window to your Diner session.
          If you are testing as the Organizer in this same browser, this will <strong>replace your Organizer session</strong>.
          <div style="margin-top: 6px; color: #fef08a;">
            💡 <em>To test as a diner while keeping your Organizer view open, open this join link in a <strong>Private / Incognito window</strong>.</em>
          </div>
        </div>
      </div>

      <div id="join-error-box" style="display: none; margin-bottom: 16px;"></div>

      <button id="submit-join-req-btn" class="btn btn-primary btn-block" style="font-size: 1.05rem; margin-bottom: 10px; min-height: 44px;">
        Request to Join
      </button>

      <button id="join-cancel-home-btn" class="btn btn-secondary btn-block" style="text-align: center; min-height: 44px; display: flex; align-items: center; justify-content: center; width: 100%;">
        Cancel & Return to Home
      </button>
    </div>
  `;

  const nameInput = document.getElementById('join-name-input');
  const submitBtn = document.getElementById('submit-join-req-btn');
  const errorBox = document.getElementById('join-error-box');
  const cancelHomeBtn = document.getElementById('join-cancel-home-btn');

  if (cancelHomeBtn) {
    cancelHomeBtn.addEventListener('click', (e) => {
      e.preventDefault();
      clearJoinPolling();
      window.history.replaceState(null, '', '/#/');
      renderWelcome();
    });
  }

  nameInput.focus();

  const handleSubmit = async () => {
    const name = nameInput.value.trim();
    if (!name) {
      errorBox.className = 'alert alert-error';
      errorBox.textContent = 'Please enter your name.';
      errorBox.style.display = 'block';
      return;
    }
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submitting Request...';
    errorBox.style.display = 'none';

    try {
      const res = await apiCall(`/api/meals/${mealId}/join-requests`, 'POST', { display_name: name });
      if (res?.ok) {
        renderJoinWaitingState(mealId, res.request_id, res.claim_token, res.display_name);
      }
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Request to Join';
      errorBox.className = 'alert alert-error';
      errorBox.style.display = 'block';
      const msg = err.message || '';
      if (msg.includes('active_join_request_exists') || msg.includes('409')) {
        errorBox.textContent = 'A join request is already pending for this diner. Please wait for the table organizer to approve your request.';
      } else if (msg.includes('resource_limit') || msg.includes('429')) {
        errorBox.textContent = 'Too many join requests have been made for this meal table. Please speak to the organizer directly.';
      } else if (msg.includes('invalid_join_target') || msg.includes('400') || msg.includes('404')) {
        errorBox.textContent = `Unable to request access for "${name}". Please check the spelling or ask the table organizer to add you.`;
      } else {
        errorBox.textContent = `Could not submit request: ${msg}`;
      }
    }
  };

  submitBtn.addEventListener('click', handleSubmit);
  nameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') handleSubmit();
  });
}

function renderJoinWaitingState(mealId, requestId, claimToken, displayName) {
  clearJoinPolling();
  const app = document.getElementById('app');

  app.innerHTML = `
    <div class="card" style="max-width: 500px; margin: 40px auto;">
      <h2 class="card-title">Join Request Submitted</h2>
      <p class="card-desc">Waiting for the organizer to approve access for <strong>${escapeHtml(displayName)}</strong>.</p>

      <div class="loading-state" style="padding: 24px 0; text-align: center;">
        <div class="spinner"></div>
        <p style="margin-top: 14px; font-weight: 600; color: #a7f3d0;" id="join-poll-status-text">
          Awaiting table organizer confirmation...
        </p>
      </div>

      <div style="font-size: 0.85rem; color: var(--text-dim); text-align: center; margin-bottom: 20px; line-height: 1.4;">
        Please ask the organizer at the table to tap <strong>Approve</strong> on their screen.
      </div>

      <div id="join-status-alert" style="display: none; margin-bottom: 16px;"></div>

      <div style="display: flex; flex-direction: column; gap: 10px;">
        <button id="cancel-join-btn" class="btn btn-secondary btn-block" style="min-height: 44px;">
          Cancel Request
        </button>
        <button id="cancel-join-home-btn" class="btn btn-secondary btn-block" style="min-height: 44px; opacity: 0.85;">
          Cancel & Return to Home
        </button>
      </div>
    </div>
  `;

  const cancelBtn = document.getElementById('cancel-join-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      cancelBtn.disabled = true;
      cancelBtn.textContent = 'Cancelling Request...';
      clearJoinPolling();
      try {
        await apiCall(`/api/meals/${mealId}/join-requests/${requestId}/cancel`, 'POST', { claim_token: claimToken });
      } catch (err) {
        console.warn('Error cancelling join request on server:', err);
      }
      renderGeneralJoinLanding(mealId, 'Your join request was cancelled.');
    });
  }

  const cancelHomeBtn = document.getElementById('cancel-join-home-btn');
  if (cancelHomeBtn) {
    cancelHomeBtn.addEventListener('click', async () => {
      cancelHomeBtn.disabled = true;
      cancelHomeBtn.textContent = 'Cancelling...';
      clearJoinPolling();
      try {
        await apiCall(`/api/meals/${mealId}/join-requests/${requestId}/cancel`, 'POST', { claim_token: claimToken });
      } catch (err) {
        console.warn('Error cancelling join request on server:', err);
      }
      window.history.replaceState(null, '', '/#/');
      renderWelcome();
    });
  }

  const pollStatus = async () => {
    try {
      const inspectRes = await apiCall(`/api/meals/${mealId}/join-requests/${requestId}`, 'GET', null, {
        'X-Claim-Token': claimToken,
      });
      if (!joinPollTimer || !inspectRes?.ok) return;

      if (inspectRes.status === 'approved') {
        clearJoinPolling();
        const statusText = document.getElementById('join-poll-status-text');
        if (statusText) {
          statusText.textContent = 'Approved! Connecting to table...';
          statusText.style.color = 'var(--accent-emerald)';
        }

        const claimRes = await apiCall(`/api/meals/${mealId}/join-requests/${requestId}/claim`, 'POST', {
          claim_token: claimToken,
        });
        if (claimRes?.ok) {
          window.history.replaceState(null, '', `/#/meal/${mealId}`);
          loadMeal(mealId);
        }
      } else if (inspectRes.status === 'rejected') {
        clearJoinPolling();
        const alertBox = document.getElementById('join-status-alert');
        if (alertBox) {
          alertBox.className = 'alert alert-error';
          alertBox.textContent = 'The organizer declined your request to join.';
          alertBox.style.display = 'block';
        }
        const spinner = document.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
        const statusText = document.getElementById('join-poll-status-text');
        if (statusText) statusText.textContent = 'Request Declined';
        if (cancelBtn) {
          cancelBtn.disabled = false;
          cancelBtn.textContent = 'Back to Table Join';
          cancelBtn.onclick = () => renderGeneralJoinLanding(mealId);
        }
      } else if (inspectRes.status === 'cancelled') {
        clearJoinPolling();
        const alertBox = document.getElementById('join-status-alert');
        if (alertBox) {
          alertBox.className = 'alert alert-info';
          alertBox.textContent = 'This join request was cancelled.';
          alertBox.style.display = 'block';
        }
        const spinner = document.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
        const statusText = document.getElementById('join-poll-status-text');
        if (statusText) statusText.textContent = 'Request Cancelled';
        if (cancelBtn) {
          cancelBtn.disabled = false;
          cancelBtn.textContent = 'Back to Table Join';
          cancelBtn.onclick = () => renderGeneralJoinLanding(mealId);
        }
      } else if (inspectRes.status === 'expired') {
        clearJoinPolling();
        const alertBox = document.getElementById('join-status-alert');
        if (alertBox) {
          alertBox.className = 'alert alert-error';
          alertBox.textContent = 'This join request has expired.';
          alertBox.style.display = 'block';
        }
        const spinner = document.querySelector('.spinner');
        if (spinner) spinner.style.display = 'none';
        const statusText = document.getElementById('join-poll-status-text');
        if (statusText) statusText.textContent = 'Request Expired';
        if (cancelBtn) {
          cancelBtn.disabled = false;
          cancelBtn.textContent = 'Back to Table Join';
          cancelBtn.onclick = () => renderGeneralJoinLanding(mealId);
        }
      }
    } catch (err) {
      // transient network retry
    }
  };

  joinPollTimer = setInterval(pollStatus, 1500);
}

// --- View 3: Meal Room ---
async function loadMeal(mealId) {
  resetSimulationView();
  if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
    URL.revokeObjectURL(state.localPhotoUrl);
  }
  state.localPhotoUrl = null;
  state.mealId = mealId;
  state.notionParentId = '';
  state.notionToken = '';
  state.notionExport = null;
  state.allocationTargetId = null;
  state.expandedHybridItemIds.clear();
  state.activeMobileSheetItemId = null;
  state.selectedSplitDiners.clear();
  const app = document.getElementById('app');
  app.innerHTML = `
    <div class="loading-state">
      <div class="spinner"></div>
      <p>Loading meal details...</p>
    </div>
  `;

  try {
    const snap = await apiCall(`/api/meals/${mealId}/snapshot`);
    if (snap?.ok) {
      state.snapshot = snap;
      state.currentUserId = snap.current_participant_id;
      state.isOrganizer = snap.is_organizer;

      // If finalized, check Notion export status (both organizer and diners)
      if (snap.finalized) {
        try {
          const expRes = await apiCall(`/api/meals/${mealId}/export/notion`);
          if (expRes?.ok && expRes.export) {
            const expStatus = expRes.export.status;
            if (expStatus === 'completed' || expStatus === 'already_exported' || expStatus === 'failed' || expStatus === 'in_progress') {
              state.notionExport = expRes.export;
            }
          }
        } catch {
          // Non-critical, ignore
        }
      }

      updateMealUI();
      loadSimulationReads(snap);
      startPolling();

      // If in-progress export, resume active polling for organizer
      if (snap.finalized && snap.is_organizer && state.notionExport && state.notionExport.status === 'in_progress') {
        pollNotionExportStatus();
      }
    }
  } catch (err) {
    if (err.status === 401) {
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title" style="color: var(--accent-rose)">Session Required</h2>
          <p class="card-desc">You are not authenticated for meal <strong>${escapeHtml(mealId)}</strong>. If you are a diner, open the invitation link sent by your organizer.</p>
          <a href="#/" class="btn btn-secondary btn-block">Back to Home</a>
          <button id="clear-invalid-session-btn" class="btn btn-secondary btn-block" style="margin-top: 10px;">Clear Active Session</button>
        </div>
      `;
      document.getElementById('clear-invalid-session-btn')?.addEventListener('click', handleLeaveRoom);
    } else {
      app.innerHTML = `
        <div class="card">
          <h2 class="card-title">Error Loading Meal</h2>
          <p class="card-desc">${escapeHtml(err.message)}</p>
          <a href="#/" class="btn btn-secondary btn-block">Back to Home</a>
        </div>
      `;
    }
  }
}

function updateMealUI() {
  window.settletable = { state, updateMealUI, navigateToWorkflowSection, navigateAfterReceiptReview };
  const snap = state.snapshot;
  if (!snap) return;

  // Preserve receipt drafts during conflict recovery, including closing the sheet.
  const draftSelector = state.allocationConflictPending
    ? '#new-item-label, #new-item-qty, #new-item-price, [id^="ocr-item-"], [id^="ocr-adj-"], #ocr-edit-included-tax'
    : '#new-item-label, #new-item-qty, #new-item-price';
  const conflictDrafts = Array.from(document.querySelectorAll(draftSelector)).map(el => [el.id, el.value]);
  const scopeDrafts = Array.from(document.querySelectorAll('details[data-service-scope]')).map(details => {
    const inputs = [...details.querySelectorAll('.service-scope-item')];
    const dirty = inputs.some(input => input.checked !== input.defaultChecked);
    return { adjustment: details.dataset.serviceScope, open: details.open,
      revision: details.dataset.financialRevision, warned: !!details.querySelector('.scope-draft-warning'),
      selected: dirty ? inputs.map(input => [input.value, input.checked]) : null };
  }).filter(draft => draft.open || draft.selected);
  const activeElem = document.activeElement;
  const previousSheet = document.getElementById('hybrid-bottom-sheet');
  const sheetFocus = previousSheet?.contains(activeElem) ? focusDescriptor(activeElem) : null;
  const activeId = activeElem?.id;
  const selectionStart = activeElem?.selectionStart;
  const selectionEnd = activeElem?.selectionEnd;

  const currentParentId = document.getElementById('notion-parent-id')?.value;
  if (currentParentId !== undefined && currentParentId !== '') {
    state.notionParentId = currentParentId;
  }
  const currentToken = document.getElementById('notion-token')?.value;
  if (currentToken !== undefined && currentToken !== '') {
    state.notionToken = currentToken;
  }

  const restoreFocus = () => {
    for (const [id, value] of conflictDrafts) {
      const el = document.getElementById(id);
      if (el) el.value = value;
    }
    for (const draft of scopeDrafts) {
      const details = Array.from(document.querySelectorAll('details[data-service-scope]'))
        .find(el => el.dataset.serviceScope === draft.adjustment);
      if (!details) continue;
      details.open = draft.open;
      if (draft.selected) {
        if (draft.warned || draft.revision !== String(snap.financial_revision)) {
          details.open = true;
          const warning = document.createElement('p');
          warning.className = 'scope-draft-warning';
          warning.setAttribute('role', 'status');
          warning.textContent = 'Receipt changed while you were editing this selection. Review the latest receipt and your selection before applying it.';
          details.insertBefore(warning, details.querySelector('summary')?.nextSibling || null);
        }
        const selected = new Map(draft.selected);
        for (const input of details.querySelectorAll('.service-scope-item')) {
          if (selected.has(input.value)) input.checked = selected.get(input.value);
        }
      }
    }
    const sheet = document.getElementById('hybrid-bottom-sheet');
    if (sheet) {
      (findDescribedElement(sheet, sheetFocus) || sheetFocusables(sheet)[0] || sheet).focus({ preventScroll: true });
      return;
    }
    if (previousSheet) {
      const trigger = findDescribedElement(document, sheetTrigger);
      sheetTrigger = null;
      if (trigger) trigger.focus({ preventScroll: true });
      return;
    }
    if (activeId) {
      const el = document.getElementById(activeId);
      if (el) {
        el.focus();
        if (typeof selectionStart === 'number' && typeof selectionEnd === 'number') {
          try {
            el.setSelectionRange(selectionStart, selectionEnd);
          } catch {}
        }
      }
    }
  };

  // Header Status
  const user = snap.participants?.find(p => p.id === state.currentUserId);
  const userName = user ? user.name : 'Unknown';
  const roleBadge = state.isOrganizer 
    ? '<span class="badge badge-organizer" title="Organizer">👑 <span class="badge-role-text">Organizer</span></span>' 
    : '<span class="badge badge-diner" title="Diner">🍽️ <span class="badge-role-text">Diner</span></span>';
  
  document.getElementById('header-user-status').innerHTML = `
    <div class="header-participant-info">
      ${roleBadge}
      <span class="header-username" title="Participant: ${escapeHtml(userName)}">${escapeHtml(userName)}</span>
    </div>
    <button id="manual-refresh-btn" class="btn btn-secondary btn-sm" title="Refresh Snapshot">⟳</button>
    <button id="header-leave-btn" class="btn btn-secondary btn-sm btn-leave" title="Exit room and clear session cookie">Leave Room</button>
  `;
  document.getElementById('manual-refresh-btn')?.addEventListener('click', () => fetchSnapshot(true));
  document.getElementById('header-leave-btn')?.addEventListener('click', handleLeaveRoom);
  syncHeaderHeight();

  const app = document.getElementById('app');
  let html = '';

  // 1. Status Bar Card
  const finalized = snap.finalized;
  const reviewConfirmed = Boolean(snap.review);
  const issues = snap.issues || [];

  let statusBadge = '<span class="badge badge-pending">Drafting</span>';
  if (finalized) {
    statusBadge = '<span class="badge badge-verified">Finalized ✓</span>';
  } else if (reviewConfirmed) {
    statusBadge = '<span class="badge badge-verified">Review Verified ✓</span>';
  }

  html += `
    <div class="card room-status-card">
      <div class="room-status-inner">
        <div class="room-status-left">
          <div class="room-status-breadcrumbs">
            <a href="#/" class="room-home-link" title="Return to Home Screen">
              <span class="room-home-arrow">←</span> Home
            </a>
            <span class="room-breadcrumb-sep">/</span>
            <span class="room-badge-label">Room</span>
          </div>
          <h2 class="room-title">${escapeHtml(snap.meal_id)}</h2>
        </div>
        <div class="room-status-right">
          ${statusBadge}
          <div class="room-revision-label">Revision ${snap.revision}</div>
        </div>
      </div>
    </div>
  `;

  if (state.emergencyRecoveryUrl && state.emergencyRecoveryMealId === (state.mealId || snap.meal_id)) {
    html += `
      <div class="alert alert-warning" id="organizer-emergency-banner" style="margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 6px;">
          <div style="font-weight: 600;">⚠️ One-Time Organizer Recovery Link</div>
          <button type="button" id="dismiss-emergency-claim-btn" class="btn btn-secondary btn-sm" style="padding: 2px 8px; font-size: 0.75rem;">Dismiss</button>
        </div>
        <p style="margin: 0 0 8px 0; font-size: 0.85rem; line-height: 1.4;">
          SettleTable uses private browser cookies instead of accounts.
          Save this <strong>one-time recovery link</strong> to restore organizer access if you switch devices or clear browser data:
        </p>
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
          <input type="text" readonly value="${escapeHtml(state.emergencyRecoveryUrl)}" id="emergency-claim-url-input" style="flex: 1; min-width: 220px; font-size: 0.8rem; background: var(--surface-bg); padding: 6px 10px; border: 1px solid var(--border-subtle); border-radius: 4px;" />
          <button type="button" class="btn btn-secondary btn-sm" id="copy-emergency-claim-btn">Copy Link</button>
        </div>
      </div>
    `;
  }

  // Quick navigation for organizers
  if (state.isOrganizer) {
    html += `
      <div class="organizer-quick-nav" style="display: flex; gap: 8px; margin-bottom: 14px; flex-wrap: wrap;">
        <button type="button" class="btn btn-secondary btn-sm" id="quick-nav-sharing-btn" style="border-color: #818cf8; color: #818cf8; font-weight: 600;">
          👥 Sharing & Access ▾
        </button>
      </div>
    `;
  }

  // 2. Finalized View: Apportionment Breakdown, Restaurant Funding & Peer Settlements
  if (finalized && snap.calculation) {
    html += renderFinalizedCalculation(snap);
    html += renderRestaurantFundingCard(snap);
    html += renderPeerSettlementCard(snap);
    if (state.isOrganizer) {
      html += renderSharingAndAccessSection(snap);
    }
    app.innerHTML = html;
    bindEvents(snap);
    restoreFocus();
    syncAlertContainerPlacement();
    return;
  }

  // 3. Organizer Section: Receipt Entry & Review
  if (state.isOrganizer) {
    html += renderOrganizerSection(snap);
  }

  // 4. Claims Section (Both Organizer & Diners)
  html += renderClaimsSection(snap);

  // 5. Organizer Finalize Action
  if (state.isOrganizer && !finalized) {
    const issues = snap.issues || [];
    const hasItems = Boolean(snap.receipt?.items?.length > 0);
    const hasClaimIssues = issues.includes('incomplete_quantity') || issues.includes('pending_claim');
    const canFinalize = hasItems && reviewConfirmed && issues.length === 0;

    let warningHtml = '';
    if (!reviewConfirmed) {
      warningHtml += '<div class="finalize-warning" role="status" aria-live="polite" tabindex="-1" style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Receipt must be verified before finalization.</div>';
    }
    if (!hasItems) {
      warningHtml += '<div class="finalize-warning" role="status" aria-live="polite" tabindex="-1" style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Add receipt items before finalization.</div>';
    } else if (hasClaimIssues) {
      warningHtml += '<div class="finalize-warning" role="status" aria-live="polite" tabindex="-1" style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ All items must be fully claimed before finalization.</div>';
    } else if (issues.length > 0) {
      warningHtml += `<div class="finalize-warning" role="status" aria-live="polite" tabindex="-1" style="color: var(--accent-amber); font-size: 0.85rem; margin-bottom: 8px;">⚠️ Issues detected: ${escapeHtml(issues.join(', '))}</div>`;
    }

    html += `
      <div id="finalize-section" class="card" style="border-color: ${canFinalize ? 'var(--accent-emerald)' : 'var(--border-subtle)'};">
        <h3 id="finalize-heading" class="card-title workflow-section-heading" tabindex="-1">Seal & Finalize Meal</h3>
        <p class="card-desc">Once all items are claimed and verified, finalize to lock claims and compute individual shares.</p>
        
        ${warningHtml}

        <button id="finalize-btn" class="btn btn-success btn-block" ${!canFinalize ? 'disabled' : ''}>
          Finalize & Calculate Bill
        </button>
      </div>
    `;
  }

  // 6. Persistent Organizer Sharing & Access Section
  if (state.isOrganizer) {
    html += renderSharingAndAccessSection(snap);
  }

  app.innerHTML = html;
  bindEvents(snap);
  restoreFocus();
  syncAlertContainerPlacement();
}

// --- Sub-renderers ---
function renderOrganizerSection(snap) {
  const mealId = state.mealId || snap.meal_id;
  const receipt = snap.receipt;
  const items = receipt?.items || [];
  const reviewConfirmed = Boolean(snap.review);
  const reviewer = snap.review ? snap.participants?.find(p => p.id === snap.review.participant_id) : null;
  const reviewerName = reviewer ? reviewer.name : 'Organizer';
  const shortDigest = snap.review?.receipt_digest ? snap.review.receipt_digest.slice(0, 8) : '';
  const photoUrl = state.localPhotoUrl || (snap.has_receipt_photo ? `/api/meals/${mealId}/receipt/photo` : null);
  const photoFilename = snap.receipt_photo?.filename || 'scanned_receipt.jpg';
  const photoMeta = snap.receipt_photo
    ? `${(snap.receipt_photo.byte_size / 1024).toFixed(0)} KB • ${snap.receipt_photo.width}×${snap.receipt_photo.height}px • Private Storage`
    : 'Local Source • Private Storage';
  
  let itemsRowsHtml = items.map((it, idx) => {
    const isComplimentary = it.line_sen === 0;
    const priceDisplay = isComplimentary
      ? `<span class="complimentary-badge">Complimentary · RM 0.00</span>`
      : `<span style="font-weight: 600;">${formatSen(it.line_sen)}</span>`;
    return `
    <div class="review-item-row ${isComplimentary ? 'is-complimentary' : ''}">
      <div class="review-item-label-group">
        <strong>${escapeHtml(it.label)}</strong>
        <span style="color: var(--text-dim); font-size: 0.85rem;">(x${formatRat(it.quantity)})</span>
      </div>
      <div class="review-item-price-group">${priceDisplay}</div>
    </div>
  `;
  }).join('');

  let totalsHtml = '';
  if (items.length > 0 && receipt?.subtotal_sen !== null && receipt?.subtotal_sen !== undefined) {
    let adjRows = (receipt?.adjustments || []).map(a => `
      <div style="display: flex; justify-content: space-between; font-size: 0.85rem; color: var(--text-muted); margin-bottom: 2px;">
        <span>${escapeHtml(a.label || a.kind)} ${a.scope_mode === 'all_items' ? '(all receipt items)' : '(selected items)'}
          ${a.kind === 'service' && !state.ocrCandidate ? `<details data-service-scope="${escapeHtml(a.id)}" data-financial-revision="${escapeHtml(snap.financial_revision)}"><summary>Change service charge scope</summary><small>Changing the scope changes who shares this charge; its amount stays the same and receipt review is required again.</small>
            <div>${items.map(it => `<label style="display:inline-block; margin:4px 8px 4px 0"><input type="checkbox" class="service-scope-item" data-adjustment="${escapeHtml(a.id)}" value="${escapeHtml(it.id)}" ${(a.eligible_item_ids || []).includes(it.id) ? 'checked' : ''}> ${escapeHtml(it.label)}</label>`).join('')}</div>
            <button type="button" class="btn btn-secondary btn-sm" data-action="service-fixed-items" data-adjustment="${escapeHtml(a.id)}">Apply to selected items</button>
            <button type="button" class="btn btn-secondary btn-sm" data-action="service-all-items" data-adjustment="${escapeHtml(a.id)}">Apply to all receipt items</button></details>` : ''}</span>
        <span>${formatSen(a.amount_sen)}</span>
      </div>
    `).join('');

    totalsHtml = `
      <div style="border-top: 1px solid var(--border-subtle); padding-top: 10px; margin-top: 10px;">
        <div style="display: flex; justify-content: space-between; font-size: 0.9rem; color: var(--text-muted); margin-bottom: 4px;">
          <span>Items Subtotal</span>
          <span>${formatSen(receipt.subtotal_sen)}</span>
        </div>
        ${adjRows}
        <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 1.05rem; margin-top: 4px;">
          <span>Receipt Total</span>
          <span style="color: #a7f3d0;">${formatSen(receipt.total_sen)}</span>
        </div>
      </div>
    `;
  }

  return `
    <div class="card">
      <div class="card-title">
        <span>Receipt & Charges</span>
        ${reviewConfirmed ? '<span class="badge badge-verified">Review Verified ✓</span>' : '<span class="badge badge-pending">Needs Review</span>'}
      </div>

      <div style="margin-bottom: 16px;">
        ${itemsRowsHtml || '<p style="color: var(--text-muted); font-size: 0.9rem;">No items added yet.</p>'}
        ${totalsHtml}
      </div>

      ${photoUrl ? `
        <!-- Attached Receipt Photo Card -->
        <div class="receipt-photo-card" id="receipt-photo-container">
          <div class="receipt-photo-header">
            <span class="receipt-photo-title">📷 Scanned Receipt Photo</span>
            <span class="badge badge-verified">Retained Locally</span>
          </div>
          <div class="receipt-photo-body">
            <div class="receipt-thumbnail-wrapper" id="receipt-thumb-btn" role="button" tabindex="0" title="Click to view and zoom receipt photo" aria-label="View receipt photo fullscreen">
              <img src="${escapeHtml(photoUrl)}" alt="Thumbnail of original receipt" class="receipt-thumbnail-img" id="receipt-card-thumb" />
            </div>
            <div class="receipt-photo-info">
              <span class="receipt-photo-filename">${escapeHtml(photoFilename)}</span>
              <span class="receipt-photo-meta">${photoMeta}</span>
              <div class="receipt-photo-actions">
                <button type="button" class="btn btn-secondary btn-sm" id="view-photo-modal-btn">🔍 View & Zoom</button>
                <input type="file" id="replace-photo-input" accept="image/jpeg,image/png,image/webp" style="display: none;">
                <button type="button" class="btn btn-secondary btn-sm" id="replace-photo-btn">🔄 Replace Photo</button>
                <button type="button" class="btn btn-secondary btn-sm" id="delete-photo-btn" style="color: var(--accent-rose);">🗑️ Remove Photo</button>
              </div>
            </div>
          </div>
        </div>
      ` : ''}

      <!-- Local OCR Receipt Scanner -->
      <div style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
          <span style="font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">RECEIPT SCANNER</span>
          <span style="font-size: 0.75rem; color: #a7f3d0; font-weight: 600;">Private & Local</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin-bottom: 10px;">
          Upload a receipt photo (JPEG, PNG, WebP) to automatically detect items and charges. Review and adjust everything before saving.
        </p>
        <input type="file" id="ocr-file-input" accept="image/jpeg,image/png,image/webp" style="display: none;">
        <button type="button" id="ocr-upload-btn" class="btn btn-secondary btn-sm btn-block">📷 Scan Receipt Image</button>
        <div id="ocr-spinner" style="display: none; text-align: center; margin-top: 8px; font-size: 0.85rem; color: var(--accent-indigo);">
          Scanning receipt image...
        </div>
      </div>

      ${state.ocrCandidate ? `
        <!-- Staged OCR Candidate Card with Polished Responsive Editor -->
        <div id="ocr-candidate-card" class="ocr-candidate-card">
          <div class="ocr-candidate-header">
            <span class="ocr-candidate-title">📋 SCANNED CANDIDATE (STAGED)</span>
            ${state.ocrCandidate.route === 'manual_correction'
              ? '<span class="badge ocr-badge-correction">⚠️ Needs Correction</span>'
              : '<span class="badge ocr-badge-ready">✓ Ready for Review</span>'}
          </div>
          <p class="ocr-candidate-desc" style="font-size: 0.85rem; color: var(--text-muted); margin-bottom: 12px; line-height: 1.4;">
            Review scanned items, taxes, or discounts before applying them to the receipt.
          </p>
          ${state.ocrCandidate.issues && state.ocrCandidate.issues.length > 0 ? `
            <div class="ocr-verification-note" role="alert">
              <strong>Verification Note:</strong>
              <ul style="margin: 4px 0 0 16px; padding: 0;">
                ${state.ocrCandidate.issues.map(iss => `<li>${escapeHtml(formatOcrIssue(iss, state.ocrCandidate))}</li>`).join('')}
              </ul>
            </div>
          ` : ''}
          <div class="ocr-meta-bar">
            <span>Merchant: <strong>${escapeHtml(state.ocrCandidate.merchant || 'Unknown')}</strong></span>
            <span>Confidence: <strong>${((state.ocrCandidate.mean_confidence || 0) * 100).toFixed(1)}%</strong></span>
          </div>

          ${photoUrl ? `
            <!-- Staged OCR Source Preview Bar -->
            <div class="ocr-source-preview-bar">
              <div style="display: flex; align-items: center; gap: 10px;">
                <div class="receipt-thumbnail-wrapper" style="width: 44px; height: 56px; cursor: pointer;" id="ocr-source-thumb-btn" role="button" tabindex="0" title="Click to view original source" aria-label="Zoom source receipt">
                  <img src="${escapeHtml(photoUrl)}" alt="Source receipt thumbnail" class="receipt-thumbnail-img" />
                </div>
                <div>
                  <strong style="font-size: 0.85rem; color: var(--text-main);">Original Scanned Receipt</strong>
                  <div style="font-size: 0.75rem; color: var(--text-dim);">Compare extracted items against the source photo</div>
                </div>
              </div>
              <button type="button" class="btn btn-secondary btn-sm" id="ocr-source-zoom-btn">🔍 Zoom Photo</button>
            </div>
          ` : ''}

          <!-- Section: Scanned Items -->
          <div class="ocr-section-title">
            <span>Receipt Items</span>
          </div>

          <!-- Candidate Items Table (Responsive Desktop Table + Mobile Stacked Cards) -->
          <div class="ocr-table-container">
            <table class="ocr-items-table">
              <thead>
                <tr>
                  <th class="col-item-name">Item Name</th>
                  <th class="col-qty">Qty</th>
                  <th class="col-amount">Line Total</th>
                  <th class="col-action"></th>
                </tr>
              </thead>
              <tbody id="ocr-cand-items-body">
                ${state.ocrCandidate.items.map((it, idx) => {
                  const qtyVal = Array.isArray(it.quantity) ? it.quantity[0] : (it.quantity || 1);
                  const lineSen = it.line_sen || 0;
                  const unitSen = qtyVal > 0 ? Math.round(lineSen / qtyVal) : lineSen;
                  return `
                  <tr class="ocr-cand-item-row" data-idx="${idx}">
                    <td class="cell-label">
                      <div class="ocr-mobile-only ocr-field-label">Item Name</div>
                      <input type="text" id="ocr-item-label-${idx}" class="ocr-edit-item-label form-input" data-idx="${idx}" value="${escapeHtml(it.label)}" placeholder="Item name" />
                    </td>

                    <td class="cell-qty">
                      <div class="ocr-mobile-only ocr-field-label">Qty</div>
                      <div class="ocr-qty-stepper numeric-stepper" role="group" aria-label="Item quantity">
                        <button type="button" class="ocr-qty-btn stepper-btn ocr-qty-dec" data-idx="${idx}" aria-label="Decrease quantity" ${qtyVal <= 1 ? 'disabled aria-disabled="true"' : ''}>−</button>
                        <input type="number" id="ocr-item-qty-${idx}" class="ocr-edit-item-qty stepper-input form-input" data-idx="${idx}" min="1" step="1" value="${qtyVal}" inputmode="numeric" />
                        <button type="button" class="ocr-qty-btn stepper-btn ocr-qty-inc" data-idx="${idx}" aria-label="Increase quantity">+</button>
                      </div>
                    </td>

                    <td class="cell-amount">
                      <div class="ocr-mobile-only ocr-field-label">Line Total (RM)</div>
                      <div class="ocr-amount-wrapper">
                        <span class="ocr-currency-prefix">RM</span>
                        <input type="text" id="ocr-item-price-${idx}" class="ocr-edit-item-price form-input" data-idx="${idx}" value="${(lineSen / 100).toFixed(2)}" placeholder="0.00" inputmode="decimal" title="${qtyVal > 1 ? `Estimated unit price: ~RM ${(unitSen / 100).toFixed(2)} each` : (lineSen === 0 ? 'Complimentary item (RM 0.00)' : 'Line total')}" />
                      </div>
                    </td>

                    <td class="cell-action">
                      <button type="button" class="ocr-del-btn ocr-del-item-btn" data-idx="${idx}" title="Remove item" aria-label="Remove ${escapeHtml(it.label || 'item')}">✕</button>
                    </td>
                  </tr>
                `;}).join('')}
              </tbody>
            </table>
            <div class="ocr-table-footer">
              <button type="button" id="ocr-add-item-btn" class="btn btn-secondary btn-sm">+ Add Missing Item</button>
              <span style="font-size: 0.8rem; color: var(--text-muted);">${state.ocrCandidate.items.length} item(s)</span>
            </div>
          </div>

          <!-- Section: Adjustments, Taxes & BNM Rounding -->
          <div class="ocr-adjustments-section">
            <div class="ocr-section-title">
              <span>Adjustments, Taxes & Discounts</span>
              <span class="ocr-section-hint">Discounts and rounding as negative (e.g. -0.02)</span>
            </div>
            <div class="ocr-adj-grid-header ocr-desktop-only">
              <span>Adjustment Label</span>
              <span>Type</span>
              <span style="text-align: right;">Amount (RM)</span>
              <span></span>
            </div>
            <div id="ocr-cand-adjustments-list">
              ${(state.ocrCandidate.adjustments || []).map((adj, idx) => `
                <div class="ocr-cand-adj-row" data-adj-idx="${idx}">
                  <div class="ocr-adj-field ocr-adj-field-label">
                    <div class="ocr-mobile-only ocr-field-label">Adjustment Label</div>
                    <input type="text" id="ocr-adj-label-${idx}" class="ocr-edit-adj-label form-input" data-adj-idx="${idx}" value="${escapeHtml(adj.label || '')}" placeholder="Label (e.g. Service Charge)" />
                  </div>
                  <div class="ocr-adj-field-details">
                    <div class="ocr-adj-field ocr-adj-field-kind">
                      <div class="ocr-mobile-only ocr-field-label">Type</div>
                      <select id="ocr-adj-kind-${idx}" class="ocr-edit-adj-kind form-input" data-adj-idx="${idx}">
                        <option value="service" ${adj.kind === 'service' ? 'selected' : ''}>Service Charge</option>
                        <option value="tax" ${adj.kind === 'tax' ? 'selected' : ''}>SST / Tax</option>
                        <option value="discount" ${adj.kind === 'discount' ? 'selected' : ''}>Discount</option>
                        <option value="rounding" ${adj.kind === 'rounding' ? 'selected' : ''}>BNM Rounding</option>
                      </select>
                    </div>
                    <div class="ocr-adj-field ocr-adj-field-amount">
                      <div class="ocr-mobile-only ocr-field-label">Amount (RM)</div>
                      <div class="ocr-amount-wrapper">
                        <span class="ocr-currency-prefix">RM</span>
                        <input type="text" id="ocr-adj-amount-${idx}" class="ocr-edit-adj-amount form-input" data-adj-idx="${idx}" value="${adj.kind === 'discount' ? (Math.abs(adj.amount_sen || 0) / 100).toFixed(2) : ((adj.amount_sen || 0) / 100).toFixed(2)}" placeholder="0.00" inputmode="decimal" />
                      </div>
                    </div>
                  </div>
                  <div class="ocr-adj-field ocr-adj-field-action">
                    <button type="button" class="ocr-del-btn ocr-del-adj-btn" data-adj-idx="${idx}" title="Remove adjustment" aria-label="Remove adjustment ${escapeHtml(adj.label || '')}">✕</button>
                  </div>
                  <div>
                    <label>Applies to <select class="ocr-adj-scope form-input" data-adj-idx="${idx}">
                      <option value="all_items" ${adj.scope_mode === 'all_items' ? 'selected' : ''}>All receipt items, including later additions</option>
                      <option value="fixed" ${adj.scope_mode !== 'all_items' ? 'selected' : ''}>Selected items only</option>
                    </select></label>
                    ${adj.kind === 'service' ? '<small>Check this scope against the printed receipt; scanning cannot determine item-specific charges.</small>' : ''}
                    <div>${state.ocrCandidate.items.map(it => `<label style="display:inline-block; margin:4px 8px 4px 0"><input type="checkbox" class="ocr-scope-item" data-adj-idx="${idx}" value="${escapeHtml(it.id)}" ${adj.scope_mode === 'all_items' || (adj.eligible_item_ids || []).includes(it.id) ? 'checked' : ''} ${adj.scope_mode === 'all_items' ? 'disabled' : ''}> ${escapeHtml(it.label)}</label>`).join('')}</div>
                  </div>
                </div>
              `).join('')}
            </div>
            <div class="ocr-adj-add-bar">
              <button type="button" id="ocr-add-adj-btn" class="btn btn-secondary btn-sm">+ Add Fee / Tax / Rounding</button>
            </div>

            <!-- Tax-inclusive Included SST -->
            <div class="ocr-included-tax-bar">
              <span>Included SST (tax-inclusive, informational):</span>
              <div class="ocr-amount-wrapper" style="width: 120px;">
                <span class="ocr-currency-prefix">RM</span>
                <input type="text" id="ocr-edit-included-tax" class="form-input" value="${((state.ocrCandidate.included_tax_sen || 0) / 100).toFixed(2)}" placeholder="0.00" inputmode="decimal" />
              </div>
            </div>

            <!-- Dynamic Recalculated Totals Display -->
            <div class="ocr-totals-card">
              <div class="ocr-total-row">
                <span class="ocr-total-label">Candidate Subtotal (sum of line totals):</span>
                <span id="ocr-cand-subtotal-val" class="ocr-total-val">${formatSen(state.ocrCandidate.subtotal_sen)}</span>
              </div>
              <div class="ocr-total-row ocr-total-final">
                <span>Candidate Final Total:</span>
                <span id="ocr-cand-total-val" class="ocr-total-val-highlight">${formatSen(state.ocrCandidate.total_sen)}</span>
              </div>
            </div>
          </div>

          ${snap.receipt && snap.receipt.items && snap.receipt.items.length > 0 ? `
            <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-sm); padding: 8px 12px; margin-bottom: 12px; font-size: 0.8rem; color: #fde68a;">
              ⚠️ Applying candidate will replace the ${snap.receipt.items.length} existing items on the draft receipt.
            </div>
          ` : ''}
          <div style="display: flex; gap: 10px; flex-wrap: wrap;">
            <button type="button" id="ocr-accept-btn" class="btn btn-primary" style="flex: 2; min-height: 48px; font-size: 1rem;">Accept & Apply to Receipt</button>
            <button type="button" id="ocr-discard-btn" class="btn btn-secondary" style="flex: 1; min-height: 48px; font-size: 1rem;">Discard</button>
          </div>
        </div>
      ` : ''}

      <!-- Add Item Form (Paused during active OCR candidate staging to prevent competing draft mutations) -->
      ${state.ocrCandidate ? `
        <div class="ocr-staging-active-notice" style="background: var(--bg-main); border: 1px dashed var(--border-subtle); padding: 12px 16px; border-radius: var(--radius-md); margin-bottom: 16px; font-size: 0.85rem; color: var(--text-muted); text-align: center;">
          <span>Staged receipt review in progress. Accept or discard the scanned candidate above before adding manual items.</span>
        </div>
      ` : `
        <!-- Add Item Form -->
        <form id="add-item-form" style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md); margin-bottom: 16px;">
          <div style="font-weight: 600; font-size: 0.85rem; margin-bottom: 8px; color: var(--text-muted);">ADD RECEIPT ITEM</div>
          <div class="add-item-grid">
            <input type="text" id="new-item-label" placeholder="Item name" required>
            <div class="numeric-stepper" role="group" aria-label="Item quantity">
              <button type="button" class="stepper-btn" id="new-item-qty-dec" aria-label="Decrease quantity" disabled>−</button>
              <input type="number" id="new-item-qty" class="stepper-input" value="1" min="1" step="1" required aria-label="Item quantity">
              <button type="button" class="stepper-btn" id="new-item-qty-inc" aria-label="Increase quantity">+</button>
            </div>
            <input type="text" id="new-item-price" placeholder="RM 0.00" inputmode="decimal" required>
          </div>
          <button type="submit" class="btn btn-secondary btn-sm btn-block">+ Add Item</button>
        </form>
      `}

      <!-- Review & Verification Card -->
      <div id="review-section" class="review-section" style="background: var(--bg-main); padding: 14px; border-radius: var(--radius-md);">
        <div id="review-heading" class="review-heading workflow-section-heading" style="font-weight: 600; font-size: 0.85rem; margin-bottom: 8px; color: var(--text-muted);" tabindex="-1">VERIFY RECEIPT TOTALS</div>
        <p style="font-size: 0.85rem; color: var(--text-dim); margin-bottom: 10px;">
          Check that items and totals match the paper bill before finalization.
        </p>
        <label class="review-confirm-label">
          <input type="checkbox" id="review-confirm-check" ${reviewConfirmed ? 'checked disabled' : ''} ${state.ocrCandidate && !reviewConfirmed ? 'disabled title="Accept or discard staged candidate before confirming physical bill"' : ''}>
          <span>I confirm totals match the physical bill.</span>
        </label>
        ${state.ocrCandidate && !reviewConfirmed ? `
          <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px;">
            ⚠️ Accept or discard the scanned candidate above before verifying and sealing the receipt.
          </div>
        ` : ''}
        ${!reviewConfirmed ? `
          <button id="review-submit-btn" class="btn btn-primary btn-sm btn-block" style="margin-top: 10px;" ${state.ocrCandidate ? 'disabled' : ''}>
            Approve & Seal Receipt
          </button>
        ` : `
          <div id="receipt-verified-status" class="receipt-verified-banner" role="status" aria-live="polite">
            <span class="verified-icon" aria-hidden="true">✓</span>
            <div class="verified-details">
              <div class="verified-heading">Receipt Verified & Sealed</div>
              <div class="verified-subtext">
                Totals confirmed by ${escapeHtml(reviewerName)} &bull; Verification ID <code>${escapeHtml(shortDigest)}</code>
              </div>
            </div>
          </div>
        `}
      </div>
    </div>

  `;
}

function renderSharingAndAccessSection(snap) {
  const isFinalized = Boolean(snap.finalized);
  const isExported = Boolean(state.notionExport && (state.notionExport.status === 'completed' || state.notionExport.status === 'already_exported'));
  const notionPublicUrl = snap.notion_public_url || state.notionExport?.public_url || '';

  return `
    <div class="card" id="sharing-access-section" style="border-color: rgba(99, 102, 241, 0.4); margin-top: 1.5rem;">
      <div id="sharing-access-heading" class="card-title workflow-section-heading" style="color: #818cf8; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;" tabindex="-1">
        <span>👥 Sharing & Access Hub</span>
        <span class="badge" style="background: rgba(99, 102, 241, 0.15); color: #818cf8; font-size: 0.72rem;">Organizer Only</span>
      </div>
      <p class="card-desc" style="margin-bottom: 14px;">
        Manage diner invitations, Notion report sharing, and organizer recovery.
      </p>

      <!-- 1. Invite Diners to Meal -->
      <div id="invitation-hub-card" class="sharing-subsection" style="background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px; margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
          <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-heading);">
            1. Invite Diners to Meal (Diner Access)
          </div>
          <span class="badge" style="font-size: 0.7rem; background: rgba(59, 130, 246, 0.15); color: #60a5fa;">Diner Permissions</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin: 0 0 10px 0; line-height: 1.4;">
          Invite dining companions to view items, claim portions, and see their share.
        </p>

        <!-- General Table Join Link Box -->
        <div style="background: var(--surface-primary); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 10px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
            <div>
              <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-heading);">🔗 General Table Join Link</div>
              <div style="font-size: 0.78rem; color: var(--text-dim);">Share with any diner; they enter their name and wait for your one-click approval.</div>
            </div>
            <button id="copy-general-join-btn" class="btn btn-secondary btn-sm" data-meal="${escapeHtml(snap.meal_id)}">
              📋 Copy Join Link
            </button>
          </div>
        </div>

        <!-- Pending Join Requests Queue -->
        ${renderPendingJoinRequests(snap)}

        <div style="font-size: 0.85rem; font-weight: 600; color: var(--text-heading); margin-bottom: 6px;">
          Personal One-Time Invitation Links
        </div>
        <div id="invitation-list">
          ${renderInvitationList(snap)}
        </div>
      </div>

      <!-- 2. Share Notion Report -->
      <div id="sharing-notion-card" class="sharing-subsection" style="background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px; margin-bottom: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
          <div style="font-weight: 700; font-size: 0.9rem; color: var(--text-heading);">
            2. Share Notion Report (Read-Only Document)
          </div>
          <span class="badge" style="font-size: 0.7rem; background: rgba(16, 185, 129, 0.15); color: #10b981;">View-Only Document</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin: 0 0 10px 0; line-height: 1.4;">
          Share a view-only Notion summary for expense records and receipts.
        </p>

        ${!isFinalized ? `
          <div style="font-size: 0.8rem; color: var(--text-muted); padding: 8px; border-radius: 4px; background: var(--surface-primary);">
            🔒 Notion report export becomes available after the meal is finalized.
          </div>
        ` : !isExported ? `
          <div style="font-size: 0.8rem; color: var(--text-muted); padding: 8px; border-radius: 4px; background: var(--surface-primary); display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px;">
            <span>Meal is finalized. Export to Notion in the summary section above to generate a shareable report.</span>
            <button type="button" class="btn btn-secondary btn-sm" id="jump-to-notion-export-btn">Go to Notion Export ↑</button>
          </div>
        ` : `
          <div style="background: var(--surface-primary); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 10px;">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 6px; margin-bottom: 6px;">
              <span style="font-size: 0.85rem; font-weight: 600; color: ${notionPublicUrl ? '#10b981' : 'var(--text-dim)'};">
                ${notionPublicUrl ? '✓ Active: Shared with Diners' : '🔒 Private: Not Shared with Diners'}
              </span>
              <button type="button" class="btn btn-secondary btn-sm" id="jump-to-notion-card-btn" style="font-size: 0.75rem;">Manage in Notion Section ↑</button>
            </div>
            ${notionPublicUrl ? `
              <div style="font-size: 0.78rem; word-break: break-all; color: var(--text-muted);">
                Link: <a href="${escapeHtml(notionPublicUrl)}" target="_blank" rel="noopener noreferrer" style="color: #6ee7b7;">${escapeHtml(notionPublicUrl)} ↗</a>
              </div>
            ` : `
              <div style="font-size: 0.78rem; color: var(--text-dim);">
                Export complete. Use "Share Exported Report with Diners" in the Notion section above to share access.
              </div>
            `}
          </div>
        `}
      </div>

      <!-- 3. Emergency Organizer Recovery Link -->
      <div id="sharing-recovery-card" class="sharing-subsection" style="background: var(--bg-main); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
          <div style="font-weight: 700; font-size: 0.9rem; color: var(--accent-rose);">
            3. Organizer Session Recovery (Administrative Control)
          </div>
          <span class="badge" style="font-size: 0.7rem; background: rgba(239, 68, 68, 0.15); color: #f87171;">⚠️ Secret Key</span>
        </div>
        <p style="font-size: 0.8rem; color: var(--text-dim); margin: 0 0 10px 0; line-height: 1.4;">
          Restores full organizer control without an account. <strong>NEVER share with diners or paste into public chats or Notion.</strong>
        </p>
        <div style="background: var(--surface-primary); border: 1px solid var(--border-subtle); border-radius: var(--radius-sm); padding: 10px;">
          <div style="display: flex; justify-content: space-between; align-items: center; gap: 8px; flex-wrap: wrap;">
            <div>
              <div style="font-weight: 600; font-size: 0.85rem; color: var(--text-heading);">🛡️ Emergency Recovery Link</div>
              <div style="font-size: 0.78rem; color: var(--text-dim);">Save in your private notes. If cookies expire or are cleared, opening it restores your organizer session.</div>
            </div>
            <button id="gen-recovery-link-btn" class="btn btn-secondary btn-sm" data-meal="${escapeHtml(snap.meal_id)}">
              ${state.recoveryLink ? '📋 Copy Recovery Link' : '🔑 Create Recovery Link'}
            </button>
          </div>
          <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-dim); line-height: 1.3;">
            🔄 <em>Accidentally disclosed?</em> Clicking "Create Recovery Link" creates a fresh recovery link and immediately revokes all previous recovery links.
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderPendingJoinRequests(snap) {
  const pending = snap.join_requests?.filter(r => r.status === 'pending') || [];
  if (pending.length === 0) {
    return '';
  }

  return `
    <div id="pending-join-requests-container" style="background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: var(--radius-md); padding: 12px; margin-bottom: 16px;">
      <div style="font-weight: 700; font-size: 0.85rem; color: #f59e0b; margin-bottom: 8px; display: flex; align-items: center; gap: 6px;">
        <span>🔔 Pending Diner Join Requests (${pending.length})</span>
      </div>
      <div style="display: flex; flex-direction: column; gap: 8px;">
        ${pending.map(r => `
          <div style="display: flex; justify-content: space-between; align-items: center; background: var(--bg-card); padding: 8px 12px; border-radius: var(--radius-sm); border: 1px solid var(--border-subtle); flex-wrap: wrap; gap: 8px;">
            <div>
              <span style="font-weight: 600;">${escapeHtml(r.display_name)}</span>
              <span style="font-size: 0.75rem; color: var(--text-dim); margin-left: 6px;">wants to join as diner</span>
            </div>
            <div style="display: flex; gap: 6px;">
              <button class="btn btn-success btn-sm approve-join-req-btn" data-req="${escapeHtml(r.id)}" style="padding: 4px 10px; font-size: 0.8rem; min-height: 32px;">
                Approve
              </button>
              <button class="btn btn-secondary btn-sm reject-join-req-btn" data-req="${escapeHtml(r.id)}" style="padding: 4px 10px; font-size: 0.8rem; min-height: 32px;">
                Decline
              </button>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
}

function renderInvitationList(snap) {
  const diners = snap.participants?.filter(p => !p.organizer) || [];
  if (diners.length === 0) {
    return '<p style="color: var(--text-dim); font-size: 0.85rem;">No other diners declared in this meal room.</p>';
  }

  const now = Math.floor(Date.now() / 1000);

  return diners.map(d => {
    const dinInvs = (snap.invitations || []).filter(i => i.participant_id === d.id);
    const hasConsumed = dinInvs.some(i => i.consumed);
    const activeInv = dinInvs.find(i => !i.revoked && !i.consumed && i.expires > now);
    const expiredInv = !activeInv && !hasConsumed ? dinInvs.find(i => !i.revoked && !i.consumed && i.expires <= now) : null;
    const cachedUrl = state.issuedTokens[d.id];

    let actionHtml = '';

    if (hasConsumed) {
      actionHtml = '<span class="badge badge-verified">Joined ✓</span>';
    } else if (activeInv) {
      if (cachedUrl) {
        actionHtml = `
          <div style="display: flex; gap: 6px; align-items: center;">
            <button class="btn btn-primary btn-sm copy-invite-btn" data-part="${d.id}" title="Copy Invite Link">
              📋 Copy Link
            </button>
            <button class="btn btn-secondary btn-sm revoke-invite-btn" data-part="${d.id}" title="Revoke Link" style="color: var(--accent-rose); padding: 2px 8px; font-size: 0.75rem;">
              Revoke
            </button>
          </div>
        `;
      } else {
        actionHtml = `
          <div style="display: flex; gap: 6px; align-items: center; flex-wrap: wrap;">
            <span class="badge" style="background: rgba(99, 102, 241, 0.15); color: #818cf8; font-size: 0.72rem;">Active (link not cached)</span>
            <button class="btn btn-secondary btn-sm reissue-invite-btn" data-part="${d.id}" title="Revoke lost link and create fresh invitation">
              🔄 Revoke & Reissue
            </button>
          </div>
        `;
      }
    } else if (expiredInv) {
      actionHtml = `
        <div style="display: flex; gap: 6px; align-items: center;">
          <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Expired</span>
          <button class="btn btn-secondary btn-sm issue-invite-btn" data-id="${d.id}">
            🔄 Reissue Link
          </button>
        </div>
      `;
    } else {
      actionHtml = `
        <button class="btn btn-secondary btn-sm issue-invite-btn" data-id="${d.id}">
          Create Link
        </button>
      `;
    }

    return `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); flex-wrap: wrap; gap: 6px;">
        <span style="font-weight: 600;">${escapeHtml(d.name)}</span>
        <div>${actionHtml}</div>
      </div>
    `;
  }).join('');
}

function openItemEditor(itemId, trigger = document.activeElement) {
  if (window.innerWidth < 768) {
    sheetTrigger = focusDescriptor(trigger);
    state.activeMobileSheetItemId = itemId;
  } else {
    state.expandedHybridItemIds.add(itemId);
  }
  updateMealUI();
}

function toggleItemEditor(itemId, trigger = document.activeElement) {
  if (window.innerWidth < 768) {
    if (state.activeMobileSheetItemId === itemId) {
      state.activeMobileSheetItemId = null;
    } else {
      sheetTrigger = focusDescriptor(trigger);
      state.activeMobileSheetItemId = itemId;
    }
  } else {
    if (state.expandedHybridItemIds.has(itemId)) {
      state.expandedHybridItemIds.delete(itemId);
    } else {
      state.expandedHybridItemIds.add(itemId);
    }
  }
  updateMealUI();
}

async function executeSetItemAllocations(itemId, allocations, expectedItemRevision) {
  const snap = state.snapshot;
  if (!snap || !snap.meal_id) return;
  if (state.allocationConflictPending) {
    showAlert('⚠️ Allocation Conflict: Refresh failed. Check your connection or session, close Details / Split if open, then use the refresh button to retry.', 'conflict');
    return;
  }

  const payload = {
    command_id: `alloc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    kind: 'SetItemAllocations',
    item_id: itemId,
    allocations: allocations,
    expected_item_revision: expectedItemRevision,
    expected_financial_revision: snap.financial_revision,
  };

  state.mutationActive = true;
  try {
    await apiCall(`/api/meals/${snap.meal_id}/apply`, 'POST', payload);
    state.mutationActive = false;
    await fetchSnapshot(true);
  } catch (err) {
    state.mutationActive = false;
    if (err.status === 409 || err.code === 'item_revision_conflict' || err.code === 'financial_revision_conflict' || err.code === 'revision_conflict') {
      state.allocationConflictPending = true;
      showAlert('⚠️ Allocation Conflict: Another diner or organizer modified this item or receipt. Refreshing latest state…', 'conflict');
      await fetchSnapshot(true);
    } else if (err.code === 'quantity_capacity') {
      showAlert('⚠️ Capacity Exceeded: Total allocated quantity cannot exceed item quantity.', 'error');
    } else if (err.code === 'forbidden') {
      showAlert('⚠️ Forbidden: Only the meal organizer can modify participant allocations.', 'error');
    } else {
      handleApiError(err, itemId);
    }
  } finally {
    state.mutationActive = false;
  }
}

function renderHybridDetailContent(item, snap, activeParts, isModal = false) {
  if (item.line_sen === 0) {
    return `
      <div style="padding: 12px; text-align: center; color: var(--text-muted); font-size: 0.9rem;">
        This item is complimentary (RM 0.00) and does not require diner allocation.
      </div>
      <div class="hybrid-drawer-footer" style="display: flex; justify-content: flex-end; margin-top: 12px;">
        <button type="button" class="btn btn-secondary btn-sm" data-action="${isModal ? 'close-sheet' : 'hybrid-close-details'}" data-item="${item.id}">
          ✓ Close
        </button>
      </div>
    `;
  }
  const claims = snap.claims?.filter(c => c.item_id === item.id) || [];
  const stateItem = snap.items?.find(i => i.item_id === item.id);
  const itemRevision = stateItem ? stateItem.item_revision : 0;
  const itemTotalQty = ratToNum(item.quantity);

  const provisionalShares = apportionItemBase(item.line_sen, claims, item.id, item.quantity);

  if (!state.selectedSplitDiners.has(item.id)) {
    state.selectedSplitDiners.set(item.id, new Set(activeParts.map(p => p.id)));
  }
  const splitSet = state.selectedSplitDiners.get(item.id);
  const selectedCount = splitSet.size;

  let splitDesc = '';
  if (selectedCount > 0) {
    const shareRat = makeReducedFraction(itemTotalQty, selectedCount);
    const eachSen = Math.round(item.line_sen / selectedCount);
    splitDesc = `Split among ${selectedCount} diners → <strong>${formatRat(shareRat)} portion</strong> each (~${formatSen(eachSen)} base)`;
  } else {
    splitDesc = 'Select diners below to split equally';
  }

  let overwriteWarningHtml = '';
  if (claims.length > 0) {
    const existingList = claims.map(c => {
      const p = activeParts.find(part => part.id === c.participant_id);
      return `${p ? p.name : c.participant_id} (${formatRat(c.quantity)})`;
    }).join(', ');
    overwriteWarningHtml = `
      <div class="split-affected-warning">
        <strong>⚠️ Note:</strong> Applying equal split will replace current allocations: <em>${escapeHtml(existingList)}</em>.
      </div>
    `;
  }

  const selectorToggles = activeParts.map(p => {
    const isSel = splitSet.has(p.id);
    return `
      <label class="subset-diner-toggle ${isSel ? 'is-selected' : ''}">
        <input type="checkbox" data-action="toggle-split-diner" data-item="${item.id}" data-target="${p.id}" ${isSel ? 'checked' : ''}>
        <span>${p.organizer ? '👑' : '🍽️'} ${escapeHtml(p.name)}</span>
      </label>
    `;
  }).join('');

  const dinerRows = activeParts.map(p => {
    const claim = claims.find(c => c.participant_id === p.id);
    const currentRat = claim ? claim.quantity : [0, 1];
    const currentQty = ratToNum(currentRat);
    const dinerSen = currentQty > 0 ? (provisionalShares.get(p.id) || 0) : 0;

    const otherClaimsForP = claims.filter(c => c.participant_id !== p.id);
    const otherSumRatForP = otherClaimsForP.reduce((acc, c) => addFractions(acc, c.quantity), 0);
    const remForP = subtractFractions(item.quantity, otherSumRatForP);
    const remQtyForP = ratToNum(remForP);
    const isAllDisabled = remQtyForP <= 0 || (currentQty >= remQtyForP && currentQty > 0);

    return `
      <div class="diner-allocation-row">
        <div class="diner-row-header">
          <div class="diner-name-col">
            <span>${p.organizer ? '👑' : '🍽️'}</span>
            <span>${escapeHtml(p.name)}</span>
          </div>
          <span class="diner-portion-badge ${currentQty > 0 ? 'is-active' : ''}">${formatRat(currentRat)} portion</span>
          <span class="diner-share-preview" title="Provisional item base share. Taxes, service charge, discounts, and rounding are apportioned at finalization.">${currentQty > 0 ? `~${formatSen(dinerSen)} base` : 'RM 0.00'}</span>
        </div>
        <div class="diner-row-controls">
          <div class="quantity-stepper numeric-stepper" role="group" aria-label="Portion for ${escapeHtml(p.name)}">
            <button type="button" class="btn btn-secondary btn-sm stepper-btn hybrid-step-btn" data-action="hybrid-step" data-step="-1" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" ${currentQty <= 0 ? 'disabled' : ''} aria-label="Decrease portion for ${escapeHtml(p.name)}">−</button>
            <span class="step-val" aria-live="polite">${formatRat(currentRat)}</span>
            <button type="button" class="btn btn-secondary btn-sm stepper-btn hybrid-step-btn" data-action="hybrid-step" data-step="1" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" aria-label="Increase portion for ${escapeHtml(p.name)}">+</button>
          </div>
          <div class="fraction-btn-group">
            <button type="button" class="btn-fraction" data-action="hybrid-fraction" data-frac="1/3" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" title="Set 1/3 portion" aria-label="Set 1/3 portion for ${escapeHtml(p.name)}">⅓</button>
            <button type="button" class="btn-fraction" data-action="hybrid-fraction" data-frac="1/2" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" title="Set 1/2 portion" aria-label="Set 1/2 portion for ${escapeHtml(p.name)}">½</button>
            <button type="button" class="btn-fraction" data-action="hybrid-fraction" data-frac="all" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" ${isAllDisabled ? 'disabled' : ''} title="${isAllDisabled ? 'No unassigned portion remains' : 'Set remaining portion'}" aria-label="Set remaining portion for ${escapeHtml(p.name)}">All</button>
            <button type="button" class="btn-fraction btn-fraction-clear" data-action="hybrid-fraction" data-frac="0" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" ${currentQty <= 0 ? 'disabled' : ''} title="Remove assignment" aria-label="Remove assignment for ${escapeHtml(p.name)}">✕</button>
          </div>
        </div>
      </div>
    `;
  }).join('');

  return `
    <div class="subset-split-panel">
      <div class="subset-split-header">
        <div class="subset-split-title">⚡ Selective Equal Split</div>
        <div class="subset-split-formula">${splitDesc}</div>
      </div>

      ${overwriteWarningHtml}

      <div class="subset-diners-grid">
        ${selectorToggles}
      </div>

      <div class="subset-action-bar">
        <div class="subset-helpers">
          <button type="button" class="btn btn-ghost btn-sm" data-action="split-select-all" data-item="${item.id}">Select All</button>
          <button type="button" class="btn btn-ghost btn-sm" data-action="split-clear-all" data-item="${item.id}">Clear</button>
        </div>
        <button type="button" class="btn btn-primary btn-sm" data-action="apply-equal-split" data-item="${item.id}" data-rev="${itemRevision}" ${selectedCount === 0 ? 'disabled' : ''}>
          ⚡ Apply Equal Split (${selectedCount})
        </button>
      </div>
    </div>

    <div class="diner-allocation-section-title">
      <span>Per-Diner Exact Portions &amp; Base Share</span>
      <span class="diner-allocation-section-hint">Provisional item base • Taxes and service charge apportioned at finalization</span>
    </div>
    <div class="diner-allocation-table">
      ${dinerRows}
    </div>

    <div class="hybrid-footer-actions">
      <button type="button" class="btn btn-danger-ghost btn-sm" data-action="hybrid-clear-item" data-item="${item.id}" data-rev="${itemRevision}" ${claims.length === 0 ? 'disabled' : ''}>
        🗑️ Clear All Claims
      </button>
      <button type="button" class="btn btn-secondary btn-sm" data-action="${isModal ? 'close-sheet' : 'hybrid-close-details'}" data-item="${item.id}">
        ✓ Done
      </button>
    </div>
  `;
}

function renderClaimsSection(snap) {
  const receipt = snap.receipt;
  const items = receipt?.items || [];
  if (items.length === 0) {
    return `
      <div id="allocation-section" class="card">
        <h3 id="allocation-heading" class="card-title workflow-section-heading" tabindex="-1">${snap.is_organizer ? 'Item Allocation' : 'Item Claims'}</h3>
        <p class="card-desc">No receipt items to claim. The organizer must add items first.</p>
      </div>
    `;
  }

  const activeParts = snap.participants?.filter(p => !snap.inactive_participant_ids?.includes(p.id)) || [];

  // 1. DINER VIEW: Preserved untouched
  if (!snap.is_organizer) {
    const itemsHtml = items.map(item => {
      const stateItem = snap.items?.find(i => i.item_id === item.id);
      const itemRevision = stateItem ? stateItem.item_revision : 0;
      const isComplimentary = item.line_sen === 0;
      const claims = snap.claims?.filter(c => c.item_id === item.id) || [];
      const targetClaim = claims.find(c => c.participant_id === state.currentUserId);
      const targetQty = targetClaim ? (Array.isArray(targetClaim.quantity) ? targetClaim.quantity[0]/targetClaim.quantity[1] : targetClaim.quantity) : 0;

      const totalClaimed = claims.reduce((acc, c) => acc + ratToNum(c.quantity), 0);
      const itemTotalQty = ratToNum(item.quantity);
      const pct = Math.min(100, Math.round((totalClaimed / itemTotalQty) * 100));
      const unassigned = Math.max(0, itemTotalQty - totalClaimed);

      let statusBadge = '';
      if (isComplimentary) {
        statusBadge = '<span class="badge badge-complimentary">Complimentary · No allocation needed</span>';
      } else if (Math.abs(totalClaimed - itemTotalQty) < 0.0001) {
        statusBadge = '<span class="badge badge-verified">✓ Fully Allocated</span>';
      } else if (totalClaimed < itemTotalQty) {
        statusBadge = `<span class="badge badge-pending">⚠️ ${unassigned} unassigned</span>`;
      } else {
        statusBadge = '<span class="badge" style="background: rgba(244,63,94,0.2); color: #fecdd3; border: 1px solid var(--accent-rose);">⚠️ Over-allocated</span>';
      }

      const chipsHtml = claims.map(c => {
        const p = snap.participants?.find(part => part.id === c.participant_id);
        const name = p ? p.name : c.participant_id;
        const isSelected = c.participant_id === state.currentUserId;
        const qStr = formatRat(c.quantity);
        let badgeLabel = '';
        if (c.assigned_by && c.assigned_by !== c.participant_id) {
          badgeLabel = ' <span style="font-size: 0.68rem; color: #a5b4fc;">(Organizer Assigned)</span>';
        } else if (!p?.organizer) {
          badgeLabel = ' <span style="font-size: 0.68rem; color: #6ee7b7;">(Diner Claim)</span>';
        }
        return `<span class="chip ${isSelected ? 'own-chip' : ''}">${escapeHtml(name)}: ${qStr}${badgeLabel}</span>`;
      }).join('');

      const priceDisplay = isComplimentary
        ? '<span class="complimentary-badge">Complimentary · RM 0.00</span>'
        : formatSen(item.line_sen);

      const metaDisplay = isComplimentary
        ? `Total Qty: ${itemTotalQty} &bull; ${statusBadge}`
        : `Total: ${itemTotalQty} &bull; Allocated: ${totalClaimed} / ${itemTotalQty} &bull; ${statusBadge}`;

      const progressBarHtml = isComplimentary ? '' : `
        <div class="progress-bar-wrap">
          <div class="progress-bar-fill ${totalClaimed > itemTotalQty ? 'overclaimed' : ''}" style="width: ${pct}%"></div>
        </div>
      `;

      const actionsHtml = isComplimentary ? `
        <div style="font-size: 0.85rem; color: var(--text-muted); padding: 4px 0;">
          Complimentary receipt record. No diner allocation needed.
        </div>
      ` : `
        <div class="claim-actions">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="font-size: 0.85rem; font-weight: 600; color: var(--text-muted);">Your Portion:</span>
            <div class="quantity-stepper numeric-stepper" role="group" aria-label="Your portion">
              <button type="button" class="btn btn-secondary btn-sm stepper-btn claim-dec-btn" data-id="${item.id}" data-current="${targetQty}" data-target="${state.currentUserId}" data-rev="${itemRevision}" aria-label="Decrease portion" ${targetQty <= 0 ? 'disabled' : ''}>−</button>
              <span class="step-val" aria-live="polite">${targetQty}</span>
              <button type="button" class="btn btn-secondary btn-sm stepper-btn claim-inc-btn" data-id="${item.id}" data-current="${targetQty}" data-target="${state.currentUserId}" data-rev="${itemRevision}" aria-label="Increase portion" ${targetQty >= itemTotalQty ? 'disabled' : ''}>+</button>
            </div>
          </div>
          <div>
            <button class="btn btn-secondary btn-sm claim-all-btn" data-id="${item.id}" data-target="${state.currentUserId}" data-rev="${itemRevision}" data-total="${itemTotalQty}" data-unassigned="${unassigned}">
              Claim All
            </button>
          </div>
        </div>
      `;

      return `
        <div class="item-card ${isComplimentary ? 'is-complimentary' : ''}" id="item-card-${item.id}" data-item-id="${item.id}" data-revision="${itemRevision}">
          <div class="item-header">
            <div>
              <div class="item-label">${escapeHtml(item.label)}</div>
              <div class="item-meta">${metaDisplay}</div>
            </div>
            <div class="item-price">${priceDisplay}</div>
          </div>

          ${progressBarHtml}
          ${actionsHtml}
          ${chipsHtml ? `<div class="chips-row">${chipsHtml}</div>` : ''}
        </div>
      `;
    }).join('');

    return `
      <div id="allocation-section" class="card">
        <h3 id="allocation-heading" class="card-title workflow-section-heading" tabindex="-1">Claim Your Portions</h3>
        <p class="card-desc">Tap + or - to set your claimed portion for each item. Overlapping claims split the cost.</p>
        ${itemsHtml}
      </div>
    `;
  }

  // 2. ORGANIZER VIEW: Concept C (Unified Expandable Hybrid)
  const itemsHtml = items.map(item => {
    const stateItem = snap.items?.find(i => i.item_id === item.id);
    const itemRevision = stateItem ? stateItem.item_revision : 0;
    const isComplimentary = item.line_sen === 0;
    const claims = snap.claims?.filter(c => c.item_id === item.id) || [];

    const totalClaimedRat = claims.reduce((acc, c) => addFractions(acc, c.quantity), 0);
    const totalClaimed = ratToNum(totalClaimedRat);
    const itemTotalQty = ratToNum(item.quantity);
    const isComplete = Math.abs(totalClaimed - itemTotalQty) < 0.0001;
    const isOver = totalClaimed > itemTotalQty;
    const unassignedRat = subtractFractions(item.quantity, totalClaimedRat);
    const canQuickAssign = ratToNum(unassignedRat) >= 1;
    const quickAssignHelp = ratToNum(unassignedRat) <= 0
      ? 'Fully allocated. Use Details / Split to reallocate.'
      : 'Less than 1 portion remains. Use Details / Split for exact fractions.';
    const pct = Math.min(100, Math.round((totalClaimed / itemTotalQty) * 100));
    const isExpanded = state.expandedHybridItemIds.has(item.id);

    let statusBadge = '';
    let cardStatusClass = 'is-unassigned';
    if (isComplimentary) {
      statusBadge = '<span class="badge badge-complimentary">Complimentary · No allocation needed</span>';
      cardStatusClass = 'is-complimentary';
    } else if (isComplete) {
      statusBadge = '<span class="badge badge-verified">✓ Fully Allocated</span>';
      cardStatusClass = 'is-complete';
    } else if (isOver) {
      statusBadge = '<span class="badge badge-danger">⚠️ Over-allocated</span>';
      cardStatusClass = 'is-over';
    } else {
      statusBadge = `<span class="badge badge-pending">⚠️ ${formatRat(unassignedRat)} unassigned</span>`;
      cardStatusClass = 'is-unassigned';
    }

    const priceDisplay = isComplimentary
      ? '<span class="complimentary-badge">Complimentary · RM 0.00</span>'
      : formatSen(item.line_sen);

    const metaDisplay = isComplimentary
      ? `Total Qty: ${itemTotalQty} &bull; ${statusBadge}`
      : `Total Qty: ${itemTotalQty} &bull; Allocated: ${formatRat(totalClaimedRat)} / ${itemTotalQty} &bull; ${statusBadge}`;

    const progressBarHtml = isComplimentary ? '' : `
      <div class="progress-bar-wrap">
        <div class="progress-bar-fill ${isOver ? 'overclaimed' : ''}" style="width: ${pct}%"></div>
      </div>
    `;

    const clusterHtml = isComplimentary ? `
      <div class="complimentary-notice" style="font-size: 0.85rem; color: var(--text-muted); padding: 6px 0;">
        Complimentary receipt record. No allocation needed.
      </div>
    ` : `
      <div class="hybrid-pill-cluster">
        ${activeParts.map(p => {
          const claim = claims.find(c => c.participant_id === p.id);
          const claimedQty = claim ? ratToNum(claim.quantity) : 0;
          const isClaimed = claimedQty > 0;
          const qStr = claim ? formatRat(claim.quantity) : '0';

          if (!isClaimed) {
            const title = canQuickAssign
              ? `Assign 1 portion to ${escapeHtml(p.name)}`
              : `Quick assignment unavailable for ${escapeHtml(p.name)}. ${quickAssignHelp}`;
            return `
              <button type="button" class="hybrid-pill hybrid-pill-available" data-action="hybrid-quick-assign" data-item="${item.id}" data-target="${p.id}" data-rev="${itemRevision}" title="${title}" ${canQuickAssign ? '' : `disabled aria-describedby="quick-assign-help-${item.id}"`}>
                <span class="pill-plus">+</span>
                <span class="pill-avatar">${p.organizer ? '👑' : '🍽️'}</span>
                <span class="pill-name">${escapeHtml(p.name)}</span>
              </button>
            `;
          } else {
            const isOrgAssigned = Boolean(claim.assigned_by && claim.assigned_by !== claim.participant_id);
            const title = `${escapeHtml(p.name)}: allocated ${qStr} portion${qStr === '1' ? '' : 's'}. Tap to edit in Details / Split`;
            return `
              <button type="button" class="hybrid-pill hybrid-pill-allocated ${isOrgAssigned ? 'is-org-assigned' : 'is-diner-claimed'}" data-action="hybrid-open-details" data-item="${item.id}" data-target="${p.id}" title="${title}">
                <span class="pill-avatar">${p.organizer ? '👑' : '🍽️'}</span>
                <span class="pill-name">${escapeHtml(p.name)}</span>
                <span class="pill-sep">·</span>
                <span class="pill-qty">${qStr}</span>
              </button>
            `;
          }
        }).join('')}
        <button type="button" class="btn btn-secondary btn-sm hybrid-details-btn" data-action="hybrid-toggle-details" data-item="${item.id}" aria-expanded="${isExpanded}">
          <span>${isExpanded ? '▴ Close' : '▾ Details / Split'}</span>
        </button>
      </div>
      ${canQuickAssign ? '' : `<p class="item-meta" id="quick-assign-help-${item.id}">${quickAssignHelp}</p>`}
    `;

    let drawerHtml = '';
    if (isExpanded && !isComplimentary) {
      drawerHtml = `
        <div class="hybrid-drawer" id="hybrid-drawer-${item.id}">
          ${renderHybridDetailContent(item, snap, activeParts, false)}
        </div>
      `;
    }

    return `
      <div class="hybrid-item-card ${cardStatusClass}" id="item-card-${item.id}" data-item-id="${item.id}" data-revision="${itemRevision}">
        <div class="item-header">
          <div>
            <div class="item-label">${escapeHtml(item.label)}</div>
            <div class="item-meta">${metaDisplay}</div>
          </div>
          <div class="item-price">${priceDisplay}</div>
        </div>

        ${progressBarHtml}
        ${clusterHtml}
        ${drawerHtml}
      </div>
    `;
  }).join('');

  let mobileSheetHtml = '';
  if (state.activeMobileSheetItemId) {
    const sheetItem = items.find(it => it.id === state.activeMobileSheetItemId);
    if (sheetItem) {
      const claims = snap.claims?.filter(c => c.item_id === sheetItem.id) || [];
      const totalClaimedRat = claims.reduce((acc, c) => addFractions(acc, c.quantity), 0);
      const totalClaimed = ratToNum(totalClaimedRat);
      const itemTotalQty = ratToNum(sheetItem.quantity);
      let badgeHtml = '';
      if (Math.abs(totalClaimed - itemTotalQty) < 0.0001) badgeHtml = '<span class="badge badge-verified">✓ Fully Allocated</span>';
      else if (totalClaimed > itemTotalQty) badgeHtml = '<span class="badge badge-danger">⚠️ Over-allocated</span>';
      else badgeHtml = `<span class="badge badge-pending">⚠️ ${formatRat(subtractFractions(sheetItem.quantity, totalClaimedRat))} unassigned</span>`;

      mobileSheetHtml = `
        <div class="bottom-sheet-scrim" data-action="close-sheet"></div>
        <div class="bottom-sheet-modal" role="dialog" aria-modal="true" aria-labelledby="bottom-sheet-title" id="hybrid-bottom-sheet" tabindex="-1">
          <div class="bottom-sheet-handle"></div>
          <div class="bottom-sheet-header">
            <div>
              <h3 id="bottom-sheet-title" class="bottom-sheet-item-title">${escapeHtml(sheetItem.label)}</h3>
              <div class="bottom-sheet-item-meta">Total Qty: ${itemTotalQty} &bull; ${formatSen(sheetItem.line_sen)} &bull; ${badgeHtml}</div>
            </div>
            <button type="button" class="bottom-sheet-close-btn" data-action="close-sheet" aria-label="Close sheet">✕</button>
          </div>
          <div class="bottom-sheet-body">
            ${renderHybridDetailContent(sheetItem, snap, activeParts, true)}
          </div>
        </div>
      `;
    }
  }

  return `
    <div id="allocation-section" class="card">
      <h3 id="allocation-heading" class="card-title workflow-section-heading" tabindex="-1">Item Allocation</h3>
      <p class="card-desc">
        Tap a diner to assign a portion, or use Details / Split to divide custom shares or split equally.
      </p>
      ${itemsHtml}
    </div>
    ${mobileSheetHtml}
  `;
}

function clearSimulationTimers(id = null) {
  for (const [participant, timers] of state.paymentTimers) {
    if (id === null || participant === id) {
      timers.forEach(clearTimeout);
      state.paymentTimers.delete(participant);
    }
  }
}

function resetSimulationView() {
  clearSimulationTimers();
  state.paymentEpoch++;
  state.paymentSimulations.clear();
  state.paymentBusy.clear();
  state.paymentReadSeq.clear();
}

function renderSimulationControl(participant, snap) {
  if (!snap.payment_simulation_enabled || (!snap.is_organizer && participant.id !== snap.current_participant_id)
      || snap.inactive_participant_ids?.includes(participant.id)) return '';
  const value = state.paymentSimulations.get(participant.id);
  const busy = state.paymentBusy.has(participant.id);
  const labels = {
    NO_PAYMENT_NEEDED: 'No payment needed (zero allocation)', NOT_SENT: 'Not requested',
    REQUEST_UNKNOWN: 'Request uncertain — refresh status first', PENDING: 'Pending simulated authorization',
    AUTHORIZED: 'Simulated authorization approved', DECLINED: 'Simulated authorization declined',
    FAILED: 'Simulated authorization definitively failed', CONFLICT: 'Request conflict — operator review needed',
    UNAVAILABLE: 'Status unavailable — refresh to check again', UNEXPECTED_STATUS: 'Unsupported payment status — operator review needed',
  };
  const terminal = ['NO_PAYMENT_NEEDED', 'AUTHORIZED', 'DECLINED', 'FAILED', 'CONFLICT', 'UNEXPECTED_STATUS'].includes(value?.state);
  const canInitiate = snap.is_organizer && !terminal && (!value?.exists || value?.state === 'NOT_SENT' || value?.refreshed);
  return `<div class="allocation-simulation" data-simulation-participant="${escapeHtml(participant.id)}">
    <span class="simulation-status" role="status">${busy ? 'Checking simulation…' : (labels[value?.state] || 'Simulation status not loaded')}</span>
    ${value?.observedAt ? `<span class="simulation-observed">Last observed ${escapeHtml(new Date(value.observedAt * 1000).toLocaleTimeString())}</span>` : ''}
    <div class="simulation-actions">
      ${canInitiate ? `<button type="button" class="btn btn-secondary" data-simulation-action="initiate" data-participant-id="${escapeHtml(participant.id)}" ${busy ? 'disabled' : ''}>${value?.exists && value.state !== 'NOT_SENT' ? 'Retry same simulation' : 'Simulate authorization'}</button>` : ''}
      <button type="button" class="btn btn-secondary" data-simulation-action="refresh" data-participant-id="${escapeHtml(participant.id)}" ${busy ? 'disabled' : ''}>Refresh status</button>
    </div>
  </div>`;
}

async function requestSimulation(participantId, initiate = false, schedule = true) {
  if (!state.mealId || state.paymentBusy.has(participantId) || document.visibilityState === 'hidden') return;
  const meal = state.mealId;
  const epoch = state.paymentEpoch;
  const seq = (state.paymentReadSeq.get(participantId) || 0) + 1;
  state.paymentReadSeq.set(participantId, seq);
  state.paymentBusy.add(participantId);
  updateMealUI();
  try {
    const result = await apiCall(`/api/meals/${encodeURIComponent(meal)}/participants/${encodeURIComponent(participantId)}/payment-simulation`,
      initiate ? 'POST' : 'GET', initiate ? {} : null);
    if (state.mealId !== meal || state.paymentEpoch !== epoch || state.paymentReadSeq.get(participantId) !== seq) return;
    const next = result.payment_simulation;
    const prior = state.paymentSimulations.get(participantId);
    if (prior?.paymentVersion != null && next.paymentVersion != null && next.paymentVersion < prior.paymentVersion) return;
    next.refreshed = !initiate;
    state.paymentSimulations.set(participantId, next);
    if (['PENDING', 'REQUEST_UNKNOWN'].includes(next.state) && schedule) scheduleSimulationReads(participantId);
    else if (!['PENDING', 'REQUEST_UNKNOWN'].includes(next.state)) clearSimulationTimers(participantId);
  } catch (err) {
    if (state.mealId !== meal || state.paymentEpoch !== epoch) return;
    if (err.status === 401 || err.status === 403) {
      resetSimulationView();
      showAlert('Simulation access expired or was revoked. Reload your meal session.', 'error');
    } else {
      const prior = state.paymentSimulations.get(participantId);
      state.paymentSimulations.set(participantId, {...prior, exists: prior?.exists || initiate,
        state: initiate ? 'REQUEST_UNKNOWN' : 'UNAVAILABLE', refreshed: !initiate});
      if (initiate && schedule) scheduleSimulationReads(participantId);
    }
  } finally {
    if (state.mealId === meal && state.paymentEpoch === epoch) {
      state.paymentBusy.delete(participantId);
      updateMealUI();
    }
  }
}

function scheduleSimulationReads(participantId) {
  clearSimulationTimers(participantId);
  const epoch = state.paymentEpoch;
  state.paymentTimers.set(participantId, [2, 5, 10, 30, 60, 90, 120].map(seconds => setTimeout(() => {
    if (state.paymentEpoch === epoch && document.visibilityState !== 'hidden') requestSimulation(participantId, false, false);
  }, seconds * 1000)));
}

async function loadSimulationReads(snap) {
  if (!snap.finalized || !snap.payment_simulation_enabled) return;
  const epoch = state.paymentEpoch;
  for (const participant of snap.participants || []) {
    if (state.paymentEpoch !== epoch) return;
    if ((snap.is_organizer || participant.id === snap.current_participant_id)
        && !snap.inactive_participant_ids?.includes(participant.id)) await requestSimulation(participant.id);
  }
}

function validateNotionSharingUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') {
    return { valid: false, error: 'Please enter a valid URL.' };
  }
  const trimmed = rawUrl.trim();
  if (!trimmed) {
    return { valid: false, error: 'Please enter a valid URL.' };
  }

  // 1. Explicitly check for Organizer Recovery / Claim URL
  if (trimmed.includes('claim-organizer') || trimmed.includes('/claim-organizer/')) {
    return {
      valid: false,
      isSensitive: true,
      kind: 'organizer_claim',
      error: '⚠️ Sensitive Credential Detected: You entered an Organizer Recovery Link. This grants administrative control over this meal and must NEVER be shared with diners! If this link was exposed, click "Create Recovery Link" in Sharing & Access to immediately revoke it.',
    };
  }

  // 2. Check for Diner Invitation URL
  if (trimmed.includes('/invite/') || trimmed.includes('#/invite/')) {
    return {
      valid: false,
      isSensitive: true,
      kind: 'diner_invite',
      error: '⚠️ Diner Invitation Detected: You entered a personal Diner Invitation Link. These links are for individual diners to join, not for Notion report sharing. Use the Sharing & Access section below.',
    };
  }

  // 3. Check for General Table Join URL
  if (trimmed.includes('/join/')) {
    return {
      valid: false,
      isSensitive: true,
      kind: 'table_join',
      error: '⚠️ Table Join Link Detected: You entered a Table Join Link, not a Notion report URL.',
    };
  }

  // 4. Check for internal SettleTable URLs
  try {
    const locOrigin = window.location.origin.toLowerCase();
    const candidate = new URL(trimmed, window.location.origin);
    if (candidate.origin.toLowerCase() === locOrigin && !trimmed.startsWith('https://notion.')) {
      return {
        valid: false,
        error: '⚠️ SettleTable URL Detected: Please enter a Notion report URL (https://...notion.site/..., https://...notion.so/..., or https://...notion.com/...), not a SettleTable application link.',
      };
    }
  } catch {
    // If invalid relative URL
  }

  // 5. Must parse as complete HTTPS URL
  let parsed;
  try {
    parsed = new URL(trimmed);
  } catch {
    return {
      valid: false,
      error: '⚠️ Invalid URL Format: Please provide a complete HTTPS URL starting with https://',
    };
  }

  if (parsed.protocol !== 'https:') {
    return {
      valid: false,
      error: '⚠️ Insecure Protocol: Notion links must use HTTPS (https://).',
    };
  }

  if (parsed.username || parsed.password) {
    return {
      valid: false,
      error: '⚠️ Invalid URL: URLs containing embedded user credentials are not permitted.',
    };
  }

  const host = (parsed.hostname || '').toLowerCase();
  const isNotionHost = host === 'notion.site' || host.endsWith('.notion.site') ||
                       host === 'notion.so' || host.endsWith('.notion.so') ||
                       host === 'notion.com' || host.endsWith('.notion.com');
  if (!isNotionHost) {
    return {
      valid: false,
      error: `⚠️ Unrecognized Domain: "${host}" is not a Notion domain. Please provide a link from notion.site, notion.so, or notion.com.`,
    };
  }

  if (trimmed.length > 512) {
    return {
      valid: false,
      error: '⚠️ URL Too Long: Notion links must not exceed 512 characters.',
    };
  }

  return { valid: true, url: trimmed };
}

function formatNotionSuccessHtml(exp) {
  if (!exp) return '';
  const pageId = exp.page_id || '';
  const pageUrl = exp.page_url || '#';
  const publicUrl = exp.public_url || '';
  const exportTimeStr = exp.exported_at ? new Date(exp.exported_at * 1000).toLocaleString() : '';
  const hasPageUrl = Boolean(exp.page_url && exp.page_url !== '#');

  return `
    <div id="notion-export-result" style="display: block; margin-top: 0.75rem; padding: 0.85rem; border-radius: 8px; background-color: rgba(16, 185, 129, 0.08); border: 1px solid rgba(16, 185, 129, 0.3); color: #6ee7b7;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 6px;">
        <div style="font-weight: 700; font-size: 0.95rem;">✓ Export Successful — Meal Archived to Notion</div>
        ${exportTimeStr ? `<small style="color: var(--text-dim);">${escapeHtml(exportTimeStr)}</small>` : ''}
      </div>
      <div style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 8px;">
        Page ID: <code style="font-size: 0.8rem; color: #a7f3d0;">${escapeHtml(pageId)}</code>
      </div>
      <div style="display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px;">
        <a href="${escapeHtml(pageUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-success" style="font-weight: 700; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; padding: 6px 14px;" id="notion-page-link">
          Open Report in Notion ↗
        </a>
        ${hasPageUrl ? `
          <button type="button" class="btn btn-secondary btn-sm" id="test-notion-incognito-btn" data-url="${escapeHtml(pageUrl)}" title="Copy link to test anonymous view-only access in a private/incognito window">
            🔍 Test Link in Private Window
          </button>
        ` : ''}
      </div>

      <!-- Public Link Sharing with Diners -->
      <div style="margin-top: 1rem; padding: 0.85rem; border-radius: 6px; background-color: var(--surface-primary); border: 1px solid var(--border-subtle); text-align: left;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 4px;">
          <div style="font-weight: 600; color: #818cf8; font-size: 0.85rem;">
            🔗 Diner Sharing: View-Only Web Link
          </div>
          <span class="badge" style="font-size: 0.72rem; ${publicUrl ? 'background: rgba(16, 185, 129, 0.2); color: #10b981;' : 'background: rgba(148, 163, 184, 0.15); color: var(--text-dim);'}">
            ${publicUrl ? '✓ Shared with Diners' : '🔒 Private (Disabled)'}
          </span>
        </div>

        ${publicUrl ? `
          <!-- State A: Already Shared -->
          <p style="margin: 0 0 6px 0; color: var(--text-dim); font-size: 0.8rem;">
            Diners viewing this meal can open this view-only Notion report:
          </p>
          <div style="background: var(--bg-main); padding: 8px; border-radius: 4px; border: 1px solid var(--border-subtle); margin-bottom: 8px; word-break: break-all; font-family: monospace; font-size: 0.8rem; color: #a7f3d0;">
            ${escapeHtml(publicUrl)}
          </div>
          <div style="display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin-bottom: 8px;">
            <a href="${escapeHtml(publicUrl)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="color: #6ee7b7; font-weight: 600; text-decoration: none;">
              Open Shared Report ↗
            </a>
            <button type="button" class="btn btn-secondary btn-sm" id="test-shared-incognito-btn" data-url="${escapeHtml(publicUrl)}">
              🔍 Test in Private Window
            </button>
            <button type="button" class="btn btn-secondary btn-sm" id="clear-notion-public-url-btn" style="color: var(--accent-rose);">
              Stop Sharing with Diners
            </button>
          </div>
          <div style="font-size: 0.75rem; color: var(--text-dim); margin-top: 6px;">
            ℹ️ Saved in SettleTable. This does not change your Notion permissions. Verify view access in a private window.
          </div>

          <!-- Option to update link -->
          <details id="notion-custom-url-details" style="margin-top: 10px;">
            <summary style="font-size: 0.8rem; color: var(--text-muted); cursor: pointer;">Change shared link ▾</summary>
            <div style="margin-top: 8px; padding: 8px; border-radius: 6px; background: var(--bg-main); border: 1px solid var(--border-subtle);">
              <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                <input type="url" id="notion-public-url-input" value="${escapeHtml(publicUrl)}" placeholder="https://...notion.site/..." class="form-input" style="flex: 1; min-width: 200px; font-size: 0.82rem; font-family: monospace;" />
                <button type="button" class="btn btn-secondary btn-sm" id="save-notion-public-url-btn">Update Link</button>
              </div>
              <div id="notion-url-validation-alert" style="display: none; margin-top: 6px; font-size: 0.78rem;"></div>
            </div>
          </details>
        ` : `
          <!-- State B: Not Shared Yet (Disabled by default) -->
          <p style="margin: 0 0 8px 0; color: var(--text-dim); font-size: 0.8rem; line-height: 1.4;">
            Report sharing is disabled by default. If your Notion parent page is published or allows public link viewing (inherited permissions), you can share the exported report URL directly with diners.
          </p>

          ${hasPageUrl ? `
            <div style="margin-bottom: 10px;">
              <button type="button" class="btn btn-primary btn-sm" id="share-candidate-notion-url-btn" data-url="${escapeHtml(pageUrl)}">
                📢 Share Exported Report with Diners
              </button>
            </div>

            <!-- Confirmation Prompt for Candidate Sharing -->
            <div id="notion-candidate-share-confirm" style="display: none; margin-bottom: 12px; padding: 10px; border-radius: 6px; background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.25);">
              <div style="font-weight: 700; font-size: 0.85rem; color: #818cf8; margin-bottom: 6px;">
                Share Exported Notion Report with Diners?
              </div>
              <div style="font-size: 0.8rem; color: var(--text-main); margin-bottom: 6px;">
                This will make the following report URL accessible to all diners viewing this meal:
                <div style="font-family: monospace; font-size: 0.78rem; word-break: break-all; margin: 4px 0; color: #a7f3d0; background: var(--bg-main); padding: 4px 8px; border-radius: 4px; border: 1px solid var(--border-subtle);">
                  ${escapeHtml(pageUrl)}
                </div>
              </div>
              <ul style="font-size: 0.75rem; color: var(--text-muted); margin: 0 0 10px 16px; padding: 0; line-height: 1.4;">
                <li><strong>Access Verification:</strong> SettleTable cannot verify whether your Notion page is accessible without login. Always test the link in a private/incognito window first.</li>
                <li><strong>Privacy Notice:</strong> If you published your parent page in Notion to enable inherited permissions, ensure no sensitive personal pages or unrelated subpages are located inside that parent page.</li>
                <li>Saving this link does not alter your Notion workspace permissions; it simply makes the URL visible to diners.</li>
              </ul>
              <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                <button type="button" class="btn btn-success btn-sm" id="confirm-share-candidate-btn" data-url="${escapeHtml(pageUrl)}">
                  Confirm & Share with Diners
                </button>
                <button type="button" class="btn btn-secondary btn-sm" id="cancel-share-candidate-btn">
                  Cancel
                </button>
              </div>
            </div>
          ` : ''}

          <!-- Manual Published URL Fallback -->
          <details id="notion-custom-url-details" style="margin-top: 8px;">
            <summary style="font-size: 0.8rem; color: var(--text-muted); cursor: pointer;">Need to paste a separate published web link (e.g. notion.site)? ▾</summary>
            <div style="margin-top: 8px; padding: 8px; border-radius: 6px; background: var(--bg-main); border: 1px solid var(--border-subtle);">
              <p style="font-size: 0.78rem; color: var(--text-dim); margin: 0 0 6px 0;">
                If your Notion parent page is private, publish the page in Notion (Share &rarr; Publish &rarr; Publish to web) and paste the published link:
              </p>
              <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                <input type="url" id="notion-public-url-input" placeholder="https://...notion.site/... or https://...notion.so/..." class="form-input" style="flex: 1; min-width: 200px; font-size: 0.82rem; font-family: monospace;" />
                <button type="button" class="btn btn-secondary btn-sm" id="save-notion-public-url-btn">Save Custom Link</button>
              </div>
              <div id="notion-url-validation-alert" style="display: none; margin-top: 6px; font-size: 0.78rem;"></div>
            </div>
          </details>
        `}
      </div>
    </div>
  `;
}

function renderFinalizedCalculation(snap) {
  const mealId = state.mealId || snap.meal_id;
  const calc = snap.calculation;
  if (!calc || !Array.isArray(calc.consumption)) {
    return `
      <div class="card">
        <div class="card-title" style="color: var(--accent-rose);">Calculation Data Missing</div>
        <p class="card-desc">Finalized calculation records could not be loaded.</p>
      </div>
    `;
  }

  const consumptionMap = new Map();
  for (const entry of calc.consumption) {
    if (entry && entry.participant_id !== undefined && entry.sen !== undefined) {
      consumptionMap.set(entry.participant_id, entry.sen);
    }
  }

  let grandTotalSen = snap.receipt?.total_sen;
  if (grandTotalSen === null || grandTotalSen === undefined) {
    grandTotalSen = calc.consumption.reduce((sum, c) => sum + (c.sen ?? 0), 0);
  }

  const dinersRows = snap.participants?.map(p => {
    if (!consumptionMap.has(p.id)) {
      return `
        <tr>
          <td><strong>${escapeHtml(p.name)}</strong> ${p.organizer ? '(Organizer)' : ''}</td>
          <td class="amount" style="color: var(--accent-rose);">Amount Missing</td>
        </tr>
      `;
    }
    const totalSen = consumptionMap.get(p.id);
    return `
      <tr>
        <td><strong>${escapeHtml(p.name)}</strong> ${p.organizer ? '(Organizer)' : ''}${renderSimulationControl(p, snap)}</td>
        <td class="amount" style="color: #6ee7b7; font-weight: 700;">${formatSen(totalSen)}</td>
      </tr>
    `;
  }).join('');

  const parentVal = state.notionParentId || '';
  const tokenVal = state.notionToken || '';

  const isExported = Boolean(state.notionExport && (state.notionExport.status === 'completed' || state.notionExport.status === 'already_exported'));
  let exportResultHtml = '';
  if (isExported) {
    exportResultHtml = formatNotionSuccessHtml(state.notionExport);
  } else if (state.notionExport && state.notionExport.status === 'failed') {
    exportResultHtml = `
      <div id="notion-export-result" style="display: block; margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px; background-color: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.3); color: var(--accent-rose);">
        Export failed: ${escapeHtml(state.notionExport.export_digest || 'notion_error')}
      </div>
    `;
  } else {
    exportResultHtml = `<div id="notion-export-result" style="display: none; margin-top: 0.75rem; padding: 0.75rem; border-radius: 6px;"></div>`;
  }

  const exportControlsHtml = `
    <div id="notion-export-controls">
      <div style="display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.75rem;">
        <label style="font-size: 0.8rem; color: var(--text-muted);">Notion Parent Page URL or UUID:</label>
        <input type="text" id="notion-parent-id" value="${escapeHtml(parentVal)}" placeholder="Paste Notion page URL or UUID (e.g. 3fb0ffe1-72a6-815e-b59d-ef81c6e8eb4d)" class="form-input" style="font-family: monospace; font-size: 0.85rem;" />
      </div>
      <div style="display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 0.75rem;">
        <label style="font-size: 0.8rem; color: var(--text-muted);">Integration Token (optional if set on server):</label>
        <input type="password" id="notion-token" value="${escapeHtml(tokenVal)}" placeholder="secret_..." class="form-input" style="font-family: monospace; font-size: 0.85rem;" />
      </div>
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 0.75rem;">
        <input type="checkbox" id="notion-include-photo" ${snap.has_receipt_photo ? '' : 'disabled'} />
        <label for="notion-include-photo" style="font-size: 0.85rem; color: ${snap.has_receipt_photo ? 'var(--text-main)' : 'var(--text-dim)'}; cursor: ${snap.has_receipt_photo ? 'pointer' : 'not-allowed'}; margin: 0;">
          Include original receipt photo in Notion report
          ${!snap.has_receipt_photo ? '<small style="display:block; color:var(--text-dim);">(No receipt photo attached to this meal)</small>' : ''}
        </label>
      </div>
      <button id="notion-export-btn" class="btn btn-primary" style="width: 100%;">
        Export Finalized Report to Notion
      </button>
    </div>
  `;

  return `
    <div id="apportionment-section" class="card">
      <div id="apportionment-heading" class="card-title workflow-section-heading" style="color: var(--accent-emerald);" tabindex="-1">Final Apportionment Summary</div>
      <p class="card-desc">Each person's share of the bill, calculated to the exact cent.</p>
      ${snap.payment_simulation_enabled ? '<p class="simulation-notice">Simulation only — no money moved; reimbursement unchanged.</p>' : ''}

      <table class="breakdown-table">
        <thead>
          <tr>
            <th>Participant</th>
            <th style="text-align: right;">Total Share</th>
          </tr>
        </thead>
        <tbody>
          ${dinersRows}
          <tr class="breakdown-total-row">
            <td>Grand Total</td>
            <td class="amount">${formatSen(grandTotalSen)}</td>
          </tr>
        </tbody>
      </table>
    </div>

    ${(snap.has_receipt_photo && (snap.is_organizer || snap.receipt_photo_shared)) ? `
      <div class="card" id="finalized-receipt-photo-card" style="margin-top: 1.5rem; border-color: rgba(99, 102, 241, 0.4); background: rgba(99, 102, 241, 0.05);">
        <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; color: #818cf8;">
          <span>📷 Original Receipt Photo</span>
          <button type="button" class="btn btn-secondary btn-sm" id="view-finalized-photo-btn">🔍 View & Zoom</button>
        </div>
        <div style="display: flex; align-items: center; gap: 14px; margin-top: 8px;">
          <div class="receipt-thumbnail-wrapper" id="finalized-receipt-thumb-btn" role="button" tabindex="0" title="Click to view and zoom receipt photo" aria-label="View receipt photo fullscreen">
            <img src="/api/meals/${mealId}/receipt/photo" alt="Thumbnail of original receipt" class="receipt-thumbnail-img" />
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted);">
            <div>${snap.is_organizer ? 'Receipt photo saved with this meal.' : 'Receipt photo shared by organizer for transparency.'}</div>
            <small style="color: var(--text-dim);">${snap.receipt_photo ? `${(snap.receipt_photo.byte_size / 1024).toFixed(0)} KB • ${snap.receipt_photo.width}×${snap.receipt_photo.height}px` : 'Archived receipt photo'}</small>
          </div>
        </div>
        ${snap.is_organizer ? `
          <div style="margin-top: 12px; padding-top: 10px; border-top: 1px solid rgba(99, 102, 241, 0.2);">
            <label style="display: flex; align-items: flex-start; gap: 8px; cursor: pointer; font-size: 0.85rem; margin: 0;">
              <input type="checkbox" id="share-receipt-photo-checkbox" ${snap.receipt_photo_shared ? 'checked' : ''} style="margin-top: 2px;" />
              <div>
                <strong style="color: var(--text-main);">Allow authenticated diners to view receipt photo</strong>
                <div style="font-size: 0.78rem; color: var(--text-dim); margin-top: 2px;">
                  ⚠️ Privacy Warning: Merchant receipts may show cardholder payment details, server names, or cashier notes. Only enable if trusted.
                </div>
              </div>
            </label>
          </div>
        ` : ''}
      </div>
    ` : ''}

    ${snap.is_organizer ? `
      <div class="card" id="notion-export-card" style="margin-top: 1.5rem; border-color: rgba(99, 102, 241, 0.4); background: rgba(99, 102, 241, 0.05);">
        <div class="card-title" style="color: #818cf8;">📤 Export to Notion</div>
        <p class="card-desc">Save a structured bill breakdown and receipt summary to your Notion workspace.</p>

        ${isExported ? `
          ${exportResultHtml}
          <details style="margin-top: 0.75rem;">
            <summary style="font-size: 0.82rem; color: var(--text-muted); cursor: pointer; padding: 4px 0;">
              Re-export or change Notion destination ▾
            </summary>
            <div style="margin-top: 0.75rem; padding-top: 0.75rem; border-top: 1px dashed var(--border-subtle);">
              ${exportControlsHtml}
            </div>
          </details>
        ` : `
          ${exportControlsHtml}
          ${exportResultHtml}
        `}

        <div id="notion-export-spinner" style="display: none; text-align: center; padding: 1rem; color: var(--text-muted);">
          ⏳ Creating structured Notion page...
        </div>
      </div>
    ` : `
      ${(snap.notion_export_status === 'completed' || state.notionExport?.status === 'completed' || state.notionExport?.status === 'already_exported') ? `
        <div class="card" id="diner-notion-card" style="margin-top: 1.5rem; border-color: rgba(16, 185, 129, 0.3); background: rgba(16, 185, 129, 0.04);">
          <div class="card-title" style="color: #6ee7b7; display: flex; justify-content: space-between; align-items: center;">
            <span>📤 Notion Report</span>
            <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; font-size: 0.72rem;">${snap.notion_public_url || state.notionExport?.public_url ? 'View-Only' : 'Archived'}</span>
          </div>
          ${(snap.notion_public_url || state.notionExport?.public_url) ? `
            <p class="card-desc" style="margin-bottom: 8px;">The organizer has shared a view-only Notion report for this meal:</p>
            <a href="${escapeHtml(snap.notion_public_url || state.notionExport?.public_url)}" target="_blank" rel="noopener noreferrer" class="btn btn-secondary btn-sm" style="display: inline-block; color: #6ee7b7; font-weight: 700; text-decoration: none;">
              Open Published Report ↗
            </a>
          ` : `
            <p class="card-desc" style="margin-bottom: 0;">This finalized meal was archived to the organizer's private Notion workspace.</p>
            <small style="color: var(--text-dim); display: block; margin-top: 4px;">Private Archive. Contact the organizer if you need a shared web link.</small>
          `}
        </div>
      ` : (snap.notion_export_status === 'in_progress' || state.notionExport?.status === 'in_progress') ? `
        <div class="card" id="diner-notion-card" style="margin-top: 1.5rem; border-color: rgba(99, 102, 241, 0.2); background: rgba(99, 102, 241, 0.03);">
          <div class="card-title" style="color: #818cf8;">📤 Notion Archive</div>
          <p class="card-desc" style="margin-bottom: 0;">The organizer is currently archiving this meal to Notion...</p>
        </div>
      ` : ''}
    `}
  `;
}

function renderRestaurantFundingCard(snap) {
  const funding = snap.funding;
  if (!funding) return '';

  const contributions = snap.contributions || [];
  const currentUserId = state.currentUserId || snap.current_participant_id;
  const pendingContributions = (snap.pending_contributions || []).filter(p => p.status === 'pending');
  const resolvedContribs = (snap.pending_contributions || []).filter(p => p.status === 'declined' || p.status === 'cancelled');
  const status = funding.status;
  const totalContributed = funding.total_contributed_sen;
  const receiptTotal = funding.receipt_total_sen;
  const unfunded = funding.unfunded_sen;
  const pct = receiptTotal > 0 ? Math.min(100, Math.round((totalContributed / receiptTotal) * 100)) : 100;

  let badgeHtml = '';
  if (status === 'fully_funded') {
    badgeHtml = `<span class="badge" id="funding-status-badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; font-weight: 600;">✓ Fully Funded</span>`;
  } else if (status === 'partially_funded') {
    badgeHtml = `<span class="badge" id="funding-status-badge" style="background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #60a5fa; font-weight: 600;">⚠️ Partially Funded (${formatSen(unfunded)} remaining)</span>`;
  } else {
    badgeHtml = `<span class="badge" id="funding-status-badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; font-weight: 600;">⚠️ Not Funded (${formatSen(receiptTotal)} bill)</span>`;
  }

  // Net balances rows
  const balanceRows = (funding.net_balances || []).map(b => {
    const isCreditor = b.net_sen > 0;
    const isDebtor = b.net_sen < 0;
    const netFormatted = isCreditor
      ? `+${formatSen(b.net_sen)}`
      : (isDebtor ? `-${formatSen(-b.net_sen)}` : `RM 0.00`);
    const netColor = isCreditor ? '#10b981' : (isDebtor ? '#f87171' : 'var(--text-muted)');
    const roleBadge = isCreditor
      ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 0.72rem;">Creditor (recovers)</span>`
      : (isDebtor ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.72rem;">Debtor (owes)</span>`
                 : `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: var(--text-muted); font-size: 0.72rem;">Balanced</span>`);
    const inactiveNote = !b.is_active ? ` <small style="color: var(--accent-rose);">(Inactive)</small>` : '';

    return `
      <tr>
        <td><strong>${escapeHtml(b.participant_name)}</strong>${inactiveNote}</td>
        <td class="amount">${formatSen(b.consumption_sen)}</td>
        <td class="amount" style="color: #60a5fa;">${formatSen(b.contributed_sen)}</td>
        <td class="amount" style="color: ${netColor}; font-weight: 700;">${netFormatted}</td>
        <td style="text-align: right;">${roleBadge}</td>
      </tr>
    `;
  }).join('');

  // Contribution history rows
  let historyHtml = '';
  if (contributions.length === 0) {
    historyHtml = `<p style="color: var(--text-dim); font-size: 0.85rem; font-style: italic; margin-top: 0.5rem;">No restaurant payments recorded yet.</p>`;
  } else {
    const historyRows = contributions.map(c => {
      const isReversed = c.status === 'reversed';
      const rowStyle = isReversed ? 'opacity: 0.6; text-decoration: line-through;' : '';
      const methodLabels = {
        card: '💳 Card',
        cash: '💵 Cash',
        ewallet: '📱 E-Wallet',
        bank_transfer: '🏦 Online Banking',
        other: 'Other',
      };
      const methodLabel = methodLabels[c.payment_method] || (c.payment_method ? escapeHtml(c.payment_method) : '—');
      const timeStr = new Date(c.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      let actionHtml = '';
      if (!isReversed && snap.is_organizer) {
        actionHtml = `
          <button type="button" class="btn btn-secondary btn-sm reverse-contrib-btn"
                  data-id="${escapeHtml(c.contribution_id)}"
                  data-name="${escapeHtml(c.participant_name)}"
                  data-amount="${formatSen(c.amount_sen)}"
                  style="padding: 2px 8px; font-size: 0.75rem; color: var(--accent-rose);">
            ↩ Reverse
          </button>
        `;
      } else if (isReversed) {
        actionHtml = `<small style="color: var(--accent-rose);">Reversed${c.reversal_reason ? `: ${escapeHtml(c.reversal_reason)}` : ''}</small>`;
      }

      let attributionHtml = '';
      if (c.reported_by_name && c.confirmed_by_name) {
        attributionHtml = `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">Reported by ${escapeHtml(c.reported_by_name)}, confirmed by ${escapeHtml(c.confirmed_by_name)}</div>`;
      } else {
        attributionHtml = `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">Recorded directly by Organizer</div>`;
      }

      return `
        <tr style="${rowStyle}">
          <td>
            <strong>${escapeHtml(c.participant_name)}</strong>
            ${attributionHtml}
          </td>
          <td class="amount" style="font-weight: 600;">${formatSen(c.amount_sen)}</td>
          <td><span class="badge" style="font-size: 0.72rem;">${methodLabel}</span></td>
          <td style="font-size: 0.78rem; color: var(--text-dim);">${timeStr}</td>
          <td style="text-align: right; text-decoration: none;">${actionHtml}</td>
        </tr>
      `;
    }).join('');

    historyHtml = `
      <div style="overflow-x: auto; margin-top: 0.5rem;">
        <table class="breakdown-table" style="font-size: 0.85rem;">
          <thead>
            <tr>
              <th>Payer</th>
              <th style="text-align: right;">Amount</th>
              <th>Method</th>
              <th>Time</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${historyRows}
          </tbody>
        </table>
      </div>
    `;
  }

  // Pending contributions HTML
  let pendingContribHtml = '';
  if (pendingContributions.length > 0) {
    const pendingRows = pendingContributions.map(p => {
      const methodLabels = {
        card: '💳 Card',
        cash: '💵 Cash',
        ewallet: '📱 E-Wallet',
        bank_transfer: '🏦 Online Banking',
        other: 'Other',
      };
      const methodLabel = methodLabels[p.payment_method] || (p.payment_method ? escapeHtml(p.payment_method) : '—');
      const timeStr = new Date(p.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      let actionHtml = '';
      if (snap.is_organizer) {
        actionHtml = `
          <div style="display: flex; gap: 4px; justify-content: flex-end;">
            <button type="button" class="btn btn-primary btn-sm confirm-pending-contrib-btn"
                    data-id="${escapeHtml(p.report_id)}"
                    data-name="${escapeHtml(p.participant_name)}"
                    data-amount="${formatSen(p.amount_sen)}"
                    style="padding: 2px 8px; font-size: 0.75rem; background: #10b981; border-color: #10b981;">
              ✓ Confirm
            </button>
            <button type="button" class="btn btn-secondary btn-sm decline-pending-contrib-btn"
                    data-id="${escapeHtml(p.report_id)}"
                    data-name="${escapeHtml(p.participant_name)}"
                    style="padding: 2px 8px; font-size: 0.75rem; color: var(--accent-rose);">
              ✕ Decline
            </button>
          </div>
        `;
      } else if (p.created_by === currentUserId || p.participant_id === currentUserId) {
        actionHtml = `
          <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
            <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Pending Organizer</span>
            <button type="button" class="btn btn-secondary btn-sm cancel-pending-contrib-btn"
                    data-id="${escapeHtml(p.report_id)}"
                    style="padding: 2px 6px; font-size: 0.72rem; color: var(--accent-rose);">
              Cancel
            </button>
          </div>
        `;
      } else {
        actionHtml = `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Pending Organizer</span>`;
      }

      return `
        <tr>
          <td><strong>${escapeHtml(p.participant_name)}</strong></td>
          <td class="amount" style="font-weight: 600; color: #f59e0b;">${formatSen(p.amount_sen)}</td>
          <td><span class="badge" style="font-size: 0.72rem;">${methodLabel}</span></td>
          <td style="font-size: 0.78rem; color: var(--text-dim);">${timeStr}</td>
          <td style="text-align: right;">${actionHtml}</td>
        </tr>
      `;
    }).join('');

    pendingContribHtml = `
      <div style="margin-top: 1.25rem; padding: 0.85rem; background: rgba(245, 158, 11, 0.06); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px;">
        <div style="font-weight: 600; font-size: 0.92rem; color: #f59e0b; margin-bottom: 4px;">
          ⏳ Pending Restaurant Payments (${pendingContributions.length})
        </div>
        <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.5rem;">
          Reported by diners at the counter. Pending reports do not alter balances until confirmed by the organizer.
        </div>
        <div style="overflow-x: auto;">
          <table class="breakdown-table" style="font-size: 0.85rem;">
            <thead>
              <tr>
                <th>Payer</th>
                <th style="text-align: right;">Amount</th>
                <th>Method</th>
                <th>Time</th>
                <th style="text-align: right;">Status / Action</th>
              </tr>
            </thead>
            <tbody>
              ${pendingRows}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Resolved (declined or cancelled) contributions HTML
  let resolvedContribHtml = '';
  if (resolvedContribs.length > 0) {
    const rows = resolvedContribs.map(p => {
      const isDeclined = p.status === 'declined';
      const statusBadge = isDeclined
        ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.72rem;">Declined</span>`
        : `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: var(--text-muted); font-size: 0.72rem;">Cancelled</span>`;
      const reasonStr = p.rejection_reason ? ` (${escapeHtml(p.rejection_reason)})` : '';
      return `
        <li style="margin-bottom: 4px;">
          <strong>${escapeHtml(p.participant_name)}</strong> — ${formatSen(p.amount_sen)}: ${statusBadge}${reasonStr}
        </li>
      `;
    }).join('');
    resolvedContribHtml = `
      <details style="margin-top: 0.75rem; font-size: 0.8rem; color: var(--text-muted);">
        <summary style="cursor: pointer;">Declined or Cancelled Payment Reports (${resolvedContribs.length})</summary>
        <ul style="margin-top: 0.4rem; padding-left: 1.2rem;">
          ${rows}
        </ul>
      </details>
    `;
  }

  // Options for participant select
  const participantOptions = (funding.net_balances || []).map(b => {
    return `<option value="${escapeHtml(b.participant_id)}">${escapeHtml(b.participant_name)} (consumed ${formatSen(b.consumption_sen)})</option>`;
  }).join('');

  return `
    <div class="card" id="restaurant-funding-card" style="margin-top: 1.5rem; border-color: rgba(59, 130, 246, 0.4); background: rgba(15, 23, 42, 0.5);">
      <div class="card-title" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
        <span style="color: #60a5fa;">💳 Restaurant Payers & Bill Funding</span>
        ${badgeHtml}
      </div>
      <p class="card-desc">
        Record how much each person paid at the counter to reconcile who covered the bill.
      </p>

      <!-- Funding Progress Bar -->
      <div style="margin: 1rem 0;">
        <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
          <span>Funding Progress: <strong>${formatSen(totalContributed)}</strong> of <strong>${formatSen(receiptTotal)}</strong></span>
          <span><strong>${pct}%</strong></span>
        </div>
        <div style="height: 10px; background: rgba(255, 255, 255, 0.1); border-radius: 5px; overflow: hidden;">
          <div id="funding-progress-bar-fill" style="height: 100%; width: ${pct}%; background: ${status === 'fully_funded' ? '#10b981' : (status === 'partially_funded' ? '#3b82f6' : '#f59e0b')}; transition: width 0.3s ease;"></div>
        </div>
      </div>

      <!-- Net Balance Reconciliation Table -->
      <div style="margin-top: 1.25rem;">
        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: var(--text-main);">
          Participant Net Balances (Paid to Restaurant − Amount Consumed)
        </div>
        <div style="overflow-x: auto;">
          <table class="breakdown-table">
            <thead>
              <tr>
                <th>Participant</th>
                <th style="text-align: right;" title="Finalized meal consumption share">Amount Consumed</th>
                <th style="text-align: right;" title="Actual payment made to the restaurant at the counter">Paid to Restaurant</th>
                <th style="text-align: right;" title="Paid to restaurant minus amount consumed">Base Net (Paid − Consumed)</th>
                <th style="text-align: right;">Status</th>
              </tr>
            </thead>
            <tbody>
              ${balanceRows}
              <tr class="breakdown-total-row">
                <td>Grand Total</td>
                <td class="amount">${formatSen(receiptTotal)}</td>
                <td class="amount" style="color: #60a5fa;">${formatSen(totalContributed)}</td>
                <td class="amount" style="color: ${totalContributed >= receiptTotal ? '#10b981' : '#f87171'};">
                  ${totalContributed >= receiptTotal ? 'RM 0.00' : `-${formatSen(unfunded)}`}
                </td>
                <td></td>
              </tr>
            </tbody>
          </table>
        </div>
        ${status !== 'fully_funded' ? `
          <p style="font-size: 0.82rem; color: var(--text-muted); margin-top: 0.5rem; padding: 0.5rem 0.75rem; background: rgba(245, 158, 11, 0.1); border-left: 3px solid #f59e0b; border-radius: 4px;">
            ℹ️ <strong>Unfunded bill balance:</strong> ${formatSen(unfunded)} remains owed to the restaurant. Peer reimbursements can be settled once the cashier bill is fully covered.
          </p>
        ` : `
          <p style="font-size: 0.82rem; color: #10b981; margin-top: 0.5rem; padding: 0.5rem 0.75rem; background: rgba(16, 185, 129, 0.1); border-left: 3px solid #10b981; border-radius: 4px;">
            ✓ <strong>Restaurant bill is fully paid.</strong> Net balances are ready for peer settlement.
          </p>
        `}
      </div>

      <!-- Pending Contributions Section -->
      ${pendingContribHtml}

      <!-- Diner I Paid Counter Toggle & Form -->
      ${(!snap.is_organizer && status !== 'fully_funded' && currentUserId) ? `
        <div style="margin-top: 1rem;">
          <button type="button" id="toggle-diner-contrib-panel-btn" class="btn btn-secondary" style="width: 100%; border: 1px dashed #60a5fa; color: #60a5fa; padding: 8px 12px; font-size: 0.9rem;">
            💳 I Paid the Restaurant Counter
          </button>
          <div id="diner-contrib-panel" style="display: none; margin-top: 0.75rem; padding: 1rem; border-radius: 8px; background: rgba(59, 130, 246, 0.07); border: 1px solid rgba(59, 130, 246, 0.3);">
            <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: #93c5fd;">
              Report Restaurant Payment
            </div>
            <p style="font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.75rem;">
              If you paid the restaurant cashier at the counter, enter the amount and method below. Your report will be sent to the organizer for confirmation before updating the ledger.
            </p>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
              <div>
                <label for="diner-payer-method-select" style="display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">Payment Method:</label>
                <select id="diner-payer-method-select" class="form-input" style="width: 100%;">
                  <option value="card">💳 Credit / Debit Card</option>
                  <option value="cash">💵 Cash</option>
                  <option value="ewallet">📱 E-Wallet (TNG / GrabPay)</option>
                  <option value="bank_transfer">🏦 Online Banking / DuitNow</option>
                  <option value="other">Other</option>
                </select>
              </div>
              <div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <label for="diner-payer-amount-input" style="font-size: 0.8rem; color: var(--text-muted); margin: 0;">Amount (RM):</label>
                  <button type="button" id="diner-fill-remaining-btn" class="btn btn-secondary btn-sm" style="font-size: 0.72rem; padding: 1px 6px;">
                    Remaining (${formatSen(unfunded)})
                  </button>
                </div>
                <input type="text" id="diner-payer-amount-input" class="form-input" placeholder="e.g. 50.00" inputmode="decimal" autocomplete="off" style="width: 100%; font-size: 1rem; font-weight: 600;" />
              </div>
            </div>
            <div style="display: flex; gap: 8px;">
              <button type="button" id="submit-diner-contrib-btn" class="btn btn-primary" style="flex: 1;">
                Submit Payment for Confirmation
              </button>
              <button type="button" id="cancel-diner-contrib-panel-btn" class="btn btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        </div>
      ` : ''}

      <!-- Organizer Record Payment Form -->
      ${(snap.is_organizer && status !== 'fully_funded') ? `
        <div style="margin-top: 1.5rem; padding: 1rem; border-radius: 8px; background: rgba(59, 130, 246, 0.07); border: 1px solid rgba(59, 130, 246, 0.25);">
          <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.75rem; color: #93c5fd;">
            ➕ Record Restaurant Payment
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
            <div>
              <label for="payer-participant-select" style="display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">Payer Participant:</label>
              <select id="payer-participant-select" class="form-input" style="width: 100%;">
                <option value="">Select participant...</option>
                ${participantOptions}
              </select>
            </div>
            <div>
              <label for="payer-method-select" style="display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">Payment Method:</label>
              <select id="payer-method-select" class="form-input" style="width: 100%;">
                <option value="card">💳 Credit / Debit Card</option>
                <option value="cash">💵 Cash</option>
                <option value="ewallet">📱 E-Wallet (TNG / GrabPay)</option>
                <option value="bank_transfer">🏦 Online Banking / DuitNow</option>
                <option value="other">Other</option>
              </select>
            </div>
          </div>
          <div style="margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <label for="payer-amount-input" style="font-size: 0.8rem; color: var(--text-muted); margin: 0;">Amount (RM):</label>
              <button type="button" id="fill-remaining-btn" class="btn btn-secondary btn-sm" style="font-size: 0.75rem; padding: 2px 8px;">
                Fill Remaining (${formatSen(unfunded)})
              </button>
            </div>
            <input type="text" id="payer-amount-input" class="form-input" placeholder="e.g. 50.00" inputmode="decimal" autocomplete="off" style="width: 100%; font-size: 1rem; font-weight: 600;" />
          </div>
          <button type="button" id="record-contribution-btn" class="btn btn-primary" style="width: 100%;">
            Record Payment to Restaurant
          </button>
        </div>
      ` : ''}

      <!-- Contribution History Ledger -->
      <div style="margin-top: 1.5rem;">
        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: var(--text-main);">
          Recorded Restaurant Payments
        </div>
        ${historyHtml}
        ${resolvedContribHtml}
      </div>
    </div>
  `;
}

function renderPeerSettlementCard(snap) {
  const settle = snap.settlement;
  if (!settle) return '';

  const currentUserId = state.currentUserId || snap.current_participant_id;
  const isSettled = settle.is_settled;
  const unfundedBlocker = settle.unfunded_blocker_sen;
  const suggestedTransfers = settle.suggested_transfers || [];
  const transfers = snap.transfers || [];
  const outstandingList = settle.outstanding_net_balances || [];
  const pendingTransfers = (snap.pending_transfers || []).filter(t => t.status === 'pending');
  const resolvedTransfers = (snap.pending_transfers || []).filter(t => t.status === 'declined' || t.status === 'cancelled');

  // Debtors and Creditors for reimbursement dropdowns
  const debtors = outstandingList.filter(b => b.outstanding_net_balance_sen < 0);
  const creditors = outstandingList.filter(b => b.outstanding_net_balance_sen > 0);

  // Status badge
  let statusBadgeHtml = '';
  if (isSettled) {
    statusBadgeHtml = `<span class="badge" id="settlement-status-badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981; border: 1px solid #10b981; font-weight: 600;">✓ All Debts Settled</span>`;
  } else {
    statusBadgeHtml = `<span class="badge" id="settlement-status-badge" style="background: rgba(245, 158, 11, 0.2); color: #f59e0b; border: 1px solid #f59e0b; font-weight: 600;">Reimbursements Pending</span>`;
  }

  // Outstanding net balances table rows
  const balanceRows = outstandingList.map(b => {
    const isCreditor = b.outstanding_net_balance_sen > 0;
    const isDebtor = b.outstanding_net_balance_sen < 0;

    const outFormatted = isCreditor
      ? `+${formatSen(b.outstanding_net_balance_sen)}`
      : (isDebtor ? `-${formatSen(-b.outstanding_net_balance_sen)}` : `RM 0.00`);
    const outColor = isCreditor ? '#10b981' : (isDebtor ? '#f87171' : 'var(--text-muted)');
    const statusBadge = isCreditor
      ? `<span class="badge" style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 0.72rem;">To Recover</span>`
      : (isDebtor ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.72rem;">Still Owes</span>`
                 : `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: var(--text-muted); font-size: 0.72rem;">Settled ✓</span>`);
    const inactiveNote = !b.is_active ? ` <small style="color: var(--accent-rose);">(Inactive)</small>` : '';

    return `
      <tr>
        <td><strong>${escapeHtml(b.name)}</strong>${inactiveNote}</td>
        <td class="amount">${formatSen(b.base_net_balance_sen)}</td>
        <td class="amount" style="color: #60a5fa;">${formatSen(b.confirmed_sent_sen)}</td>
        <td class="amount" style="color: #a78bfa;">${formatSen(b.confirmed_received_sen)}</td>
        <td class="amount" style="color: ${outColor}; font-weight: 700;">${outFormatted}</td>
        <td style="text-align: right;">${statusBadge}</td>
      </tr>
    `;
  }).join('');

  // Suggested Transfers HTML
  let suggestionsHtml = '';
  if (isSettled) {
    suggestionsHtml = `
      <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; padding: 12px; margin-top: 10px; color: #10b981; text-align: center;">
        <strong>🎉 All Accounts Balanced!</strong><br/>
        <span style="font-size: 0.85rem;">Every participant has fully settled their share of the meal.</span>
      </div>
    `;
  } else if (suggestedTransfers.length === 0) {
    suggestionsHtml = `
      <p style="color: var(--text-dim); font-size: 0.85rem; font-style: italic; margin-top: 0.5rem;">
        No peer transfer suggestions available.
        ${unfundedBlocker > 0 ? `Outstanding ${formatSen(unfundedBlocker)} must be contributed directly to the restaurant bill.` : ''}
      </p>
    `;
  } else {
    const cards = suggestedTransfers.map(st => {
      const sender = outstandingList.find(b => b.participant_id === st.sender_id);
      const receiver = outstandingList.find(b => b.participant_id === st.receiver_id);
      const sName = sender ? sender.name : st.sender_id;
      const rName = receiver ? receiver.name : st.receiver_id;

      let actionBtns = '';
      if (snap.is_organizer) {
        actionBtns += `
          <button type="button" class="btn btn-secondary btn-sm prefill-transfer-btn"
                  data-sender="${escapeHtml(st.sender_id)}"
                  data-receiver="${escapeHtml(st.receiver_id)}"
                  data-amount="${(st.amount_sen / 100).toFixed(2)}"
                  style="font-size: 0.75rem; padding: 3px 10px; margin-left: auto;">
            Use Suggestion
          </button>
        `;
      }
      if (st.sender_id === currentUserId) {
        actionBtns += `
          <button type="button" class="btn btn-primary btn-sm diner-report-sent-btn"
                  data-receiver="${escapeHtml(st.receiver_id)}"
                  data-receiver-name="${escapeHtml(rName)}"
                  data-amount="${(st.amount_sen / 100).toFixed(2)}"
                  style="font-size: 0.75rem; padding: 3px 10px; margin-left: auto;">
            💸 I've Sent Payment
          </button>
        `;
      }

      return `
        <div class="card" style="margin-bottom: 8px; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; background: var(--surface-secondary);">
          <div style="display: flex; align-items: center; gap: 10px; font-size: 0.95rem;">
            <span style="font-weight: 700; color: #f87171;">${escapeHtml(sName)}</span>
            <span style="color: var(--text-muted); font-size: 0.85rem;">pays</span>
            <span style="font-weight: 700; color: #10b981;">${escapeHtml(rName)}</span>
            <span style="font-size: 1.05rem; font-weight: 700; color: var(--text-main); margin-left: 6px;">${formatSen(st.amount_sen)}</span>
          </div>
          ${actionBtns}
        </div>
      `;
    }).join('');

    suggestionsHtml = `
      <div style="margin-top: 0.75rem;">
        ${cards}
      </div>
    `;
  }

  // Unfunded blocker warning
  let unfundedWarningHtml = '';
  if (unfundedBlocker > 0) {
    unfundedWarningHtml = `
      <div style="background: rgba(245, 158, 11, 0.1); border: 1px solid rgba(245, 158, 11, 0.3); border-radius: 8px; padding: 10px 14px; margin-bottom: 12px; font-size: 0.85rem; color: #f59e0b;">
        <strong>⚠️ Unfunded Restaurant Bill (${formatSen(unfundedBlocker)})</strong><br/>
        The restaurant bill is not fully funded. Suggested peer transfers only settle up to the fronted restaurant amounts. The remaining balance represents an outstanding restaurant obligation.
      </div>
    `;
  }

  // Pending reimbursements HTML
  let pendingTransfersHtml = '';
  if (pendingTransfers.length > 0) {
    const rows = pendingTransfers.map(t => {
      const timeStr = new Date(t.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const isRecipient = currentUserId === t.receiver_id;
      const isSender = currentUserId === t.sender_id;

      let actionHtml = '';
      if (isRecipient) {
        actionHtml = `
          <div style="display: flex; gap: 4px; justify-content: flex-end;">
            <button type="button" class="btn btn-primary btn-sm confirm-pending-transfer-btn"
                    data-id="${escapeHtml(t.report_id)}"
                    data-sender="${escapeHtml(t.sender_name)}"
                    data-amount="${formatSen(t.amount_sen)}"
                    style="padding: 2px 8px; font-size: 0.75rem; background: #10b981; border-color: #10b981;">
              ✓ Confirm Received
            </button>
            <button type="button" class="btn btn-secondary btn-sm decline-pending-transfer-btn"
                    data-id="${escapeHtml(t.report_id)}"
                    data-sender="${escapeHtml(t.sender_name)}"
                    style="padding: 2px 8px; font-size: 0.75rem; color: var(--accent-rose);">
              ✕ Not Received
            </button>
          </div>
        `;
      } else if (isSender) {
        actionHtml = `
          <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
            <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Awaiting ${escapeHtml(t.receiver_name)}</span>
            <button type="button" class="btn btn-secondary btn-sm cancel-pending-transfer-btn"
                    data-id="${escapeHtml(t.report_id)}"
                    style="padding: 2px 6px; font-size: 0.72rem; color: var(--accent-rose);">
              Cancel
            </button>
          </div>
        `;
      } else if (snap.is_organizer) {
        actionHtml = `
          <div style="display: flex; gap: 4px; justify-content: flex-end; align-items: center;">
            <span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Awaiting ${escapeHtml(t.receiver_name)}</span>
            <button type="button" class="btn btn-secondary btn-sm decline-pending-transfer-btn"
                    data-id="${escapeHtml(t.report_id)}"
                    data-sender="${escapeHtml(t.sender_name)}"
                    style="padding: 2px 6px; font-size: 0.72rem; color: var(--accent-rose);">
              ✕ Decline
            </button>
          </div>
        `;
      } else {
        actionHtml = `<span class="badge" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b; font-size: 0.72rem;">Awaiting ${escapeHtml(t.receiver_name)}</span>`;
      }

      return `
        <tr>
          <td><strong>${escapeHtml(t.sender_name)}</strong> → <strong>${escapeHtml(t.receiver_name)}</strong></td>
          <td class="amount" style="font-weight: 600; color: #f59e0b;">${formatSen(t.amount_sen)}</td>
          <td style="font-size: 0.82rem; color: var(--text-muted);">${t.note ? escapeHtml(t.note) : '—'}</td>
          <td style="font-size: 0.78rem; color: var(--text-dim);">${timeStr}</td>
          <td style="text-align: right;">${actionHtml}</td>
        </tr>
      `;
    }).join('');

    pendingTransfersHtml = `
      <div style="margin-bottom: 1.5rem; padding: 0.85rem; background: rgba(245, 158, 11, 0.06); border: 1px solid rgba(245, 158, 11, 0.25); border-radius: 8px;">
        <div style="font-weight: 600; font-size: 0.92rem; color: #f59e0b; margin-bottom: 4px;">
          ⏳ Pending Reimbursement Confirmations (${pendingTransfers.length})
        </div>
        <div style="font-size: 0.78rem; color: var(--text-muted); margin-bottom: 0.5rem;">
          Reported peer reimbursements awaiting recipient confirmation. SettleTable does not execute banking transactions; balances update only when confirmed.
        </div>
        <div style="overflow-x: auto;">
          <table class="breakdown-table" style="font-size: 0.85rem;">
            <thead>
              <tr>
                <th>Transfer</th>
                <th style="text-align: right;">Amount</th>
                <th>Note</th>
                <th>Time</th>
                <th style="text-align: right;">Status / Action</th>
              </tr>
            </thead>
            <tbody>
              ${rows}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  // Resolved (declined or cancelled) transfers HTML
  let resolvedTransfersHtml = '';
  if (resolvedTransfers.length > 0) {
    const rows = resolvedTransfers.map(t => {
      const isDeclined = t.status === 'declined';
      const statusBadge = isDeclined
        ? `<span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; font-size: 0.72rem;">Declined / Not Received</span>`
        : `<span class="badge" style="background: rgba(148, 163, 184, 0.15); color: var(--text-muted); font-size: 0.72rem;">Cancelled</span>`;
      const reasonStr = t.rejection_reason ? ` (${escapeHtml(t.rejection_reason)})` : '';
      return `
        <li style="margin-bottom: 4px;">
          <strong>${escapeHtml(t.sender_name)}</strong> → <strong>${escapeHtml(t.receiver_name)}</strong> (${formatSen(t.amount_sen)}): ${statusBadge}${reasonStr}
        </li>
      `;
    }).join('');
    resolvedTransfersHtml = `
      <details style="margin-top: 0.75rem; font-size: 0.8rem; color: var(--text-muted);">
        <summary style="cursor: pointer;">Declined or Cancelled Reimbursement Reports (${resolvedTransfers.length})</summary>
        <ul style="margin-top: 0.4rem; padding-left: 1.2rem;">
          ${rows}
        </ul>
      </details>
    `;
  }

  // Transfer history ledger
  let ledgerHtml = '';
  if (transfers.length === 0) {
    ledgerHtml = `<p style="color: var(--text-dim); font-size: 0.85rem; font-style: italic; margin-top: 0.5rem;">No peer reimbursements recorded yet.</p>`;
  } else {
    const transferRows = transfers.map(t => {
      const isReversed = t.status === 'reversed';
      const rowStyle = isReversed ? 'opacity: 0.6; text-decoration: line-through;' : '';
      const sObj = outstandingList.find(b => b.participant_id === t.sender_id);
      const rObj = outstandingList.find(b => b.participant_id === t.receiver_id);
      const sName = sObj ? sObj.name : t.sender_id;
      const rName = rObj ? rObj.name : t.receiver_id;
      const timeStr = new Date(t.created_at * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      let actionHtml = '';
      if (!isReversed && snap.is_organizer) {
        actionHtml = `
          <button type="button" class="btn btn-secondary btn-sm reverse-transfer-btn"
                  data-id="${escapeHtml(t.transfer_id)}"
                  data-desc="${escapeHtml(sName)} → ${escapeHtml(rName)}"
                  data-amount="${formatSen(t.amount_sen)}"
                  style="padding: 2px 8px; font-size: 0.75rem; color: var(--accent-rose);">
            ↩ Reverse
          </button>
        `;
      } else if (isReversed) {
        actionHtml = `<small style="color: var(--accent-rose);">Reversed${t.reversal_reason ? `: ${escapeHtml(t.reversal_reason)}` : ''}</small>`;
      }

      let attributionHtml = '';
      if (t.reported_by_name && t.confirmed_by_name) {
        attributionHtml = `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">Reported by ${escapeHtml(t.reported_by_name)}, confirmed by ${escapeHtml(t.confirmed_by_name)}</div>`;
      } else {
        attributionHtml = `<div style="font-size: 0.72rem; color: var(--text-dim); margin-top: 2px;">Recorded directly by Organizer</div>`;
      }

      return `
        <tr style="${rowStyle}">
          <td>
            <strong>${escapeHtml(sName)}</strong> → <strong>${escapeHtml(rName)}</strong>
            ${attributionHtml}
          </td>
          <td class="amount" style="font-weight: 600;">${formatSen(t.amount_sen)}</td>
          <td style="font-size: 0.82rem; color: var(--text-muted);">${t.note ? escapeHtml(t.note) : '—'}</td>
          <td style="font-size: 0.78rem; color: var(--text-dim);">${timeStr}</td>
          <td style="text-align: right; text-decoration: none;">${actionHtml}</td>
        </tr>
      `;
    }).join('');

    ledgerHtml = `
      <div style="overflow-x: auto; margin-top: 0.5rem;">
        <table class="breakdown-table" style="font-size: 0.85rem;">
          <thead>
            <tr>
              <th>Transfer</th>
              <th style="text-align: right;">Amount</th>
              <th>Note</th>
              <th>Time</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody>
            ${transferRows}
          </tbody>
        </table>
      </div>
    `;
  }

  // Record transfer form (organizer only)
  let recordFormHtml = '';
  if (snap.is_organizer && !isSettled && debtors.length > 0 && creditors.length > 0) {
    const senderOptions = debtors.map(d =>
      `<option value="${escapeHtml(d.participant_id)}">${escapeHtml(d.name)} (owes ${formatSen(-d.outstanding_net_balance_sen)})</option>`
    ).join('');
    const receiverOptions = creditors.map(c =>
      `<option value="${escapeHtml(c.participant_id)}">${escapeHtml(c.name)} (receives ${formatSen(c.outstanding_net_balance_sen)})</option>`
    ).join('');

    recordFormHtml = `
      <div class="card" id="record-transfer-form" style="margin-top: 1.5rem; padding: 1rem; border-left: 3px solid var(--accent-indigo);">
        <div id="record-transfer-heading" class="card-title workflow-section-heading" tabindex="-1" style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.75rem; color: var(--text-main);">
          Record Confirmed Peer Reimbursement
        </div>
        <div id="prefill-transfer-banner" class="prefill-transfer-banner" role="status" aria-live="polite" style="display: none;"></div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px;">
          <div>
            <label for="transfer-sender-select" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 4px;">Payer (Debtor):</label>
            <select id="transfer-sender-select" class="form-input" style="width: 100%;">
              ${senderOptions}
            </select>
          </div>
          <div>
            <label for="transfer-receiver-select" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 4px;">Recipient (Creditor):</label>
            <select id="transfer-receiver-select" class="form-input" style="width: 100%;">
              ${receiverOptions}
            </select>
          </div>
        </div>
        <div style="margin-bottom: 10px;">
          <label for="transfer-amount-input" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 4px;">Amount (RM):</label>
          <input type="text" id="transfer-amount-input" class="form-input" placeholder="e.g. 15.00" inputmode="decimal" autocomplete="off" style="width: 100%; font-size: 1rem; font-weight: 600;" />
        </div>
        <div style="margin-bottom: 12px;">
          <label for="transfer-note-input" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 4px;">Reference / Note (Optional):</label>
          <input type="text" id="transfer-note-input" class="form-input" placeholder="e.g. DuitNow reference or cash at table" style="width: 100%;" />
        </div>
        <button type="button" id="record-transfer-btn" class="btn btn-primary" style="width: 100%;">
          Record Confirmed Reimbursement
        </button>
        <div style="margin-top: 8px; font-size: 0.75rem; color: var(--text-dim); line-height: 1.4;">
          ℹ️ SettleTable records organizer-attested reimbursements without executing or independently verifying bank or e-wallet payments.
        </div>
      </div>
    `;
  }

  // Diner personalized settlement summary card
  let dinerPersonalCardHtml = '';
  if (!snap.is_organizer) {
    const myRec = outstandingList.find(b => b.participant_id === currentUserId);
    if (myRec) {
      const myNet = myRec.outstanding_net_balance_sen;
      if (myNet < 0) {
        // Debtor
        const oweSen = -myNet;
        const myTransfers = suggestedTransfers.filter(st => st.sender_id === currentUserId);
        const transferLines = myTransfers.map(st => {
          const recObj = outstandingList.find(b => b.participant_id === st.receiver_id);
          const rName = recObj ? recObj.name : st.receiver_id;
          return `
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 6px 0; border-bottom: 1px dashed rgba(255, 255, 255, 0.08); flex-wrap: wrap; gap: 6px;">
              <div>
                👉 Pay <strong>${escapeHtml(rName)}</strong>: <span style="color: #6ee7b7; font-size: 1.05rem; font-weight: 700;">${formatSen(st.amount_sen)}</span>
              </div>
              <button type="button" class="btn btn-primary btn-sm diner-report-sent-btn"
                      data-receiver="${escapeHtml(st.receiver_id)}"
                      data-receiver-name="${escapeHtml(rName)}"
                      data-amount="${(st.amount_sen / 100).toFixed(2)}"
                      style="font-size: 0.75rem; padding: 3px 10px;">
                💸 I've Sent Payment
              </button>
            </div>
          `;
        }).join('');

        const creditorOptions = creditors.map(c =>
          `<option value="${escapeHtml(c.participant_id)}">${escapeHtml(c.name)} (receives ${formatSen(c.outstanding_net_balance_sen)})</option>`
        ).join('');

        const dinerXferFormHtml = `
          <div style="margin-top: 8px;">
            <button type="button" id="toggle-custom-diner-transfer-btn" class="btn btn-secondary btn-sm" style="font-size: 0.75rem; padding: 3px 10px;">
              ➕ Report Reimbursement
            </button>
            <div id="diner-report-transfer-form" style="display: none; margin-top: 8px; padding: 10px 12px; background: rgba(0, 0, 0, 0.25); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 6px;">
              <div style="font-weight: 600; font-size: 0.88rem; margin-bottom: 6px; color: #fca5a5;">
                Report Sent Reimbursement
              </div>
              <div style="font-size: 0.78rem; color: var(--text-dim); margin-bottom: 8px;">
                Report a reimbursement you've transferred. The recipient will be notified to confirm they received the funds before balances update.
              </div>
              <div style="margin-bottom: 8px;">
                <label for="diner-xfer-receiver-select" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 2px;">Recipient (Creditor):</label>
                <select id="diner-xfer-receiver-select" class="form-input" style="width: 100%;">
                  ${creditorOptions}
                </select>
              </div>
              <div style="margin-bottom: 8px;">
                <label for="diner-xfer-amount-input" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 2px;">Amount (RM):</label>
                <input type="text" id="diner-xfer-amount-input" class="form-input" placeholder="e.g. 15.00" inputmode="decimal" autocomplete="off" style="width: 100%; font-size: 0.95rem; font-weight: 600;" />
              </div>
              <div style="margin-bottom: 10px;">
                <label for="diner-xfer-note-input" style="font-size: 0.8rem; color: var(--text-muted); display: block; margin-bottom: 2px;">Reference / Note (Optional):</label>
                <input type="text" id="diner-xfer-note-input" class="form-input" placeholder="e.g. DuitNow reference or cash handed" style="width: 100%; font-size: 0.85rem;" />
              </div>
              <div style="display: flex; gap: 8px;">
                <button type="button" id="submit-diner-transfer-btn" class="btn btn-primary btn-sm" style="flex: 1;">
                  Submit Sent Payment Report
                </button>
                <button type="button" id="cancel-diner-transfer-form-btn" class="btn btn-secondary btn-sm">
                  Cancel
                </button>
              </div>
            </div>
          </div>
        `;

        dinerPersonalCardHtml = `
          <div class="card" id="diner-personal-settlement-card" style="margin-bottom: 12px; padding: 12px 14px; background: rgba(239, 68, 68, 0.07); border: 1px solid rgba(239, 68, 68, 0.3); border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 6px;">
              <span style="font-weight: 700; color: #f87171;">💰 Your Settlement Action</span>
              <span class="badge" style="background: rgba(239, 68, 68, 0.2); color: #f87171;">You Owe ${formatSen(oweSen)}</span>
            </div>
            ${transferLines ? `<div style="margin: 6px 0;">${transferLines}</div>` : ''}
            ${dinerXferFormHtml}
            ${unfundedBlocker > 0 ? `<div style="font-size: 0.8rem; color: #f59e0b; margin-top: 6px;">⚠️ ${formatSen(unfundedBlocker)} of the restaurant bill remains unfunded. Direct peer settlement is pending cashier funding.</div>` : ''}
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 8px; padding-top: 6px; border-top: 1px solid rgba(239, 68, 68, 0.15);">
              ℹ️ Transfer your share to the recipient above, then tap <strong>I've Sent Payment</strong> so they can confirm receipt.
            </div>
          </div>
        `;
      } else if (myNet > 0) {
        // Creditor
        const recoverSen = myNet;
        const incomingTransfers = suggestedTransfers.filter(st => st.receiver_id === currentUserId);
        const incomingLines = incomingTransfers.map(st => {
          const sndObj = outstandingList.find(b => b.participant_id === st.sender_id);
          const sName = sndObj ? sndObj.name : st.sender_id;
          return `<div style="padding: 4px 0; font-weight: 600; color: var(--text-main);">👉 <strong>${escapeHtml(sName)}</strong> pays you: <span style="color: #6ee7b7; font-size: 1.05rem;">${formatSen(st.amount_sen)}</span></div>`;
        }).join('');

        dinerPersonalCardHtml = `
          <div class="card" id="diner-personal-settlement-card" style="margin-bottom: 12px; padding: 12px 14px; background: rgba(16, 185, 129, 0.07); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; flex-wrap: wrap; gap: 6px;">
              <span style="font-weight: 700; color: #10b981;">💰 Your Reimbursement Summary</span>
              <span class="badge" style="background: rgba(16, 185, 129, 0.2); color: #10b981;">To Recover ${formatSen(recoverSen)}</span>
            </div>
            ${incomingLines ? `<div style="margin: 6px 0;">${incomingLines}</div>` : ''}
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(16, 185, 129, 0.15);">
              ℹ️ When you receive repayment, tap <strong>Confirm Received</strong> below to complete settlement.
            </div>
          </div>
        `;
      } else {
        // Settled
        dinerPersonalCardHtml = `
          <div class="card" id="diner-personal-settlement-card" style="margin-bottom: 12px; padding: 12px 14px; background: rgba(16, 185, 129, 0.07); border: 1px solid rgba(16, 185, 129, 0.3); border-radius: 8px; text-align: center;">
            <span style="font-weight: 700; color: #10b981; font-size: 0.95rem;">🎉 You're All Settled!</span>
            <div style="font-size: 0.82rem; color: var(--text-muted); margin-top: 2px;">Your share of this meal is fully balanced. No further action needed.</div>
          </div>
        `;
      }
    }
  }

  return `
    <div class="card" id="peer-settlement-card" style="margin-top: 1.5rem;">
      <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.75rem; flex-wrap: wrap; gap: 8px;">
        <div>
          <div style="font-weight: 700; font-size: 1.15rem; color: var(--text-main);">
            Peer Settlements & Reimbursements
          </div>
          <div style="font-size: 0.85rem; color: var(--text-muted); margin-top: 2px;">
            Suggested transfers to balance everyone's fair share.
          </div>
        </div>
        ${statusBadgeHtml}
      </div>

      <!-- Collaborative Settlement Notice -->
      <div class="settlement-attestation-notice" style="background: rgba(99, 102, 241, 0.08); border: 1px solid rgba(99, 102, 241, 0.25); border-radius: var(--radius-md); padding: 8px 12px; margin-bottom: 12px; font-size: 0.8rem; color: var(--text-muted); line-height: 1.4;">
        ℹ️ <strong>Collaborative Settlement Tracking:</strong> Diners report transfers; recipients confirm receipt. SettleTable does not execute or independently verify bank, card, or e-wallet transactions.
      </div>

      ${dinerPersonalCardHtml}

      <!-- Pending Reimbursements Section -->
      ${pendingTransfersHtml}

      ${unfundedWarningHtml}

      <!-- Suggested Transfers -->
      <div style="margin-bottom: 1.5rem;">
        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: var(--text-main);">
          Suggested Peer Transfers
        </div>
        ${suggestionsHtml}
      </div>

      <!-- Outstanding Balances Table -->
      <div style="margin-bottom: 1.5rem;">
        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: var(--text-main);">
          Outstanding Balances Reconciliation
        </div>
        <div style="overflow-x: auto;">
          <table class="breakdown-table" style="font-size: 0.85rem;">
            <thead>
              <tr>
                <th>Participant</th>
                <th style="text-align: right;" title="Initial net balance from restaurant bill (Paid to restaurant − Amount consumed)">Base Net (Bill)</th>
                <th style="text-align: right;" title="Total reimbursement paid to other diners">Reimbursed Others</th>
                <th style="text-align: right;" title="Total reimbursement received from other diners">Received from Peers</th>
                <th style="text-align: right;" title="Net outstanding amount still owed or to recover">Still Owed / Recoverable</th>
                <th style="text-align: right;">Status</th>
              </tr>
            </thead>
            <tbody>
              ${balanceRows}
            </tbody>
          </table>
        </div>
      </div>

      ${recordFormHtml}

      <!-- Transfer Ledger -->
      <div style="margin-top: 1.5rem;">
        <div style="font-weight: 600; font-size: 0.95rem; margin-bottom: 0.5rem; color: var(--text-main);">
          Recorded Peer Reimbursements Ledger
        </div>
        ${ledgerHtml}
        ${resolvedTransfersHtml}
      </div>
    </div>
  `;
}

// --- Event Binding ---
function bindEvents(snap) {
  // Emergency Recovery Link Banner Actions
  document.getElementById('copy-emergency-claim-btn')?.addEventListener('click', async () => {
    const input = document.getElementById('emergency-claim-url-input');
    if (input) {
      input.select();
      try {
        await navigator.clipboard.writeText(input.value);
        showAlert('Emergency recovery link copied to clipboard!', 'success');
      } catch {
        showAlert('Please copy the recovery link manually.', 'info');
      }
    }
  });

  document.getElementById('dismiss-emergency-claim-btn')?.addEventListener('click', () => {
    state.emergencyRecoveryUrl = null;
    state.emergencyRecoveryMealId = null;
    document.getElementById('organizer-emergency-banner')?.remove();
  });

  // --- Receipt Photo Modal & Lifecycle Actions ---
  initReceiptModalEvents();

  const mealId = state.mealId || snap.meal_id;
  const photoUrl = state.localPhotoUrl || (snap.has_receipt_photo ? `/api/meals/${mealId}/receipt/photo` : null);

  const thumbBtn = document.getElementById('receipt-thumb-btn');
  const viewModalBtn = document.getElementById('view-photo-modal-btn');
  if (thumbBtn && photoUrl) {
    thumbBtn.addEventListener('click', (e) => openReceiptModal(photoUrl, e.currentTarget));
    thumbBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openReceiptModal(photoUrl, e.currentTarget);
      }
    });
  }
  if (viewModalBtn && photoUrl) {
    viewModalBtn.addEventListener('click', (e) => openReceiptModal(photoUrl, e.currentTarget));
  }

  const ocrThumbBtn = document.getElementById('ocr-source-thumb-btn');
  const ocrZoomBtn = document.getElementById('ocr-source-zoom-btn');
  if (ocrThumbBtn && photoUrl) {
    ocrThumbBtn.addEventListener('click', (e) => openReceiptModal(photoUrl, e.currentTarget));
    ocrThumbBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openReceiptModal(photoUrl, e.currentTarget);
      }
    });
  }
  if (ocrZoomBtn && photoUrl) {
    ocrZoomBtn.addEventListener('click', (e) => openReceiptModal(photoUrl, e.currentTarget));
  }

  const finThumbBtn = document.getElementById('finalized-receipt-thumb-btn');
  const finViewBtn = document.getElementById('view-finalized-photo-btn');
  if (finThumbBtn) {
    const finUrl = `/api/meals/${mealId}/receipt/photo`;
    finThumbBtn.addEventListener('click', (e) => openReceiptModal(finUrl, e.currentTarget));
    finThumbBtn.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openReceiptModal(finUrl, e.currentTarget);
      }
    });
  }
  if (finViewBtn) {
    const finUrl = `/api/meals/${mealId}/receipt/photo`;
    finViewBtn.addEventListener('click', (e) => openReceiptModal(finUrl, e.currentTarget));
  }

  const replaceBtn = document.getElementById('replace-photo-btn');
  const replaceInput = document.getElementById('replace-photo-input');
  if (replaceBtn && replaceInput) {
    replaceBtn.addEventListener('click', () => {
      replaceInput.click();
    });
    replaceInput.addEventListener('change', async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file) return;
      if (file.size > 5 * 1024 * 1024) {
        showAlert('Receipt image exceeds 5MB limit. Please upload a smaller photo.', 'error');
        replaceInput.value = '';
        return;
      }
      const allowedMimes = ['image/jpeg', 'image/png', 'image/webp'];
      const mimeType = file.type || 'image/jpeg';
      if (!allowedMimes.includes(mimeType)) {
        showAlert('Unsupported image format. Please upload JPEG, PNG, or WebP.', 'error');
        replaceInput.value = '';
        return;
      }
      replaceBtn.disabled = true;
      try {
        const res = await fetch(`/api/meals/${mealId}/receipt/photo`, {
          method: 'POST',
          headers: {
            'Content-Type': mimeType,
            'X-SettleTable-Action': '1',
          },
          body: file,
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw { status: res.status, code: data?.error, message: data?.error };
        }
        if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
          URL.revokeObjectURL(state.localPhotoUrl);
        }
        state.localPhotoUrl = URL.createObjectURL(file);
        showAlert('Receipt photo replaced successfully.', 'success');
        await fetchSnapshot(true);
      } catch (err) {
        handleApiError(err);
      } finally {
        replaceBtn.disabled = false;
        replaceInput.value = '';
      }
    });
  }

  const deletePhotoBtn = document.getElementById('delete-photo-btn');
  if (deletePhotoBtn) {
    deletePhotoBtn.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to remove the stored receipt photo? This action cannot be undone.')) {
        return;
      }
      deletePhotoBtn.disabled = true;
      try {
        await apiCall(`/api/meals/${mealId}/receipt/photo`, 'DELETE');
        if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
          URL.revokeObjectURL(state.localPhotoUrl);
        }
        state.localPhotoUrl = null;
        showAlert('Receipt photo removed.', 'info');
        await fetchSnapshot(true);
      } catch (err) {
        deletePhotoBtn.disabled = false;
        handleApiError(err);
      }
    });
  }

  document.querySelectorAll('[data-simulation-action]').forEach(button => {
    button.addEventListener('click', () => requestSimulation(button.dataset.participantId, button.dataset.simulationAction === 'initiate'));
  });
  // 1. Add Item Form
  document.querySelectorAll('[data-action="service-all-items"], [data-action="service-fixed-items"]').forEach(button => {
    button.addEventListener('click', async () => {
      const adjustment = button.getAttribute('data-adjustment');
      const receipt = snap.receipt;
      if (!receipt || !receipt.items.length) return;
      const mode = button.getAttribute('data-action') === 'service-all-items' ? 'all_items' : 'fixed_items';
      const submittedSelection = [...document.querySelectorAll('.service-scope-item')]
        .filter(el => el.dataset.adjustment === adjustment).map(el => [el.value, el.checked]);
      const selected = mode === 'all_items' ? receipt.items.map(i => i.id)
        : [...document.querySelectorAll('.service-scope-item')].filter(el => el.dataset.adjustment === adjustment && el.checked).map(el => el.value);
      if (!selected.length) {
        showAlert('Select at least one eligible item for the service charge.', 'error');
        return;
      }
      const adjustments = receipt.adjustments.map(a => a.id === adjustment
        ? { ...a, scope_mode: mode, eligible_item_ids: selected }
        : a);
      button.disabled = true;
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${snap.meal_id}/apply`, 'POST', {
          kind: 'ReplaceReceipt', command_id: `scope-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          expected_revision: snap.revision, expected_financial_revision: snap.financial_revision,
          receipt: { ...receipt, adjustments },
        });
        state.mutationActive = false;
        const currentDetails = Array.from(document.querySelectorAll('details[data-service-scope]'))
          .find(el => el.dataset.serviceScope === adjustment);
        if (currentDetails) {
          const currentInputs = [...currentDetails.querySelectorAll('.service-scope-item')];
          if (currentInputs.length === submittedSelection.length && currentInputs.every((input, index) =>
            input.value === submittedSelection[index][0] && input.checked === submittedSelection[index][1])) {
            currentDetails.open = false;
            for (const input of currentInputs) {
              input.checked = selected.includes(input.value);
              input.defaultChecked = input.checked;
            }
          }
        }
        await fetchSnapshot(true);
        showAlert('Service charge scope updated. Review the receipt again before finalizing.', 'success');
      } catch (err) {
        handleApiError(err);
      } finally {
        state.mutationActive = false;
        button.disabled = false;
      }
    });
  });
  const addItemForm = document.getElementById('add-item-form');
  if (addItemForm) {
    const newItemQtyInput = document.getElementById('new-item-qty');
    const newItemQtyDec = document.getElementById('new-item-qty-dec');
    const newItemQtyInc = document.getElementById('new-item-qty-inc');
    if (newItemQtyInput && newItemQtyDec && newItemQtyInc) {
      const syncNewItemDecState = () => {
        const val = parseInt(newItemQtyInput.value, 10);
        const atMin = isNaN(val) || val <= 1;
        newItemQtyDec.disabled = atMin;
        newItemQtyDec.setAttribute('aria-disabled', atMin ? 'true' : 'false');
      };
      newItemQtyDec.addEventListener('click', () => {
        const current = parseInt(newItemQtyInput.value, 10) || 1;
        if (current > 1) {
          newItemQtyInput.value = current - 1;
          newItemQtyInput.dispatchEvent(new Event('input', { bubbles: true }));
          newItemQtyInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
        syncNewItemDecState();
      });
      newItemQtyInc.addEventListener('click', () => {
        const current = parseInt(newItemQtyInput.value, 10) || 1;
        newItemQtyInput.value = current + 1;
        newItemQtyInput.dispatchEvent(new Event('input', { bubbles: true }));
        newItemQtyInput.dispatchEvent(new Event('change', { bubbles: true }));
        syncNewItemDecState();
      });
      newItemQtyInput.addEventListener('input', syncNewItemDecState);
      newItemQtyInput.addEventListener('change', syncNewItemDecState);
      addItemForm.addEventListener('reset', () => {
        setTimeout(syncNewItemDecState, 0);
      });
      syncNewItemDecState();
    }

    addItemForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const submittedDraft = ['new-item-label', 'new-item-qty', 'new-item-price']
        .map(id => document.getElementById(id).value);
      const label = submittedDraft[0].trim();
      const qty = parseInt(submittedDraft[1], 10);
      if (!label) {
        showAlert('Item name is required', 'error');
        return;
      }
      if (!qty || qty < 1) {
        showAlert('Quantity must be at least 1', 'error');
        return;
      }

      let priceSen;
      try {
        priceSen = parseSen(document.getElementById('new-item-price').value);
        if (priceSen < 0) {
          showAlert('Price must not be negative', 'error');
          return;
        }
      } catch (err) {
        showAlert(err.message, 'error');
        return;
      }

      const currentItems = snap.receipt?.items ? [...snap.receipt.items] : [];
      // Initial empty meals retain the familiar ID. Subsequent corrections use
      // fresh identities because deleted IDs are permanently retired by authority.
      const newItemId = snap.financial_revision === 0 && currentItems.length === 0
        ? 'item-1' : freshReceiptItemId(currentItems, snap.receipt?.adjustments || []);
      currentItems.push({
        id: newItemId,
        label,
        quantity: qty,
        line_sen: priceSen,
      });

      const subtotalSen = currentItems.reduce((acc, it) => acc + (it.line_sen || 0), 0);
      const adjTotal = (snap.receipt?.adjustments || []).reduce((acc, a) => acc + (a.amount_sen || 0), 0);
      const totalSen = subtotalSen + adjTotal;

      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: `rcpt-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: currentItems,
            subtotal_sen: subtotalSen,
            total_sen: totalSen,
            adjustments: (snap.receipt?.adjustments || []).map(adj => {
              if (adj.scope_mode === 'all_items') {
                return { ...adj, eligible_item_ids: currentItems.map(i => i.id) };
              }
              return adj;
            }),
            included_tax_sen: snap.receipt?.included_tax_sen || 0,
          }
        });
        state.mutationActive = false;
        const currentForm = document.getElementById('add-item-form');
        const currentDraft = ['new-item-label', 'new-item-qty', 'new-item-price']
          .map(id => document.getElementById(id)?.value);
        if (currentForm && currentDraft.every((value, index) => value === submittedDraft[index])) {
          currentForm.reset();
        }
        await fetchSnapshot(true);
        const addedMsg = priceSen === 0
          ? `Added "${label}" (Complimentary · RM 0.00) ✓`
          : `Added "${label}" (${formatSen(priceSen)}) ✓`;
        showAlert(addedMsg, 'success');
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 1b. OCR Receipt Scanner Upload
  const ocrBtn = document.getElementById('ocr-upload-btn');
  const ocrInput = document.getElementById('ocr-file-input');
  const ocrSpinner = document.getElementById('ocr-spinner');
  if (ocrBtn && ocrInput) {
    ocrBtn.addEventListener('click', () => ocrInput.click());
    ocrInput.addEventListener('change', async (e) => {
      const file = e.target.files?.[0];
      if (!file) return;

      if (ocrSpinner) ocrSpinner.style.display = 'block';
      ocrBtn.disabled = true;

      let mimeType = file.type;
      if (!mimeType) {
        const lowerName = (file.name || '').toLowerCase();
        if (lowerName.endsWith('.png')) mimeType = 'image/png';
        else if (lowerName.endsWith('.webp')) mimeType = 'image/webp';
        else mimeType = 'image/jpeg';
      }

      if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
        URL.revokeObjectURL(state.localPhotoUrl);
      }
      state.localPhotoUrl = URL.createObjectURL(file);

      try {
        const res = await fetch(`/api/meals/${state.mealId}/ocr/extract`, {
          method: 'POST',
          headers: {
            'Content-Type': mimeType,
            'X-SettleTable-Action': '1',
          },
          body: file,
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw { status: res.status, code: data.error, message: data.error };
        }

        const candidate = data.candidate;
        if (!candidate.items || candidate.items.length === 0) {
          showAlert('No receipt items recognized from photo. Please enter items manually.', 'error');
          return;
        }

        // Stage candidate outside authoritative SQLite state until explicit organizer acceptance
        state.ocrCandidate = candidate;
        updateMealUI();

        if (candidate.route === 'manual_correction' || (candidate.issues && candidate.issues.length > 0)) {
          const detail = candidate.discrepancy_sen
            ? `Charges differ by ${formatSen(Math.abs(candidate.discrepancy_sen))}`
            : 'Review needed';
          showAlert(`⚠️ Scanned ${candidate.items.length} items (${formatSen(candidate.total_sen)}) — ${detail}`, 'conflict', true);
        } else {
          showAlert(`✓ Scanned ${candidate.items.length} items (${formatSen(candidate.total_sen)})`, 'success', true);
        }
      } catch (err) {
        if (state.localPhotoUrl && state.localPhotoUrl.startsWith('blob:')) {
          URL.revokeObjectURL(state.localPhotoUrl);
          state.localPhotoUrl = null;
        }
        state.mutationActive = false;
        if (err.status === 503 || err.code === 'ocr_unavailable') {
          showAlert('Local OCR engine unavailable. Please enter items manually.', 'error');
        } else if (err.status === 413 || err.code === 'payload_too_large') {
          showAlert('Receipt image exceeds 5MB limit. Please upload a smaller photo.', 'error');
        } else {
          handleApiError(err);
        }
      } finally {
        if (ocrSpinner) ocrSpinner.style.display = 'none';
        ocrBtn.disabled = false;
        ocrInput.value = '';
      }
    });
  }

  // 1c. Staged OCR Candidate Edit & Verification Actions
  const syncCandidateInputs = () => {
    if (!state.ocrCandidate) return;
    const cand = state.ocrCandidate;

    // Read items from candidate table
    const itemRows = document.querySelectorAll('.ocr-cand-item-row');
    const items = [];
    itemRows.forEach((row, i) => {
      const labelInput = row.querySelector('.ocr-edit-item-label');
      const qtyInput = row.querySelector('.ocr-edit-item-qty');
      const priceInput = row.querySelector('.ocr-edit-item-price');
      const label = labelInput ? (labelInput.value.trim() || `Item ${i + 1}`) : `Item ${i + 1}`;
      const qty = qtyInput ? Math.max(1, parseInt(qtyInput.value, 10) || 1) : 1;
      let lineSen = null;
      let parseError = false;
      if (priceInput) {
        const raw = priceInput.value.trim();
        if (raw === '') {
          parseError = true;
          lineSen = null;
        } else {
          try {
            lineSen = parseSen(raw);
          } catch {
            parseError = true;
            lineSen = NaN;
          }
        }
      }
      const existingId = (cand.items && cand.items[i]) ? cand.items[i].id : `item-${i + 1}`;
      items.push({ id: existingId, label, quantity: qty, line_sen: lineSen, parse_error: parseError });

      // Update unit price estimate as accessible tooltip on amount input
      const unitSen = (typeof lineSen === 'number' && !isNaN(lineSen) && qty > 0) ? Math.round(lineSen / qty) : null;
      if (priceInput) {
        if (unitSen !== null && qty > 1) {
          priceInput.title = `Estimated unit price: ~RM ${(unitSen / 100).toFixed(2)} each`;
        } else if (unitSen === 0) {
          priceInput.title = 'Complimentary item (RM 0.00)';
        } else {
          priceInput.title = 'Line total';
        }
      }

      // Update minus stepper button state
      const decBtn = row.querySelector('.ocr-qty-dec');
      if (decBtn) {
        decBtn.disabled = qty <= 1;
        decBtn.setAttribute('aria-disabled', qty <= 1 ? 'true' : 'false');
      }
    });

    // Read adjustments from candidate list
    const adjRows = document.querySelectorAll('.ocr-cand-adj-row');
    const adjustments = [];
    adjRows.forEach((row, j) => {
      const labelInput = row.querySelector('.ocr-edit-adj-label');
      const kindSelect = row.querySelector('.ocr-edit-adj-kind');
      const amountInput = row.querySelector('.ocr-edit-adj-amount');
      const label = labelInput ? (labelInput.value.trim() || 'Adjustment') : 'Adjustment';
      const kind = kindSelect ? kindSelect.value : 'service';
      let rawSen = 0;
      if (amountInput) {
        try {
          rawSen = parseSen(amountInput.value, true);
        } catch {
          rawSen = 0;
        }
      }
      let amountSen = rawSen;
      if (kind === 'discount') {
        amountSen = -Math.abs(rawSen);
      } else if (kind === 'service' || kind === 'tax') {
        amountSen = Math.abs(rawSen);
      } else if (kind === 'rounding') {
        if (amountInput && amountInput.value.trim().startsWith('-')) {
          amountSen = -Math.abs(rawSen);
        } else {
          amountSen = Math.abs(rawSen);
        }
      }
      const existingId = (cand.adjustments && cand.adjustments[j]) ? cand.adjustments[j].id : `adj-${j + 1}`;
      const existingRationale = (cand.adjustments && cand.adjustments[j] && cand.adjustments[j].rationale)
        ? cand.adjustments[j].rationale
        : `${label} adjustment`;
      const mode = row.querySelector('.ocr-adj-scope')?.value === 'all_items' ? 'all_items' : 'fixed_items';
      const eligible = mode === 'all_items' ? items.map(it => it.id)
        : [...row.querySelectorAll('.ocr-scope-item:checked')].map(el => el.value);
      adjustments.push({
        id: existingId,
        label,
        kind,
        amount_sen: amountSen,
        eligible_item_ids: eligible,
        rationale: existingRationale,
        scope_mode: mode,
      });
    });

    // Read included tax
    const incTaxInput = document.getElementById('ocr-edit-included-tax');
    let incTaxSen = 0;
    if (incTaxInput) {
      try {
        incTaxSen = parseSen(incTaxInput.value);
      } catch {
        incTaxSen = 0;
      }
    }

    const subtotalSen = items.reduce((acc, it) => acc + (typeof it.line_sen === 'number' && !isNaN(it.line_sen) && it.line_sen >= 0 ? it.line_sen : 0), 0);
    const adjTotalSen = adjustments.reduce((acc, a) => acc + (a.amount_sen || 0), 0);
    const totalSen = subtotalSen + adjTotalSen;

    cand.items = items;
    cand.adjustments = adjustments;
    cand.included_tax_sen = incTaxSen;
    cand.subtotal_sen = subtotalSen;
    cand.total_sen = totalSen;

    const subtotalValEl = document.getElementById('ocr-cand-subtotal-val');
    const totalValEl = document.getElementById('ocr-cand-total-val');
    if (subtotalValEl) subtotalValEl.textContent = formatSen(subtotalSen);
    if (totalValEl) totalValEl.textContent = formatSen(totalSen);
  };

  if (state.ocrCandidate) {
    document.querySelectorAll('.ocr-adj-scope, .ocr-scope-item').forEach(el => {
      el.addEventListener('change', () => { syncCandidateInputs(); updateMealUI(); });
    });
    document.querySelectorAll('.ocr-edit-item-label, .ocr-edit-item-qty, .ocr-edit-item-price, .ocr-edit-adj-label, .ocr-edit-adj-kind, .ocr-edit-adj-amount, #ocr-edit-included-tax').forEach(el => {
      el.addEventListener('input', syncCandidateInputs);
      el.addEventListener('change', syncCandidateInputs);
    });

    // Stepper Decrement Button
    document.querySelectorAll('.ocr-qty-dec').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = btn.getAttribute('data-idx');
        const input = document.getElementById(`ocr-item-qty-${idx}`);
        if (input) {
          let val = parseInt(input.value, 10) || 1;
          if (val > 1) {
            val -= 1;
            input.value = val;
            btn.disabled = val <= 1;
            btn.setAttribute('aria-disabled', val <= 1 ? 'true' : 'false');
            syncCandidateInputs();
          }
        }
      });
    });

    // Stepper Increment Button
    document.querySelectorAll('.ocr-qty-inc').forEach(btn => {
      btn.addEventListener('click', () => {
        const idx = btn.getAttribute('data-idx');
        const input = document.getElementById(`ocr-item-qty-${idx}`);
        if (input) {
          let val = parseInt(input.value, 10) || 1;
          val += 1;
          input.value = val;
          const decBtn = document.querySelector(`.ocr-qty-dec[data-idx="${idx}"]`);
          if (decBtn) {
            decBtn.disabled = false;
            decBtn.setAttribute('aria-disabled', 'false');
          }
          syncCandidateInputs();
        }
      });
    });

    // Stepper Numeric Input Blur Sanitization
    document.querySelectorAll('.ocr-edit-item-qty').forEach(input => {
      input.addEventListener('blur', () => {
        let val = parseInt(input.value, 10);
        if (isNaN(val) || val < 1) {
          val = 1;
          input.value = 1;
        }
        const idx = input.getAttribute('data-idx');
        const decBtn = document.querySelector(`.ocr-qty-dec[data-idx="${idx}"]`);
        if (decBtn) {
          decBtn.disabled = val <= 1;
          decBtn.setAttribute('aria-disabled', val <= 1 ? 'true' : 'false');
        }
        syncCandidateInputs();
      });
    });

    // Category Selector change: auto-suggest default label if untouched
    document.querySelectorAll('.ocr-edit-adj-kind').forEach(select => {
      select.addEventListener('change', () => {
        const idx = select.getAttribute('data-adj-idx');
        const labelInput = document.getElementById(`ocr-adj-label-${idx}`);
        if (labelInput) {
          const currentLabel = labelInput.value.trim();
          const defaultLabels = ['Service Charge', 'SST Tax', 'SST / Tax', 'Discount', 'Rounding Adjustment', 'Adjustment'];
          if (defaultLabels.includes(currentLabel) || currentLabel === '') {
            const kindDefaults = {
              service: 'Service Charge',
              tax: 'SST Tax',
              discount: 'Discount',
              rounding: 'Rounding Adjustment',
            };
            labelInput.value = kindDefaults[select.value] || 'Adjustment';
          }
        }
        syncCandidateInputs();
      });
    });

    document.getElementById('ocr-add-item-btn')?.addEventListener('click', () => {
      syncCandidateInputs();
      const items = state.ocrCandidate.items || [];
      items.push({
        id: freshReceiptItemId(items, state.ocrCandidate.adjustments || []),
        label: `Item ${items.length + 1}`,
        quantity: 1,
        line_sen: 1000,
      });
      state.ocrCandidate.items = items;
      state.ocrCandidate.subtotal_sen = items.reduce((s, i) => s + (i.line_sen || 0), 0);
      state.ocrCandidate.total_sen = state.ocrCandidate.subtotal_sen + (state.ocrCandidate.adjustments || []).reduce((s, a) => s + (a.amount_sen || 0), 0);
      updateMealUI();
    });

    document.querySelectorAll('.ocr-del-item-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        syncCandidateInputs();
        const idx = parseInt(btn.getAttribute('data-idx'), 10);
        if (state.ocrCandidate.items && state.ocrCandidate.items.length > 1) {
          state.ocrCandidate.items.splice(idx, 1);
          state.ocrCandidate.subtotal_sen = state.ocrCandidate.items.reduce((s, i) => s + (i.line_sen || 0), 0);
          state.ocrCandidate.total_sen = state.ocrCandidate.subtotal_sen + (state.ocrCandidate.adjustments || []).reduce((s, a) => s + (a.amount_sen || 0), 0);
          updateMealUI();
        } else {
          showAlert('Candidate must have at least one receipt item.', 'conflict');
        }
      });
    });

    document.getElementById('ocr-add-adj-btn')?.addEventListener('click', () => {
      syncCandidateInputs();
      const adjs = state.ocrCandidate.adjustments || [];
      const allItemIds = (state.ocrCandidate.items || []).map(it => it.id);
      adjs.push({
        id: `adj-${adjs.length + 1}`,
        label: 'Service Charge',
        kind: 'service',
        amount_sen: 100,
        eligible_item_ids: allItemIds,
      });
      state.ocrCandidate.adjustments = adjs;
      state.ocrCandidate.total_sen = (state.ocrCandidate.subtotal_sen || 0) + adjs.reduce((s, a) => s + (a.amount_sen || 0), 0);
      updateMealUI();
    });

    document.querySelectorAll('.ocr-del-adj-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        syncCandidateInputs();
        const idx = parseInt(btn.getAttribute('data-adj-idx'), 10);
        if (state.ocrCandidate.adjustments) {
          state.ocrCandidate.adjustments.splice(idx, 1);
          state.ocrCandidate.total_sen = (state.ocrCandidate.subtotal_sen || 0) + state.ocrCandidate.adjustments.reduce((s, a) => s + (a.amount_sen || 0), 0);
          updateMealUI();
        }
      });
    });
  }

  const ocrAcceptBtn = document.getElementById('ocr-accept-btn');
  const ocrDiscardBtn = document.getElementById('ocr-discard-btn');
  if (ocrAcceptBtn && state.ocrCandidate) {
    ocrAcceptBtn.addEventListener('click', async () => {
      syncCandidateInputs();
      const candidate = state.ocrCandidate;
      if (!candidate) return;

      if (!candidate.items || candidate.items.length === 0) {
        showAlert('Candidate must have at least one receipt item.', 'error');
        return;
      }

      for (const it of candidate.items) {
        if (!it.label || it.line_sen === null || isNaN(it.line_sen) || it.line_sen < 0) {
          showAlert(`Item "${it.label || 'Unnamed'}" must have a valid name and non-negative price (RM 0.00 or greater)`, 'error');
          return;
        }
      }

      const allItemIds = candidate.items.map(i => i.id);
      const itemIdSet = new Set(allItemIds);
      const cleanAdjustments = (candidate.adjustments || []).map((adj, idx) => {
        const filteredEligible = (adj.eligible_item_ids || []).filter(id => itemIdSet.has(id));
        const finalEligible = adj.scope_mode === 'all_items' ? allItemIds : filteredEligible;
        const fallbackRationale = `${adj.label || adj.kind || 'Receipt'} adjustment`;
        return {
          id: adj.id || `adj-${idx + 1}`,
          label: adj.label || adj.kind || 'Adjustment',
          kind: adj.kind || 'rounding',
          amount_sen: adj.amount_sen,
          eligible_item_ids: finalEligible,
          rationale: (adj.rationale && adj.rationale.trim()) ? adj.rationale.trim() : fallbackRationale,
          scope_mode: adj.scope_mode || null,
        };
      });
      if (cleanAdjustments.some(adj => adj.eligible_item_ids.length === 0)) {
        showAlert('An adjustment has no eligible items. Remove or correct the adjustment before applying the receipt.', 'error');
        return;
      }

      ocrAcceptBtn.disabled = true;
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReplaceReceipt',
          command_id: `ocr-rcpt-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: candidate.items,
            subtotal_sen: candidate.subtotal_sen,
            total_sen: candidate.total_sen,
            adjustments: cleanAdjustments,
            included_tax_sen: candidate.included_tax_sen || 0,
          }
        });
        state.ocrCandidate = null;
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Scanned receipt accepted and applied to draft. Mandatory human receipt review is still required before finalization.', 'success');
        navigateToWorkflowSection('review-section', 'review-confirm-check');
      } catch (err) {
        state.mutationActive = false;
        ocrAcceptBtn.disabled = false;
        handleApiError(err);
      }
    });
  }
  if (ocrDiscardBtn) {
    ocrDiscardBtn.addEventListener('click', () => {
      state.ocrCandidate = null;
      updateMealUI();
      showAlert('Scanned receipt candidate discarded. Existing receipt unchanged.', 'info');
    });
  }

  // 2. Review Confirmation Checkbox & Button
  const reviewCheck = document.getElementById('review-confirm-check');
  const reviewBtn = document.getElementById('review-submit-btn');
  if (reviewCheck && reviewBtn) {
    reviewCheck.addEventListener('change', () => {
      reviewBtn.disabled = !reviewCheck.checked;
    });

    reviewBtn.addEventListener('click', async () => {
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'ReviewReceipt',
          command_id: `rev-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt_digest: snap.receipt_digest,
        });
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Receipt verified and sealed ✓', 'success');
        navigateAfterReceiptReview();
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 3. Issue Invite Buttons
  document.querySelectorAll('.issue-invite-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const partId = btn.getAttribute('data-id');
      try {
        btn.disabled = true;
        btn.textContent = 'Creating...';
        const invRes = await apiCall(`/api/meals/${state.mealId}/invitations`, 'POST', {
          participant_id: partId,
          invite_ttl: 86400,
        });
        if (invRes?.token) {
          const inviteUrl = invRes.invite_url || `${window.location.origin}/#/invite/${invRes.token}`;
          state.issuedTokens[partId] = inviteUrl;
          navigator.clipboard.writeText(inviteUrl).catch(() => {});
          showAlert(`Invite link created & copied for ${partId}!`, 'success');
          await fetchSnapshot(true);
        }
      } catch (err) {
        handleApiError(err);
      }
    });
  });

  // 4. Copy Active Invite Link
  document.querySelectorAll('.copy-invite-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const partId = btn.getAttribute('data-part');
      const cachedUrl = state.issuedTokens[partId];
      if (cachedUrl) {
        navigator.clipboard.writeText(cachedUrl).then(() => {
          showAlert(`Invite link copied to clipboard for ${partId}!`, 'success');
        }).catch(() => {
          showAlert(`Link: ${cachedUrl}`, 'info');
        });
      } else {
        showAlert(`Invite is already active for ${partId}. Raw tokens are not stored across page reloads. If the link was lost, click "Revoke & Reissue".`, 'info');
      }
    });
  });

  // 4-rev. Revoke Active Invite Link
  document.querySelectorAll('.revoke-invite-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const partId = btn.getAttribute('data-part');
      const snap = state.snapshot;
      if (!snap || !snap.meal_id || !partId) return;
      if (!confirm(`Revoke active invitation link for ${partId}? Any unused link will stop working.`)) return;
      btn.disabled = true;
      btn.textContent = 'Revoking...';
      try {
        const cmd = {
          command_id: `rev-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          kind: 'RevokeInvitation',
          participant_id: partId,
          expected_revision: snap.revision,
        };
        await apiCall(`/api/meals/${snap.meal_id}/apply`, 'POST', cmd);
        delete state.issuedTokens[partId];
        showAlert(`Invitation revoked for ${partId}.`, 'info');
        await fetchSnapshot(true);
      } catch (err) {
        btn.disabled = false;
        btn.textContent = 'Revoke';
        handleApiError(err);
      }
    });
  });

  // 4-reis. Revoke & Reissue Lost Invite Link
  document.querySelectorAll('.reissue-invite-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const partId = btn.getAttribute('data-part');
      const snap = state.snapshot;
      if (!snap || !snap.meal_id || !partId) return;
      btn.disabled = true;
      btn.textContent = 'Reissuing...';
      try {
        // Step 1: Revoke existing active invitation
        const cmd = {
          command_id: `rev-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
          kind: 'RevokeInvitation',
          participant_id: partId,
          expected_revision: snap.revision,
        };
        await apiCall(`/api/meals/${snap.meal_id}/apply`, 'POST', cmd);

        // Step 2: Issue fresh invitation
        const invRes = await apiCall(`/api/meals/${snap.meal_id}/invitations`, 'POST', {
          participant_id: partId,
          invite_ttl: 86400,
        });

        if (invRes?.token) {
          const inviteUrl = invRes.invite_url || `${window.location.origin}/#/invite/${invRes.token}`;
          state.issuedTokens[partId] = inviteUrl;
          navigator.clipboard.writeText(inviteUrl).then(() => {
            showAlert(`Previous link revoked. New invite link created & copied for ${partId}!`, 'success');
          }).catch(() => {
            showAlert(`New invite link created for ${partId}!`, 'success');
          });
          await fetchSnapshot(true);
        }
      } catch (err) {
        btn.disabled = false;
        btn.textContent = '🔄 Revoke & Reissue';
        handleApiError(err);
      }
    });
  });

  // 4a. Copy General Table Join Link
  const copyGenBtn = document.getElementById('copy-general-join-btn');
  if (copyGenBtn) {
    copyGenBtn.addEventListener('click', () => {
      const mealId = copyGenBtn.getAttribute('data-meal');
      const joinUrl = `${window.location.origin}/join/${mealId}`;
      navigator.clipboard.writeText(joinUrl).then(() => {
        showAlert('General table join link copied to clipboard!', 'success');
        copyGenBtn.textContent = 'Copied! ✓';
        setTimeout(() => { copyGenBtn.textContent = '📋 Copy Join Link'; }, 2000);
      }).catch(() => {
        prompt('Copy this table join link:', joinUrl);
      });
    });
  }

  // 4a-rec. Generate / Copy Emergency Organizer Recovery Link
  const genRecBtn = document.getElementById('gen-recovery-link-btn');
  if (genRecBtn) {
    genRecBtn.addEventListener('click', async () => {
      if (state.recoveryLink) {
        navigator.clipboard.writeText(state.recoveryLink).then(() => {
          showAlert('Organizer emergency recovery link copied to clipboard! Keep it safe.', 'success');
          genRecBtn.textContent = 'Copied! ✓';
          setTimeout(() => { genRecBtn.textContent = '📋 Copy Recovery Link'; }, 2000);
        }).catch(() => {
          prompt('Copy this emergency recovery link:', state.recoveryLink);
        });
        return;
      }

      genRecBtn.disabled = true;
      genRecBtn.textContent = 'Generating...';
      try {
        const res = await apiCall(`/api/meals/${state.mealId}/organizer-claims`, 'POST', {});
        if (res?.ok && res.claim_url) {
          state.recoveryLink = res.claim_url;
          saveRecentMeal({
            meal_id: state.mealId,
            title: state.snapshot?.meal_id || state.mealId,
            role: 'organizer',
            created_at: Date.now(),
          });
          genRecBtn.disabled = false;
          genRecBtn.textContent = 'Copied! ✓';
          navigator.clipboard.writeText(res.claim_url).then(() => {
            showAlert('Emergency recovery link created and copied to clipboard! Bookmark or store it safely.', 'success');
          }).catch(() => {
            prompt('Copy this emergency recovery link:', res.claim_url);
          });
          setTimeout(() => { genRecBtn.textContent = '📋 Copy Recovery Link'; }, 2000);
        }
      } catch (err) {
        genRecBtn.disabled = false;
        genRecBtn.textContent = '🔑 Create Recovery Link';
        showAlert(`Failed to generate recovery link: ${err.message}`, 'error');
      }
    });
  }

  // 4a2. Approve Join Request Buttons
  document.querySelectorAll('.approve-join-req-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reqId = btn.getAttribute('data-req');
      btn.disabled = true;
      btn.textContent = 'Approving...';
      try {
        await apiCall(`/api/meals/${state.mealId}/join-requests/${reqId}/review`, 'POST', { action: 'approve' });
        showAlert('Diner join request approved!', 'success');
        await fetchSnapshot(true);
      } catch (err) {
        handleApiError(err);
      }
    });
  });

  // 4a3. Reject Join Request Buttons
  document.querySelectorAll('.reject-join-req-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reqId = btn.getAttribute('data-req');
      btn.disabled = true;
      btn.textContent = 'Declining...';
      try {
        await apiCall(`/api/meals/${state.mealId}/join-requests/${reqId}/review`, 'POST', { action: 'reject' });
        showAlert('Join request declined.', 'info');
        await fetchSnapshot(true);
      } catch (err) {
        handleApiError(err);
      }
    });
  });

  const activeParts = snap.participants?.filter(p => !snap.inactive_participant_ids?.includes(p.id)) || [];

  // 4b. CONCEPT C: Organizer Item-First Allocation Event Handlers
  if (snap.is_organizer) {
    // 1. Quick Assign (+ Diner)
    document.querySelectorAll('[data-action="hybrid-quick-assign"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const itemId = btn.getAttribute('data-item');
        const targetPid = btn.getAttribute('data-target');
        const rev = parseInt(btn.getAttribute('data-rev'), 10);
        const item = snap.receipt?.items?.find(i => i.id === itemId);
        if (!item) return;
        if (item.line_sen === 0) {
          showAlert('Complimentary items do not require allocation.', 'info');
          return;
        }

        const claims = snap.claims?.filter(c => c.item_id === itemId) || [];
        const claimedRat = claims.reduce((acc, c) => addFractions(acc, c.quantity), 0);
        const unassignedRat = subtractFractions(item.quantity, claimedRat);
        const unassignedNum = ratToNum(unassignedRat);

        if (unassignedNum <= 0) {
          openItemEditor(itemId);
          showAlert('Item is already fully allocated. Adjust existing portions in Details / Split.', 'info');
          return;
        }

        if (unassignedNum < 1) {
          openItemEditor(itemId);
          showAlert('Item has a fractional remaining portion. Use Details / Split to allocate exact fractions.', 'info');
          return;
        }

        const assignQty = 1;
        const otherClaims = claims
          .filter(c => c.participant_id !== targetPid)
          .map(c => ({ participant_id: c.participant_id, quantity: c.quantity }));
        const newAllocs = [...otherClaims, { participant_id: targetPid, quantity: assignQty }];
        await executeSetItemAllocations(itemId, newAllocs, rev);
      });
    });

    // 2. Open / Toggle Details (Pills & Buttons)
    document.querySelectorAll('[data-action="hybrid-open-details"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const itemId = btn.getAttribute('data-item');
        openItemEditor(itemId, btn);
      });
    });

    document.querySelectorAll('[data-action="hybrid-toggle-details"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const itemId = btn.getAttribute('data-item');
        toggleItemEditor(itemId, btn);
      });
    });

    // 3. Selective Equal Split: Toggle Diner Checkbox
    document.querySelectorAll('[data-action="toggle-split-diner"]').forEach(input => {
      input.addEventListener('change', () => {
        const itemId = input.getAttribute('data-item');
        const targetPid = input.getAttribute('data-target');
        if (!state.selectedSplitDiners.has(itemId)) {
          state.selectedSplitDiners.set(itemId, new Set(activeParts.map(p => p.id)));
        }
        const set = state.selectedSplitDiners.get(itemId);
        if (input.checked) {
          set.add(targetPid);
        } else {
          set.delete(targetPid);
        }
        updateMealUI();
      });
    });

    // 4. Selective Equal Split: Select All & Clear Helpers
    document.querySelectorAll('[data-action="split-select-all"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const itemId = btn.getAttribute('data-item');
        state.selectedSplitDiners.set(itemId, new Set(activeParts.map(p => p.id)));
        updateMealUI();
      });
    });

    document.querySelectorAll('[data-action="split-clear-all"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const itemId = btn.getAttribute('data-item');
        state.selectedSplitDiners.set(itemId, new Set());
        updateMealUI();
      });
    });

    // 5. Apply Selective Equal Split
    document.querySelectorAll('[data-action="apply-equal-split"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const itemId = btn.getAttribute('data-item');
        const rev = parseInt(btn.getAttribute('data-rev'), 10);
        const item = snap.receipt?.items?.find(i => i.id === itemId);
        if (!item) return;
        if (item.line_sen === 0) {
          showAlert('Complimentary items do not require allocation.', 'info');
          return;
        }

        const set = state.selectedSplitDiners.get(itemId);
        const selectedIds = Array.from(set || []);
        if (selectedIds.length === 0) return;

        const existingClaims = (snap.claims || []).filter(c => c.item_id === itemId);
        if (existingClaims.length > 0) {
          const existingSummary = existingClaims.map(c => {
            const p = activeParts.find(part => part.id === c.participant_id);
            return `${p ? p.name : c.participant_id} (${formatRat(c.quantity)})`;
          }).join(', ');
          const ok = window.confirm(`Replace current allocations on "${item.label}" (${existingSummary}) with equal split among ${selectedIds.length} diners?`);
          if (!ok) return;
        }

        const itemTotalQty = ratToNum(item.quantity);
        const shareRat = makeReducedFraction(itemTotalQty, selectedIds.length);
        const allocations = selectedIds.map(pid => ({ participant_id: pid, quantity: shareRat }));
        await executeSetItemAllocations(itemId, allocations, rev);
      });
    });

    // 6. Stepper (+ / -) in Expanded Editor
    document.querySelectorAll('[data-action="hybrid-step"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const itemId = btn.getAttribute('data-item');
        const targetPid = btn.getAttribute('data-target');
        const rev = parseInt(btn.getAttribute('data-rev'), 10);
        const step = parseInt(btn.getAttribute('data-step'), 10);

        const claim = (snap.claims || []).find(c => c.item_id === itemId && c.participant_id === targetPid);
        const currentRat = claim ? claim.quantity : 0;
        let newQty;
        if (step > 0) {
          const num = ratToNum(currentRat);
          newQty = Math.floor(num) + 1;
        } else {
          const num = ratToNum(currentRat);
          if (Array.isArray(currentRat)) {
            newQty = Math.floor(num);
          } else {
            newQty = Math.max(0, num - 1);
          }
        }

        const otherClaims = (snap.claims || [])
          .filter(c => c.item_id === itemId && c.participant_id !== targetPid)
          .map(c => ({ participant_id: c.participant_id, quantity: c.quantity }));
        const allocations = [...otherClaims];
        if (newQty > 0) {
          allocations.push({ participant_id: targetPid, quantity: newQty });
        }
        await executeSetItemAllocations(itemId, allocations, rev);
      });
    });

    // 7. Fraction Buttons in Expanded Editor (1/3, 1/2, All, 0)
    document.querySelectorAll('[data-action="hybrid-fraction"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const itemId = btn.getAttribute('data-item');
        const targetPid = btn.getAttribute('data-target');
        const rev = parseInt(btn.getAttribute('data-rev'), 10);
        const frac = btn.getAttribute('data-frac');
        const item = snap.receipt?.items?.find(i => i.id === itemId);
        if (!item) return;
        if (item.line_sen === 0) {
          showAlert('Complimentary items do not require allocation.', 'info');
          return;
        }

        const otherClaims = (snap.claims || [])
          .filter(c => c.item_id === itemId && c.participant_id !== targetPid)
          .map(c => ({ participant_id: c.participant_id, quantity: c.quantity }));
        const allocations = [...otherClaims];

        if (frac === '1/3') {
          allocations.push({ participant_id: targetPid, quantity: [1, 3] });
        } else if (frac === '1/2') {
          allocations.push({ participant_id: targetPid, quantity: [1, 2] });
        } else if (frac === 'all') {
          const otherSumRat = otherClaims.reduce((acc, c) => addFractions(acc, c.quantity), 0);
          const remRat = subtractFractions(item.quantity, otherSumRat);
          if (ratToNum(remRat) <= 0) {
            showAlert('No unassigned portion remains for this item.', 'info');
            return;
          }
          allocations.push({ participant_id: targetPid, quantity: remRat });
        } else if (frac === '0') {
          // Omitting targetPid unassigns them
        }
        await executeSetItemAllocations(itemId, allocations, rev);
      });
    });

    // 8. Clear All Claims on Item
    document.querySelectorAll('[data-action="hybrid-clear-item"]').forEach(btn => {
      btn.addEventListener('click', async () => {
        const itemId = btn.getAttribute('data-item');
        const rev = parseInt(btn.getAttribute('data-rev'), 10);
        const item = snap.receipt?.items?.find(i => i.id === itemId);
        const label = item ? item.label : 'item';

        const existingClaims = (snap.claims || []).filter(c => c.item_id === itemId);
        if (existingClaims.length === 0) return;

        const ok = window.confirm(`Clear all allocations for "${label}"?`);
        if (!ok) return;

        await executeSetItemAllocations(itemId, [], rev);
      });
    });

    // 9. Close Sheet / Close Details
    document.querySelectorAll('[data-action="close-sheet"]').forEach(el => {
      el.addEventListener('click', () => {
        closeMobileSheet();
      });
    });

    document.querySelectorAll('[data-action="hybrid-close-details"]').forEach(el => {
      el.addEventListener('click', () => {
        const itemId = el.getAttribute('data-item');
        if (itemId) state.expandedHybridItemIds.delete(itemId);
        updateMealUI();
      });
    });
  }

  // 5. Diner Self-Claiming Adjustments (+ / - / Claim All)
  document.querySelectorAll('.claim-inc-btn, .claim-dec-btn, .claim-all-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const itemId = btn.getAttribute('data-id');
      const item = snap.receipt?.items?.find(i => i.id === itemId);
      if (item && item.line_sen === 0) {
        showAlert('Complimentary items do not require allocation.', 'info');
        return;
      }
      const currentVal = parseFloat(btn.getAttribute('data-current') || '0');
      const targetUserId = btn.getAttribute('data-target') || state.currentUserId;
      const rev = parseInt(btn.getAttribute('data-rev'), 10);
      let targetVal = currentVal;

      if (btn.classList.contains('claim-inc-btn')) {
        targetVal = currentVal + 1;
      } else if (btn.classList.contains('claim-dec-btn')) {
        targetVal = Math.max(0, currentVal - 1);
      } else if (btn.classList.contains('claim-all-btn')) {
        const total = parseFloat(btn.getAttribute('data-total') || '1');
        const unassigned = parseFloat(btn.getAttribute('data-unassigned') || '0');
        if (currentVal === total) {
          targetVal = 0;
        } else if (unassigned > 0) {
          targetVal = currentVal + unassigned;
        } else {
          targetVal = total;
        }
      }

      state.mutationActive = true;
      try {
        const payload = {
          kind: 'SetOwnQuantity',
          command_id: `own-${crypto.randomUUID()}`,
          item_id: itemId,
          quantity: targetVal === 0 ? null : targetVal,
          expected_item_revision: rev,
          expected_financial_revision: snap.financial_revision,
        };

        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', payload);
        state.mutationActive = false;
        await fetchSnapshot(true);
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err, itemId);
      } finally {
        state.mutationActive = false;
      }
    });
  });

  // 6. Finalize Meal
  const finalizeBtn = document.getElementById('finalize-btn');
  if (finalizeBtn) {
    finalizeBtn.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to finalize the meal? Claims will be locked.')) return;
      state.mutationActive = true;
      try {
        await apiCall(`/api/meals/${state.mealId}/apply`, 'POST', {
          kind: 'Finalize',
          command_id: `fin-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
        });
        state.mutationActive = false;
        await fetchSnapshot(true);
        showAlert('Meal finalized successfully!', 'success');
        navigateToWorkflowSection('apportionment-section', 'apportionment-heading');
      } catch (err) {
        state.mutationActive = false;
        handleApiError(err);
      } finally {
        state.mutationActive = false;
      }
    });
  }

  // 7. Notion Export
  const parentInputElem = document.getElementById('notion-parent-id');
  if (parentInputElem) {
    parentInputElem.addEventListener('input', () => {
      const parsed = extractNotionUuid(parentInputElem.value);
      if (parsed && (parentInputElem.value.includes('http') || parentInputElem.value.length === 32)) {
        parentInputElem.value = parsed;
      }
      state.notionParentId = parentInputElem.value;
    });
  }

  const tokenInputElem = document.getElementById('notion-token');
  if (tokenInputElem) {
    tokenInputElem.addEventListener('input', () => {
      state.notionToken = tokenInputElem.value;
    });
  }

  const notionBtn = document.getElementById('notion-export-btn');
  if (notionBtn) {
    notionBtn.addEventListener('click', async () => {
      const parentInput = document.getElementById('notion-parent-id');
      const tokenInput = document.getElementById('notion-token');
      const spinner = document.getElementById('notion-export-spinner');
      const resultDiv = document.getElementById('notion-export-result');

      const rawParent = (parentInput?.value || '').trim();
      const parentId = extractNotionUuid(rawParent);
      const token = (tokenInput?.value || '').trim();

      if (!parentId) {
        showAlert('Please enter a valid Notion Parent Page UUID or paste your Notion page URL.', 'error');
        return;
      }
      if (parentInput) parentInput.value = parentId;

      notionBtn.disabled = true;
      if (spinner) spinner.style.display = 'block';
      if (resultDiv) resultDiv.style.display = 'none';

      try {
        const includePhoto = Boolean(document.getElementById('notion-include-photo')?.checked);
        const payload = {
          parent_id: parentId,
          parent_type: 'page_id',
          mode: 'compact',
          include_receipt_photo: includePhoto,
        };
        if (token) payload.token = token;

        const res = await fetch(`/api/meals/${state.mealId}/export/notion`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-SettleTable-Action': '1',
          },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.ok) {
          throw { status: res.status, code: data.error, message: data.error };
        }

        const exp = data.export || {};
        if (exp.status === 'in_progress') {
          if (resultDiv) {
            resultDiv.style.display = 'block';
            resultDiv.style.backgroundColor = 'rgba(99, 102, 241, 0.1)';
            resultDiv.style.border = '1px solid rgba(99, 102, 241, 0.3)';
            resultDiv.style.color = 'var(--accent-indigo)';
            resultDiv.innerHTML = '<strong>⏳ Archiving to Notion...</strong><br/><span style="font-size:0.8rem;">Export running asynchronously in background. Live dining updates continue uninterrupted.</span>';
          }
          pollNotionExportStatus((success) => {
            notionBtn.disabled = false;
            if (spinner) spinner.style.display = 'none';
          });
          return;
        }

        state.notionExport = exp;
        updateMealUI();
        showAlert('Report exported to Notion successfully!', 'success');
      } catch (err) {
        if (resultDiv) {
          resultDiv.style.display = 'block';
          resultDiv.style.backgroundColor = 'rgba(239, 68, 68, 0.1)';
          resultDiv.style.border = '1px solid rgba(239, 68, 68, 0.3)';
          resultDiv.style.color = 'var(--accent-rose)';
          resultDiv.textContent = `Export failed: ${err.code || err.message || 'unknown error'}`;
        }
        showAlert(`Notion export rejected: ${err.code || err.message}`, 'error');
      } finally {
        notionBtn.disabled = false;
        if (spinner) spinner.style.display = 'none';
      }
    });
  }

  // 1. Incognito / Private Window Test Buttons
  const handleTestIncognito = (btn) => {
    const url = btn.getAttribute('data-url');
    if (!url) return;
    navigator.clipboard.writeText(url).then(() => {
      showAlert('Report link copied to clipboard! Open a Private / Incognito window to verify view-only access without logging in.', 'info');
    }).catch(() => {
      prompt('Copy this report URL to test in a private/incognito window:', url);
    });
  };

  const testIncogBtn = document.getElementById('test-notion-incognito-btn');
  if (testIncogBtn) testIncogBtn.addEventListener('click', () => handleTestIncognito(testIncogBtn));

  const testSharedIncogBtn = document.getElementById('test-shared-incognito-btn');
  if (testSharedIncogBtn) testSharedIncogBtn.addEventListener('click', () => handleTestIncognito(testSharedIncogBtn));

  // 2. Share Candidate Notion URL (Exported Page Link)
  const shareCandidateBtn = document.getElementById('share-candidate-notion-url-btn');
  const candidateConfirmBox = document.getElementById('notion-candidate-share-confirm');
  if (shareCandidateBtn && candidateConfirmBox) {
    shareCandidateBtn.addEventListener('click', () => {
      candidateConfirmBox.style.display = candidateConfirmBox.style.display === 'none' ? 'block' : 'none';
      if (candidateConfirmBox.style.display === 'block') {
        candidateConfirmBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    });
  }

  const cancelCandidateBtn = document.getElementById('cancel-share-candidate-btn');
  if (cancelCandidateBtn && candidateConfirmBox) {
    cancelCandidateBtn.addEventListener('click', () => {
      candidateConfirmBox.style.display = 'none';
    });
  }

  const confirmCandidateBtn = document.getElementById('confirm-share-candidate-btn');
  if (confirmCandidateBtn) {
    confirmCandidateBtn.addEventListener('click', async () => {
      const candidateUrl = confirmCandidateBtn.getAttribute('data-url');
      if (!candidateUrl) return;

      const validation = validateNotionSharingUrl(candidateUrl);
      if (!validation.valid) {
        showAlert(validation.error, 'error');
        return;
      }

      confirmCandidateBtn.disabled = true;
      confirmCandidateBtn.textContent = 'Sharing...';
      try {
        const res = await apiCall(`/api/meals/${state.mealId}/export/notion/public-url`, 'POST', { public_url: validation.url });
        if (res?.ok) {
          if (state.notionExport) state.notionExport.public_url = res.public_url;
          if (state.snapshot) state.snapshot.notion_public_url = res.public_url;
          showAlert('Exported Notion report shared with diners! Verify view-only access in a private tab.', 'success');
          updateMealUI();
        }
      } catch (err) {
        confirmCandidateBtn.disabled = false;
        confirmCandidateBtn.textContent = 'Confirm & Share with Diners';
        handleApiError(err);
      }
    });
  }

  // 3. Save Custom Notion Public Web Link (with sensitive credential interception)
  const saveNotionPubBtn = document.getElementById('save-notion-public-url-btn');
  if (saveNotionPubBtn) {
    saveNotionPubBtn.addEventListener('click', async () => {
      const input = document.getElementById('notion-public-url-input');
      const val = (input?.value || '').trim();
      const alertBox = document.getElementById('notion-url-validation-alert');

      const validation = validateNotionSharingUrl(val);
      if (!validation.valid) {
        if (alertBox) {
          alertBox.style.display = 'block';
          alertBox.style.padding = '8px';
          alertBox.style.borderRadius = '4px';
          alertBox.style.background = validation.isSensitive ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)';
          alertBox.style.border = validation.isSensitive ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(245, 158, 11, 0.4)';
          alertBox.style.color = validation.isSensitive ? 'var(--accent-rose)' : '#fde68a';
          alertBox.textContent = validation.error;
        }
        showAlert(validation.error, 'error');
        return;
      }

      if (alertBox) alertBox.style.display = 'none';
      saveNotionPubBtn.disabled = true;
      saveNotionPubBtn.textContent = 'Saving...';
      try {
        const res = await apiCall(`/api/meals/${state.mealId}/export/notion/public-url`, 'POST', { public_url: validation.url });
        if (res?.ok) {
          if (state.notionExport) state.notionExport.public_url = res.public_url;
          if (state.snapshot) state.snapshot.notion_public_url = res.public_url;
          showAlert('View-only Notion report link shared with diners!', 'success');
          updateMealUI();
        }
      } catch (err) {
        showAlert(`Failed to save Notion public link: ${err.message || 'invalid_input'}`, 'error');
      } finally {
        saveNotionPubBtn.disabled = false;
        saveNotionPubBtn.textContent = 'Save Custom Link';
      }
    });
  }

  // 4. Remove Notion Public Web Link
  const clearNotionPubBtn = document.getElementById('clear-notion-public-url-btn');
  if (clearNotionPubBtn) {
    clearNotionPubBtn.addEventListener('click', async () => {
      if (!confirm('Stop sharing report with diners? Diners will no longer see the link to this Notion page.')) {
        return;
      }
      clearNotionPubBtn.disabled = true;
      clearNotionPubBtn.textContent = 'Removing...';
      try {
        const res = await apiCall(`/api/meals/${state.mealId}/export/notion/public-url`, 'POST', { public_url: '' });
        if (res?.ok) {
          if (state.notionExport) state.notionExport.public_url = null;
          if (state.snapshot) state.snapshot.notion_public_url = null;
          showAlert('Public Notion report link removed.', 'success');
          updateMealUI();
        }
      } catch (err) {
        showAlert('Failed to remove Notion public link.', 'error');
      } finally {
        clearNotionPubBtn.disabled = false;
        clearNotionPubBtn.textContent = 'Stop Sharing with Diners';
      }
    });
  }

  // 5. Navigation helper buttons
  const jumpToNotionExpBtn = document.getElementById('jump-to-notion-export-btn');
  if (jumpToNotionExpBtn) {
    jumpToNotionExpBtn.addEventListener('click', () => {
      navigateToWorkflowSection('notion-export-card');
    });
  }

  const jumpToNotionCardBtn = document.getElementById('jump-to-notion-card-btn');
  if (jumpToNotionCardBtn) {
    jumpToNotionCardBtn.addEventListener('click', () => {
      navigateToWorkflowSection('notion-export-card');
    });
  }

  const quickNavSharingBtn = document.getElementById('quick-nav-sharing-btn');
  if (quickNavSharingBtn) {
    quickNavSharingBtn.addEventListener('click', () => {
      navigateToWorkflowSection('sharing-access-section', 'sharing-access-heading');
    });
  }

  // Toggle Receipt Photo Sharing (Organizer only)
  const sharePhotoCheckbox = document.getElementById('share-receipt-photo-checkbox');
  if (sharePhotoCheckbox) {
    sharePhotoCheckbox.addEventListener('change', async (e) => {
      const shareVal = e.target.checked;
      sharePhotoCheckbox.disabled = true;
      try {
        const res = await apiCall(`/api/meals/${state.mealId}/receipt/photo/share`, 'POST', { share: shareVal });
        if (res?.ok) {
          if (state.snapshot) state.snapshot.receipt_photo_shared = shareVal;
          showAlert(shareVal ? 'Receipt photo sharing enabled for diners.' : 'Receipt photo sharing disabled.', 'success');
        }
      } catch (err) {
        sharePhotoCheckbox.checked = !shareVal;
        showAlert('Failed to update receipt photo sharing setting.', 'error');
      } finally {
        sharePhotoCheckbox.disabled = false;
      }
    });
  }

  // --- Restaurant Funding & Contributions Event Handlers ---
  const fillRemainingBtn = document.getElementById('fill-remaining-btn');
  if (fillRemainingBtn && snap.funding) {
    fillRemainingBtn.addEventListener('click', () => {
      const amountInput = document.getElementById('payer-amount-input');
      if (amountInput) {
        amountInput.value = (snap.funding.unfunded_sen / 100).toFixed(2);
      }
    });
  }

  const recordContributionBtn = document.getElementById('record-contribution-btn');
  if (recordContributionBtn && snap.funding) {
    recordContributionBtn.addEventListener('click', async () => {
      const partSelect = document.getElementById('payer-participant-select');
      const amountInput = document.getElementById('payer-amount-input');
      const methodSelect = document.getElementById('payer-method-select');
      if (!partSelect || !amountInput) return;

      const partId = partSelect.value;
      if (!partId) {
        showAlert('Please select a participant who paid.', 'error');
        return;
      }

      let amountSen;
      try {
        amountSen = parseSen(amountInput.value, false);
      } catch (err) {
        showAlert(err.message || 'Invalid payment amount.', 'error');
        return;
      }

      if (amountSen <= 0) {
        showAlert('Payment amount must be greater than zero.', 'error');
        return;
      }

      if (amountSen > snap.funding.unfunded_sen) {
        showAlert(`Contribution (${formatSen(amountSen)}) exceeds remaining unfunded bill (${formatSen(snap.funding.unfunded_sen)}).`, 'error');
        return;
      }

      recordContributionBtn.disabled = true;
      recordContributionBtn.textContent = 'Recording...';
      try {
        const cmdId = `pay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'RecordContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          participant_id: partId,
          amount_sen: amountSen,
          payment_method: methodSelect ? methodSelect.value : null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Recorded ${formatSen(amountSen)} contribution ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not record payment'}`, 'error');
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Payment recording failed'}`, 'error');
      } finally {
        recordContributionBtn.disabled = false;
        recordContributionBtn.textContent = 'Record Payment to Restaurant';
      }
    });
  }

  document.querySelectorAll('.reverse-contrib-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const contribId = e.currentTarget.dataset.id;
      const payerName = e.currentTarget.dataset.name;
      const amountStr = e.currentTarget.dataset.amount;
      if (!contribId) return;

      const reason = window.prompt(`Reverse contribution of ${amountStr} by ${payerName}?\nEnter reason (optional):`);
      if (reason === null) return; // User cancelled

      try {
        const cmdId = `rev-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ReverseContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          contribution_id: contribId,
          reason: reason.trim() || null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Contribution reversed ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not reverse contribution'}`, 'error');
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Reversal failed'}`, 'error');
      }
    });
  });

  // Toggle Diner Restaurant Contribution Panel
  const toggleDinerContribBtn = document.getElementById('toggle-diner-contrib-panel-btn');
  const dinerContribPanel = document.getElementById('diner-contrib-panel');
  if (toggleDinerContribBtn && dinerContribPanel) {
    toggleDinerContribBtn.addEventListener('click', () => {
      const isHidden = dinerContribPanel.style.display === 'none';
      dinerContribPanel.style.display = isHidden ? 'block' : 'none';
    });
  }

  const cancelDinerContribPanelBtn = document.getElementById('cancel-diner-contrib-panel-btn');
  if (cancelDinerContribPanelBtn && dinerContribPanel) {
    cancelDinerContribPanelBtn.addEventListener('click', () => {
      dinerContribPanel.style.display = 'none';
    });
  }

  const dinerFillRemainingBtn = document.getElementById('diner-fill-remaining-btn');
  if (dinerFillRemainingBtn && snap.funding) {
    dinerFillRemainingBtn.addEventListener('click', () => {
      const input = document.getElementById('diner-payer-amount-input');
      if (input) input.value = (snap.funding.unfunded_sen / 100).toFixed(2);
    });
  }

  const submitDinerContribBtn = document.getElementById('submit-diner-contrib-btn');
  if (submitDinerContribBtn && snap.funding) {
    submitDinerContribBtn.addEventListener('click', async () => {
      const amountInput = document.getElementById('diner-payer-amount-input');
      const methodSelect = document.getElementById('diner-payer-method-select');
      const currentUserId = state.currentUserId || snap.current_participant_id;
      if (!amountInput || !currentUserId) return;

      let amountSen;
      try {
        amountSen = parseSen(amountInput.value, false);
      } catch (err) {
        showAlert(err.message || 'Invalid payment amount.', 'error');
        return;
      }
      if (amountSen <= 0) {
        showAlert('Payment amount must be greater than zero.', 'error');
        return;
      }
      if (amountSen > snap.funding.unfunded_sen) {
        showAlert(`Reported amount (${formatSen(amountSen)}) exceeds remaining unfunded bill (${formatSen(snap.funding.unfunded_sen)}).`, 'error');
        return;
      }

      submitDinerContribBtn.disabled = true;
      submitDinerContribBtn.textContent = 'Submitting...';
      try {
        const cmdId = `rpay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ReportContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          participant_id: currentUserId,
          amount_sen: amountSen,
          payment_method: methodSelect ? methodSelect.value : null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Payment report submitted for organizer confirmation ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not report payment'}`, 'error');
          submitDinerContribBtn.disabled = false;
          submitDinerContribBtn.textContent = 'Submit Payment for Confirmation';
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Payment report failed'}`, 'error');
        submitDinerContribBtn.disabled = false;
        submitDinerContribBtn.textContent = 'Submit Payment for Confirmation';
      }
    });
  }

  // Confirm Pending Contribution (Organizer)
  document.querySelectorAll('.confirm-pending-contrib-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      const name = btn.getAttribute('data-name');
      const amount = btn.getAttribute('data-amount');
      if (!reportId) return;
      if (!confirm(`Confirm that ${name} paid ${amount} to the restaurant? This will record the payment on the official ledger.`)) return;

      btn.disabled = true;
      try {
        const cmdId = `cpay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ConfirmContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Payment confirmed and recorded on ledger ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not confirm payment'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Confirmation failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Decline Pending Contribution (Organizer)
  document.querySelectorAll('.decline-pending-contrib-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      const name = btn.getAttribute('data-name');
      if (!reportId) return;
      const reason = window.prompt(`Decline reported payment by ${name}?\nEnter reason (optional):`);
      if (reason === null) return;

      btn.disabled = true;
      try {
        const cmdId = `dpay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'DeclineContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
          reason: reason.trim() || null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Reported payment declined ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not decline payment'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Decline failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Cancel Pending Contribution (Reporter Diner)
  document.querySelectorAll('.cancel-pending-contrib-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      if (!reportId) return;
      if (!confirm('Cancel your reported payment?')) return;

      btn.disabled = true;
      try {
        const cmdId = `xpay-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'CancelContribution',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Payment report cancelled ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not cancel report'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Cancellation failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // --- Peer Settlement Event Handlers ---
  document.querySelectorAll('.prefill-transfer-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const sender = btn.getAttribute('data-sender');
      const receiver = btn.getAttribute('data-receiver');
      const amount = btn.getAttribute('data-amount');

      const sSelect = document.getElementById('transfer-sender-select');
      const rSelect = document.getElementById('transfer-receiver-select');
      const aInput = document.getElementById('transfer-amount-input');
      const banner = document.getElementById('prefill-transfer-banner');

      if (sSelect && sender) sSelect.value = sender;
      if (rSelect && receiver) rSelect.value = receiver;
      if (aInput && amount) aInput.value = amount;

      if (banner) {
        banner.textContent = 'ℹ️ Details pre-filled. Review and confirm the reimbursement below.';
        banner.style.display = 'block';
      }

      navigateToWorkflowSection('record-transfer-form', 'record-transfer-heading');
    });
  });

  const recordTransferBtn = document.getElementById('record-transfer-btn');
  if (recordTransferBtn && snap.settlement) {
    recordTransferBtn.addEventListener('click', async () => {
      const sSelect = document.getElementById('transfer-sender-select');
      const rSelect = document.getElementById('transfer-receiver-select');
      const aInput = document.getElementById('transfer-amount-input');
      const nInput = document.getElementById('transfer-note-input');
      const banner = document.getElementById('prefill-transfer-banner');
      if (!sSelect || !rSelect || !aInput) return;

      const senderId = sSelect.value;
      const receiverId = rSelect.value;
      if (!senderId || !receiverId) {
        showAlert('Please select both sender and receiver.', 'error');
        return;
      }
      if (senderId === receiverId) {
        showAlert('Sender and receiver cannot be the same diner.', 'error');
        return;
      }

      let amountSen;
      try {
        amountSen = parseSen(aInput.value, false);
      } catch (err) {
        showAlert(err.message || 'Invalid transfer amount.', 'error');
        return;
      }

      if (amountSen <= 0) {
        showAlert('Transfer amount must be greater than zero.', 'error');
        return;
      }

      recordTransferBtn.disabled = true;
      recordTransferBtn.textContent = 'Recording...';
      try {
        const cmdId = `xfer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'RecordTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          sender_id: senderId,
          receiver_id: receiverId,
          amount_sen: amountSen,
          note: nInput && nInput.value.trim() ? nInput.value.trim() : null,
        };
        if (banner) banner.style.display = 'none';
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Recorded ${formatSen(amountSen)} reimbursement ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not record reimbursement'}`, 'error');
          recordTransferBtn.disabled = false;
          recordTransferBtn.textContent = 'Record Confirmed Reimbursement';
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Reimbursement failed'}`, 'error');
        recordTransferBtn.disabled = false;
        recordTransferBtn.textContent = 'Record Confirmed Reimbursement';
      }
    });
  }

  document.querySelectorAll('.reverse-transfer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const transferId = btn.getAttribute('data-id');
      const desc = btn.getAttribute('data-desc');
      const amountStr = btn.getAttribute('data-amount');
      if (!transferId) return;

      const reason = window.prompt(`Reverse reimbursement of ${amountStr} (${desc})?\nEnter reason (optional):`);
      if (reason === null) return; // User cancelled

      try {
        const cmdId = `revx-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ReverseTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          transfer_id: transferId,
          reason: reason.trim() || null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Reimbursement reversed ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not reverse reimbursement'}`, 'error');
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Reversal failed'}`, 'error');
      }
    });
  });

  // Diner "I've Sent Payment" Action Buttons
  document.querySelectorAll('.diner-report-sent-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const receiver = btn.getAttribute('data-receiver');
      const amount = btn.getAttribute('data-amount');

      const rSelect = document.getElementById('diner-xfer-receiver-select');
      const aInput = document.getElementById('diner-xfer-amount-input');
      const form = document.getElementById('diner-report-transfer-form');

      if (rSelect && receiver) rSelect.value = receiver;
      if (aInput && amount) aInput.value = amount;
      if (form) {
        form.style.display = 'block';
        form.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
    });
  });

  // Toggle Custom Diner Reimbursement Form
  const toggleCustomXferBtn = document.getElementById('toggle-custom-diner-transfer-btn');
  const dinerXferForm = document.getElementById('diner-report-transfer-form');
  if (toggleCustomXferBtn && dinerXferForm) {
    toggleCustomXferBtn.addEventListener('click', () => {
      const isHidden = dinerXferForm.style.display === 'none';
      dinerXferForm.style.display = isHidden ? 'block' : 'none';
    });
  }

  const cancelDinerXferFormBtn = document.getElementById('cancel-diner-transfer-form-btn');
  if (cancelDinerXferFormBtn && dinerXferForm) {
    cancelDinerXferFormBtn.addEventListener('click', () => {
      dinerXferForm.style.display = 'none';
    });
  }

  // Submit Diner Sent Reimbursement Report
  const submitDinerTransferBtn = document.getElementById('submit-diner-transfer-btn');
  if (submitDinerTransferBtn && snap.settlement) {
    submitDinerTransferBtn.addEventListener('click', async () => {
      const rSelect = document.getElementById('diner-xfer-receiver-select');
      const aInput = document.getElementById('diner-xfer-amount-input');
      const nInput = document.getElementById('diner-xfer-note-input');
      const currentUserId = state.currentUserId || snap.current_participant_id;
      if (!rSelect || !aInput || !currentUserId) return;

      const receiverId = rSelect.value;
      if (!receiverId) {
        showAlert('Please select a recipient.', 'error');
        return;
      }
      if (receiverId === currentUserId) {
        showAlert('You cannot send reimbursement to yourself.', 'error');
        return;
      }

      let amountSen;
      try {
        amountSen = parseSen(aInput.value, false);
      } catch (err) {
        showAlert(err.message || 'Invalid transfer amount.', 'error');
        return;
      }
      if (amountSen <= 0) {
        showAlert('Transfer amount must be greater than zero.', 'error');
        return;
      }

      submitDinerTransferBtn.disabled = true;
      submitDinerTransferBtn.textContent = 'Submitting...';
      try {
        const cmdId = `rxfer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ReportTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          sender_id: currentUserId,
          receiver_id: receiverId,
          amount_sen: amountSen,
          note: nInput && nInput.value.trim() ? nInput.value.trim() : null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Reimbursement reported! Recipient can now confirm receipt ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not report reimbursement'}`, 'error');
          submitDinerTransferBtn.disabled = false;
          submitDinerTransferBtn.textContent = 'Submit Sent Payment Report';
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Reimbursement report failed'}`, 'error');
        submitDinerTransferBtn.disabled = false;
        submitDinerTransferBtn.textContent = 'Submit Sent Payment Report';
      }
    });
  }

  // Confirm Pending Transfer (Recipient Creditor)
  document.querySelectorAll('.confirm-pending-transfer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      const sender = btn.getAttribute('data-sender');
      const amount = btn.getAttribute('data-amount');
      if (!reportId) return;
      if (!confirm(`Confirm you received ${amount} from ${sender}? This will record the reimbursement on the official ledger.`)) return;

      btn.disabled = true;
      try {
        const cmdId = `cxfer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'ConfirmTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert(`Reimbursement confirmed and recorded on ledger ✓`, 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not confirm reimbursement'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Confirmation failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Decline Pending Transfer (Recipient or Organizer)
  document.querySelectorAll('.decline-pending-transfer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      const sender = btn.getAttribute('data-sender');
      if (!reportId) return;
      const reason = window.prompt(`Mark reimbursement from ${sender} as Not Received?\nEnter reason (optional):`);
      if (reason === null) return;

      btn.disabled = true;
      try {
        const cmdId = `dxfer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'DeclineTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
          reason: reason.trim() || null,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Reimbursement marked not received ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not decline reimbursement'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Decline failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });

  // Cancel Pending Transfer (Sender)
  document.querySelectorAll('.cancel-pending-transfer-btn').forEach(btn => {
    btn.addEventListener('click', async () => {
      const reportId = btn.getAttribute('data-id');
      if (!reportId) return;
      if (!confirm('Cancel this reported reimbursement?')) return;

      btn.disabled = true;
      try {
        const cmdId = `xxfer-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const payload = {
          kind: 'CancelTransfer',
          command_id: cmdId,
          expected_revision: snap.revision,
          report_id: reportId,
        };
        const res = await apiCall(`/api/meals/${mealId}/apply`, 'POST', payload);
        if (res && res.ok) {
          showAlert('Reimbursement report cancelled ✓', 'success');
          await fetchSnapshot(true);
        } else {
          showAlert(`Failed: ${res?.error || 'Could not cancel report'}`, 'error');
          btn.disabled = false;
        }
      } catch (err) {
        showAlert(`Error: ${err.message || 'Cancellation failed'}`, 'error');
        btn.disabled = false;
      }
    });
  });
}

// --- Error & Conflict Handling ---
function handleApiError(err, itemId = null) {
  state.mutationActive = false;
  if (err.status === 409 || err.code === 'item_revision_conflict' || err.code === 'financial_revision_conflict' || err.code === 'revision_conflict') {
    showAlert('⚠️ Stale Claim Conflict: Another diner updated quantities. Refreshing latest data...', 'conflict');
    if (itemId) {
      const card = document.getElementById(`item-card-${itemId}`);
      if (card) card.classList.add('contested');
    }
    fetchSnapshot(true);
  } else if (err.status === 401) {
    showAlert('Session expired or unauthorized. Please re-open from invitation.', 'error');
  } else {
    showAlert(`Action rejected: ${err.code || err.message}`, 'error');
  }
}
