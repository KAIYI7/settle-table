/**
 * Unit tests for the experimental checkout demo card's status-read schedule.
 *
 * Runs the real checkout-demo section and visibilitychange handler of settletable/static/app.js
 * in a Node vm context with a fake clock, a fake page visibility and a stubbed apiCall. No server,
 * browser, bridge, phone or wallet is involved. Run: node tools/test_checkout_demo_poll_schedule.mjs
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SOURCE = readFileSync(path.join(REPO_ROOT, 'settletable/static/app.js'), 'utf8');

function slice(startMarker, endMarker) {
  const start = SOURCE.indexOf(startMarker);
  const end = SOURCE.indexOf(endMarker, start);
  assert.ok(start >= 0 && end > start, `app.js markers not found: ${startMarker}`);
  return SOURCE.slice(start, end);
}

const SECTION = slice('// --- Experimental checkout demo', 'function renderCheckoutDemoCard(');
const VISIBILITY = slice("document.addEventListener('visibilitychange'", '\nfunction startPolling(');

const T0 = Date.UTC(2026, 10, 17, 4, 0, 5);  // When the schedule starts in every test.
const iso = ms => new Date(ms).toISOString();
const flush = () => new Promise(resolve => setImmediate(resolve));

// A page with the card's code, a fake clock and a bridge-status responder.
function makePage({ observed = true, respond }) {
  let now = T0;
  let nextId = 1;
  const timers = new Map();
  const reads = [];
  let inFlight = 0;
  let maxInFlight = 0;
  let hold = null;
  const listeners = {};
  const FakeDate = class extends Date {
    constructor(...args) { if (args.length) super(...args); else super(now); }
    static now() { return now; }
  };
  const state = {
    mealId: 'meal-1', checkoutDemo: null, checkoutDemoBusy: false, checkoutDemoTimers: [],
    checkoutDemoSeq: 0, checkoutDemoEpoch: 0, checkoutDemoRereadPending: null,
    checkoutDemoTail: false, checkoutDemoTailTimer: null,
    pollTimer: 1, paymentSimulations: new Map(),
  };
  const document = {
    visibilityState: 'visible',
    addEventListener(type, fn) { listeners[type] = fn; },
  };
  const sandbox = {
    state, document, Date: FakeDate, console,
    setTimeout(fn, ms) { const id = nextId++; timers.set(id, { at: now + ms, fn, id }); return id; },
    clearTimeout(id) { timers.delete(id); },
    updateMealUI() {}, showAlert() {},
    stopPolling() { state.pollTimer = null; }, startPolling() { state.pollTimer = 1; },
    clearSimulationTimers() {}, scheduleSimulationReads() {},
    async apiCall(url, method, body) {
      reads.push({ at: (now - T0) / 1000, url, method, body });
      inFlight++;
      maxInFlight = Math.max(maxInFlight, inFlight);
      try {
        if (hold) await hold;
        const demo = respond((now - T0) / 1000, reads.length);
        if (demo instanceof Error) throw demo;
        return { ok: true, checkout_demo: observed ? { ...demo, synthetic: false, observed: true, evidenceMode: 'OBSERVED_NOTIFICATION' }
          : { ...demo, synthetic: true } };
      } finally {
        inFlight--;
      }
    },
  };
  vm.createContext(sandbox);
  const api = vm.runInContext(`${SECTION}\n${VISIBILITY}\n;({scheduleCheckoutDemoReads, requestCheckoutDemo,
    checkoutDemoInstant, checkoutDemoObservedNextDelay, clearCheckoutDemoTimers, resetCheckoutDemoView})`, sandbox);
  return {
    api, state,
    reads: () => reads.map(r => r.at),
    allReads: reads,
    maxInFlight: () => maxInFlight,
    pendingTimers: () => timers.size,
    async advanceTo(seconds) {
      const until = T0 + seconds * 1000;
      for (;;) {
        const due = [...timers.values()].filter(t => t.at <= until).sort((a, b) => a.at - b.at || a.id - b.id)[0];
        if (!due) break;
        timers.delete(due.id);
        now = due.at;
        due.fn();
        for (let i = 0; i < 5; i++) await flush();
      }
      now = until;
      for (let i = 0; i < 5; i++) await flush();
    },
    setVisibility(value) { document.visibilityState = value; listeners.visibilitychange(); },
    holdReads() { let release; hold = new Promise(r => { release = r; }); return () => { hold = null; release(); }; },
    // Starts the card as a request answer would: the first response, then the fixed schedule.
    async start() {
      await api.requestCheckoutDemo(null, true);
      for (let i = 0; i < 5; i++) await flush();
    },
  };
}

const intent = (patch = {}) => ({
  attempt: 1, revision: 1, state: 'AWAITING_EVIDENCE', lastKnownState: 'AWAITING_EVIDENCE',
  terminal: false, latched: false, expiresAt: iso(T0 + 600_123), reviewExpiresAt: null, ...patch,
});
const demo = patch => ({ enabled: true, intent: intent(patch), eligible: [], lastCheck: null, retryAfter: null });

// Read times relative to the start: the fixed reads, then every `step` s while `while(t)` held at the prior read.
function expected(fixedEnd, phases) {
  const out = [2, 5, 10, 30, 60, 90, 120].filter(s => s <= fixedEnd);
  let t = 120;
  for (const [step, until] of phases) {
    while (t < until) { t += step; out.push(t); }
  }
  return out;
}

test('timestamps from the status response parse exactly; anything else is NaN', () => {
  const { api } = makePage({ respond: () => demo() });
  assert.equal(api.checkoutDemoInstant('2026-11-17T04:10:00.123456789Z'), Date.UTC(2026, 10, 17, 4, 10, 0, 123));
  assert.equal(api.checkoutDemoInstant('2026-11-17T12:10:00+08:00'), Date.UTC(2026, 10, 17, 4, 10, 0));
  assert.equal(api.checkoutDemoInstant('2026-11-17T04:10:00.5-01:30'), Date.UTC(2026, 10, 17, 5, 40, 0, 500));
  assert.equal(api.checkoutDemoInstant('2026-11-17T04:10Z'), Date.UTC(2026, 10, 17, 4, 10, 0));
  for (const bad of [null, undefined, '', 'soon', 1795000000, '2026-11-17 04:10:00Z', '2026-11-17T04:10:00',
    '2026-11-17T041000.123Z', '2026-11-17T04:10:00.1234567890Z']) {
    assert.ok(Number.isNaN(api.checkoutDemoInstant(bad)), `accepted ${bad}`);
  }
});

test('next-delay rule: 15 s in the window, 30 s until the review deadline, otherwise stop', () => {
  const { api } = makePage({ respond: () => demo() });
  const at = s => T0 + s * 1000;
  const obs = patch => ({ ...demo(patch), observed: true });
  assert.equal(api.checkoutDemoObservedNextDelay(obs(), at(130)), 15000);
  assert.equal(api.checkoutDemoObservedNextDelay(obs(), at(600.2)), null, 'window over, no review deadline');
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ reviewExpiresAt: iso(at(1800)) }), at(700)), 30000);
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ reviewExpiresAt: iso(at(1800)) }), at(1800)), null);
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ terminal: true }), at(130)), null);
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ latched: true }), at(130)), null);
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ expiresAt: null }), at(130)), null, 'no window end: no invented deadline');
  assert.equal(api.checkoutDemoObservedNextDelay(obs({ expiresAt: 'later' }), at(130)), null);
  assert.equal(api.checkoutDemoObservedNextDelay(demo(), at(130)), null, 'synthetic result');
  assert.equal(api.checkoutDemoObservedNextDelay({ ...demo(), observed: true, intent: null }, at(130)), null);
});

test('observed: fixed reads, then every 15 s through the payment window, then stop without a review deadline', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(3600);
  // The read at 600 s is still inside the window (600.123 s); the one at 615 s is the first after it.
  assert.deepEqual(page.reads(), [0, ...expected(Infinity, [[15, 600.123]])]);
  assert.equal(page.reads().at(-1), 615);
  assert.equal(page.pendingTimers(), 0);
  assert.equal(page.state.checkoutDemoTail, false);
  assert.ok(page.allReads.every(r => r.method === 'GET' && r.url === '/api/meals/meal-1/checkout-demo' && r.body === null));
  assert.equal(page.maxInFlight(), 1);
});

test('observed: a late notification shows on the next read, then 30 s reads until the review deadline', async () => {
  const review = iso(T0 + 1800_000);
  const page = makePage({ respond: t => t < 300 ? demo() : demo({ state: 'EVIDENCE_DETECTED', revision: 2, reviewExpiresAt: review }) });
  await page.start();
  await page.advanceTo(299);
  assert.equal(page.state.checkoutDemo.intent.state, 'AWAITING_EVIDENCE');
  await page.advanceTo(300);
  assert.equal(page.state.checkoutDemo.intent.state, 'EVIDENCE_DETECTED', 'read at 300 s (15 s cadence) shows it');
  await page.advanceTo(7200);
  assert.deepEqual(page.reads(), [0, ...expected(Infinity, [[15, 600.123], [30, 1800]])]);
  assert.equal(page.reads().at(-1), 1815, 'one read after the review deadline, then none');
  assert.equal(page.pendingTimers(), 0);
});

test('observed: a terminal status stops all reads', async () => {
  const page = makePage({ respond: t => t < 400 ? demo()
    : demo({ state: 'MANUALLY_CONFIRMED', lastKnownState: 'MANUALLY_CONFIRMED', terminal: true, revision: 3 }) });
  await page.start();
  await page.advanceTo(7200);
  assert.equal(page.reads().at(-1), 405);
  assert.deepEqual(page.reads(), [0, ...expected(Infinity, [[15, 405]])]);
  assert.equal(page.pendingTimers(), 0);
  assert.equal(page.state.checkoutDemoTail, false);
});

test('observed: a latched status stops all reads', async () => {
  const page = makePage({ respond: t => t < 200 ? demo() : demo({ state: 'UNEXPECTED_STATUS', latched: true, revision: 2 }) });
  await page.start();
  await page.advanceTo(7200);
  assert.equal(page.reads().at(-1), 210);
  assert.equal(page.pendingTimers(), 0);
});

test('observed: no read while hidden; visible again restarts the schedule within the deadlines', async () => {
  const review = iso(T0 + 1000_000);
  const page = makePage({ respond: () => demo({ reviewExpiresAt: review }) });
  await page.start();
  await page.advanceTo(200);
  assert.ok(page.state.checkoutDemoTailTimer !== null);
  page.setVisibility('hidden');
  assert.equal(page.pendingTimers(), 0, 'hidden clears every checkout-demo timer');
  assert.equal(page.state.checkoutDemoTail, false);
  const before = page.reads().length;
  await page.advanceTo(500);
  assert.equal(page.reads().length, before, 'no read while hidden');
  page.setVisibility('visible');
  await page.advanceTo(7200);
  const resumed = page.reads().slice(before).map(t => t - 500);
  // Fixed reads again, 15 s while the window is open (ends at 100.123 s after resuming), 30 s until 500 s.
  assert.deepEqual(resumed, expected(Infinity, [[15, 100.123], [30, 500]]));
  assert.equal(page.reads().at(-1), 1010);
  assert.equal(page.pendingTimers(), 0);
});

test('observed: a hidden page at the deadline stops for good until it is visible again', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(130);
  page.setVisibility('hidden');
  await page.advanceTo(5000);
  assert.equal(page.reads().at(-1), 120);
  assert.equal(page.pendingTimers(), 0);
});

test('observed: a tail tick during a read in flight sends no second read; the schedule continues after it', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(130);
  const release = page.holdReads();
  page.api.requestCheckoutDemo(null, false);  // e.g. a read after a snapshot change, at 130 s
  await page.advanceTo(140);                  // the 135 s tick finds the read busy
  assert.equal(page.reads().filter(t => t > 120).length, 1);
  release();
  await page.advanceTo(140);                  // the held read settles at 140 s
  await page.advanceTo(160);
  assert.deepEqual(page.reads().filter(t => t > 120), [130, 155]);
  assert.equal(page.maxInFlight(), 1);
});

test('observed: failed reads keep the stored deadlines and still stop after them', async () => {
  const page = makePage({ respond: t => t < 150 ? demo() : new Error('network') });
  await page.start();
  await page.advanceTo(7200);
  assert.equal(page.reads().at(-1), 615);
  assert.equal(page.state.checkoutDemo.lastCheck, 'UNAVAILABLE');
  assert.equal(page.pendingTimers(), 0);
});

test('observed: without a window end in the response the schedule stops at 120 s as before', async () => {
  const page = makePage({ respond: () => demo({ state: 'REQUEST_UNKNOWN', expiresAt: null }) });
  await page.start();
  await page.advanceTo(7200);
  assert.deepEqual(page.reads(), [0, 2, 5, 10, 30, 60, 90, 120]);
  assert.equal(page.pendingTimers(), 0);
});

test('synthetic (flag absent): reads stop at 120 s even with an open window and review deadline', async () => {
  const page = makePage({ observed: false, respond: () => demo({ reviewExpiresAt: iso(T0 + 1800_000) }) });
  await page.start();
  await page.advanceTo(7200);
  assert.deepEqual(page.reads(), [0, 2, 5, 10, 30, 60, 90, 120]);
  assert.equal(page.state.checkoutDemoTail, false);
  assert.equal(page.state.checkoutDemoTailTimer, null);
  page.setVisibility('hidden');
  page.setVisibility('visible');
  await page.advanceTo(9000);
  assert.deepEqual(page.reads().slice(8).map(t => t - 7200), [2, 5, 10, 30, 60, 90, 120]);
});

test('observed: "Refresh demo status" during the extended reads restarts the schedule from 2 s', async () => {
  const page = makePage({ respond: () => demo({ reviewExpiresAt: iso(T0 + 1000_000) }) });
  await page.start();
  await page.advanceTo(200);
  await page.api.requestCheckoutDemo(null);  // the refresh button: schedule defaults to true
  assert.equal(page.state.checkoutDemoTail, false);
  assert.equal(page.state.checkoutDemoTailTimer, null);
  const from = page.reads().length;
  await page.advanceTo(359);
  assert.deepEqual(page.reads().slice(from).map(t => t - 200), [2, 5, 10, 30, 60, 90, 120, 135, 150]);
  assert.equal(page.maxInFlight(), 1);
});

test('observed: a POST during the extended reads restarts the schedule from 2 s', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(200);
  await page.api.requestCheckoutDemo({ senderId: 'p-1', amountSen: 1 });
  assert.equal(page.allReads.at(-1).method, 'POST');
  assert.equal(page.state.checkoutDemoTail, false);
  const from = page.reads().length;
  await page.advanceTo(325);
  assert.deepEqual(page.reads().slice(from).map(t => t - 200), [2, 5, 10, 30, 60, 90, 120]);
});

test('observed: a 401 or 403 during the extended reads clears every timer; no read follows', async () => {
  for (const status of [401, 403]) {
    const page = makePage({ respond: t => t < 150 ? demo() : Object.assign(new Error('auth'), { status }) });
    await page.start();
    await page.advanceTo(7200);
    assert.equal(page.reads().at(-1), 150);
    assert.equal(page.pendingTimers(), 0);
    assert.equal(page.state.checkoutDemo, null);
    assert.equal(page.state.checkoutDemoTail, false);
  }
});

test('observed: leaving the meal with a tail read pending stops it, and a stale read cannot rearm it', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(130);
  const release = page.holdReads();
  page.api.requestCheckoutDemo(null, false);
  await page.advanceTo(131);
  page.api.resetCheckoutDemoView();           // as when switching meals
  release();
  await page.advanceTo(7200);
  assert.deepEqual(page.reads().filter(t => t > 120), [130]);
  assert.equal(page.pendingTimers(), 0);
});

test('observed: the 120 s tick during a read in flight still hands over to the extended reads', async () => {
  const page = makePage({ respond: () => demo() });
  await page.start();
  await page.advanceTo(119);
  const release = page.holdReads();
  page.api.requestCheckoutDemo(null, false);  // in flight across the 120 s tick
  await page.advanceTo(121);
  assert.equal(page.state.checkoutDemoTail, true);
  release();
  await page.advanceTo(121);
  await page.advanceTo(160);
  assert.deepEqual(page.reads().filter(t => t > 90), [119, 136, 151]);
  assert.equal(page.maxInFlight(), 1);
});
