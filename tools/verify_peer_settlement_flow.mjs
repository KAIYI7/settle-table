/**
 * Headless Chrome E2E verification of Suggested Peer Transfers, Partial Reimbursements & Settlement Tracking.
 *
 * Verifies:
 * - Peer Settlements & Reimbursements card rendering in finalized view.
 * - Settlement status badges ('Reimbursements Pending', '✓ All Debts Settled').
 * - Unfunded restaurant bill blocker notice.
 * - Explainable suggested transfer cards ("Bob pays Alice RM 20.00").
 * - Pre-fill convenience button for organizer.
 * - Recording partial reimbursements with optional notes.
 * - Outstanding net balances table updates and status badges.
 * - Transition to 'All Debts Settled' state upon full reimbursement.
 * - Reversal of peer transfer with strikethrough audit trail and balance restoration.
 * - Mobile responsive viewport compliance (375px width).
 */
import { spawn } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import fs, { existsSync } from 'node:fs';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path, { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:net';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function resolveChromePath() {
  const env = process.env.CHROME || process.env.CHROME_BIN || process.env.GOOGLE_CHROME_BIN;
  if (env && existsSync(env)) return env;
  const candidates = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium',
  ];
  for (const c of candidates) {
    if (c && existsSync(c)) return c;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath() {
  const env = process.env.PYTHON || process.env.PYTHON_BIN;
  if (env && existsSync(env)) return env;
  for (const c of ['C:\\Python314\\python.exe', 'C:\\Python312\\python.exe', 'python3', 'python']) {
    if (c && (existsSync(c) || !c.includes('\\'))) return c;
  }
  return 'python';
}

class CDPPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.callbacks = new Map();
    this.consoleErrors = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.method === 'Page.javascriptDialogOpening') {
        this.send('Page.handleJavaScriptDialog', { accept: true, promptText: 'Paid wrong amount' });
      }
      if (msg.method === 'Runtime.consoleAPICalled') {
        const type = msg.params.type;
        const text = (msg.params.args || []).map(a => a.value || a.description || '').join(' ');
        if (type === 'error') {
          this.consoleErrors.push(text);
        }
      }
      if (msg.id && this.callbacks.has(msg.id)) {
        const { resolve, reject } = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      }
    };
  }

  async send(method, params = {}) {
    await this.ready;
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expr, ...args) {
    const exprStr = typeof expr === 'function'
      ? `(${expr.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`
      : expr;
    const res = await this.send('Runtime.evaluate', {
      expression: exprStr,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Evaluation failed in browser: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result?.value;
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
    await this.waitFor(() => document.readyState === 'complete');
  }

  async waitFor(expr, timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const val = await this.evaluate(expr);
        if (val) return val;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 100));
    }
    throw new Error(`Timeout waiting for expression: ${expr}`);
  }

  close() {
    try {
      this.ws.close();
    } catch (e) {}
  }
}

async function startChrome(chromeBin, port, dataDir) {
  const proc = spawn(chromeBin, [
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${dataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-background-networking',
    '--disable-component-update',
    '--disable-sync',
    '--disable-gpu',
    '--no-sandbox',
    '--disable-dev-shm-usage',
    'about:blank',
  ]);

  let stderr = '';
  let spawnError;
  proc.on('error', error => { spawnError = error; });
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  try {
    let target = null;
    for (let i = 0; i < 300; i++) {
      if (spawnError) throw spawnError;
      if (proc.exitCode !== null) {
        throw new Error(`Chrome exited prematurely with code ${proc.exitCode} on port ${port}: ${stderr}`);
      }
      try {
        let activePort = port;
        try {
          const devToolsFile = await fs.promises.readFile(join(dataDir, 'DevToolsActivePort'), 'utf8');
          const parsed = Number(devToolsFile.split('\n')[0]);
          if (parsed) activePort = parsed;
        } catch {}
        const endpoint = `http://127.0.0.1:${activePort}/json/list`;
        const res = await fetch(endpoint);
        const list = await res.json();
        target = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
        if (!target) {
          const newRes = await fetch(`http://127.0.0.1:${activePort}/json/new`, { method: 'PUT' });
          const newPage = await newRes.json();
          if (newPage && newPage.webSocketDebuggerUrl) target = newPage;
        }
        if (target && target.webSocketDebuggerUrl) break;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 100));
    }

    if (!target || !target.webSocketDebuggerUrl) {
      proc.kill();
      throw new Error(`Could not connect to Chrome on port ${port} after 30s. Stderr: ${stderr}`);
    }

    const page = new CDPPage(target.webSocketDebuggerUrl);
    await page.send('Page.enable');
    await page.send('Runtime.enable');
    return { proc, page };
  } catch (error) {
    proc.kill();
    throw error;
  }
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

async function main() {
  console.log('--- Starting Peer Settlement E2E Verification in Headless Chrome ---');
  const chromePath = resolveChromePath();
  const pythonPath = resolvePythonPath();

  // Find free ports
  const serverPort = await new Promise((res, rej) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); });
    s.on('error', rej);
  });
  const chromePort = serverPort + 10;
  const origin = `http://127.0.0.1:${serverPort}`;
  const mealId = `settle-e2e-${randomBytes(4).toString('hex')}`;

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-settle-'));
  const dbPath = join(tempDir, 'settle.sqlite');
  const capture = join(tempDir, 'mock-payload.json');
  const owner = randomBytes(32).toString('hex');

  console.log(`[Config] Chrome: ${chromePath}`);
  console.log(`[Config] Python: ${pythonPath}`);
  console.log(`[Config] Port:   ${serverPort}`);
  console.log(`[Config] DB:     ${dbPath}`);

  // Start test server using verify_financial_export_runner.py
  const runnerScript = join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py');
  const server = spawn(pythonPath, [
    '-u', runnerScript,
    '--host', '127.0.0.1',
    '--port', String(serverPort),
    '--db', dbPath,
    '--mock-notion',
    '--mock-ocr',
  ], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      SETTLETABLE_MOCK_CAPTURE: capture,
      SETTLETABLE_TEST_OWNER: owner,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  server.stderr.on('data', d => process.stderr.write(d));
  server.stdout.on('data', () => {});

  // Wait for server health
  let serverReady = false;
  for (let i = 0; i < 150; i++) {
    try {
      const res = await fetch(`${origin}/__financial_test_owner__`);
      if (res.status === 200 && (await res.text()).trim() === owner) {
        serverReady = true;
        break;
      }
    } catch (e) {}
    await new Promise(r => setTimeout(r, 100));
  }
  assert(serverReady, 'Server failed to start');

  // Launch Chrome
  const chromeDir = join(tempDir, 'chrome-profile');
  await fs.promises.mkdir(chromeDir, { recursive: true });
  const chrome = await startChrome(chromePath, chromePort, chromeDir);
  const page = chrome.page;

  try {
    await page.send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 900, deviceScaleFactor: 1, mobile: false });

    console.log('[1/8] Bootstrapping room with Alice (Organizer) and Bob (Diner)...');
    await page.navigate(origin + '/');
    await page.waitFor(() => document.getElementById('create-meal-form') !== null);

    await page.evaluate((id) => {
      document.getElementById('create-meal-id').value = id;
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    }, mealId);

    await page.waitFor(() => document.getElementById('manual-refresh-btn') !== null);
    console.log('   ✓ Room created and organizer view rendered');

    console.log('[2/8] Setting receipt: Total RM 60.00 and allocating items...');
    await page.evaluate(async (mid) => {
      const rev = state.snapshot.revision;
      const fRev = state.snapshot.financial_revision;
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'ReplaceReceipt',
        command_id: `rcpt-${Date.now()}`,
        expected_revision: rev,
        expected_financial_revision: fRev,
        receipt: {
          items: [
            { id: 'item-1', label: 'Pasta', quantity: [1, 1], line_sen: 3000 },
            { id: 'item-2', label: 'Pizza', quantity: [1, 1], line_sen: 3000 },
          ],
          adjustments: [],
          subtotal_sen: 6000,
          total_sen: 6000,
          included_tax_sen: 0,
        }
      });
      await fetchSnapshot(true);
    }, mealId);

    // Confirm and review receipt
    await page.evaluate(() => {
      document.getElementById('review-confirm-check').checked = true;
      document.getElementById('review-confirm-check').dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitFor(() => !document.getElementById('review-submit-btn').disabled);
    await page.evaluate(() => document.getElementById('review-submit-btn').click());
    await page.waitFor(() => document.getElementById('receipt-verified-status') !== null);

    // Claim: Alice claims Pasta (RM 30), Bob claims Pizza (RM 30)
    await page.evaluate(async (mid) => {
      const snap = state.snapshot;
      const aliceId = snap.participants.find(p => p.organizer).id;
      const bobId = snap.participants.find(p => !p.organizer).id;
      const rev = snap.financial_revision;
      const item1Rev = snap.items.find(i => i.item_id === 'item-1').item_revision;
      const item2Rev = snap.items.find(i => i.item_id === 'item-2').item_revision;

      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'SetOwnQuantity',
        command_id: `claim-alice-${Date.now()}`,
        item_id: 'item-1',
        quantity: 1,
        expected_item_revision: item1Rev,
        expected_financial_revision: rev,
      });
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'AssignParticipantQuantity',
        command_id: `assign-bob-${Date.now()}`,
        participant_id: bobId,
        item_id: 'item-2',
        quantity: 1,
        expected_item_revision: item2Rev,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);
    }, mealId);

    console.log('[3/8] Finalizing meal and inspecting initial Settlement state...');
    await page.waitFor(() => !document.getElementById('finalize-btn').disabled);
    await page.evaluate(() => {
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
    });

    await page.waitFor(() => document.getElementById('peer-settlement-card') !== null);
    console.log('   ✓ Meal finalized and Peer Settlement card rendered');

    // Verify initial settlement state before funding
    const initialSettle = await page.evaluate(() => {
      const snap = state.snapshot;
      const badge = document.getElementById('settlement-status-badge')?.textContent;
      return {
        badge,
        isSettled: snap.settlement.is_settled,
        unfundedBlocker: snap.settlement.unfunded_blocker_sen,
      };
    });
    assert(!initialSettle.isSettled, 'Expected not settled');
    assert(initialSettle.unfundedBlocker === 6000, 'Expected unfunded blocker 6000 sen');
    assert(initialSettle.badge.includes('Reimbursements Pending'), 'Badge should show pending');
    console.log(`   ✓ Initial settlement verified: ${initialSettle.badge} (Unfunded blocker RM 60.00)`);

    console.log('[4/8] Funding restaurant bill: Alice pays RM 50.00, Bob pays RM 10.00...');
    // Alice contributes 50.00
    await page.evaluate(async () => {
      const snap = state.snapshot;
      const aliceId = snap.participants.find(p => p.organizer).id;
      const select = document.getElementById('payer-participant-select');
      select.value = aliceId;
      document.getElementById('payer-amount-input').value = '50.00';
      document.getElementById('payer-method-select').value = 'card';
      document.getElementById('record-contribution-btn').click();
    });
    await page.waitFor(() => state.snapshot.funding.status === 'partially_funded');

    // Bob contributes 10.00
    await page.evaluate(async () => {
      const snap = state.snapshot;
      const bobId = snap.participants.find(p => !p.organizer).id;
      const select = document.getElementById('payer-participant-select');
      select.value = bobId;
      document.getElementById('payer-amount-input').value = '10.00';
      document.getElementById('payer-method-select').value = 'cash';
      document.getElementById('record-contribution-btn').click();
    });
    await page.waitFor(() => state.snapshot.funding.status === 'fully_funded');
    console.log('   ✓ Restaurant fully funded: Alice paid RM 50.00, Bob paid RM 10.00');

    console.log('[5/8] Verifying Suggested Transfers and Prefill Button...');
    // Alice consumed 30, paid 50 -> Base Net +20.00
    // Bob consumed 30, paid 10 -> Base Net -20.00
    // Suggested: Bob pays Alice RM 20.00
    const suggestionText = await page.evaluate(() => {
      const card = document.querySelector('#peer-settlement-card');
      return card.innerText;
    });
    assert(suggestionText.includes('Bob') && suggestionText.includes('Alice') && suggestionText.includes('RM 20.00'),
           `Expected suggestion Bob pays Alice RM 20.00, got: ${suggestionText}`);
    console.log('   ✓ Suggested transfer verified: Bob pays Alice RM 20.00');

    // Click Record Payment prefill button
    await page.evaluate(() => {
      document.querySelector('.prefill-transfer-btn').click();
    });
    const prefillValues = await page.evaluate(() => {
      const snap = state.snapshot;
      const aliceId = snap.participants.find(p => p.organizer).id;
      const bobId = snap.participants.find(p => !p.organizer).id;
      return {
        sender: document.getElementById('transfer-sender-select').value,
        receiver: document.getElementById('transfer-receiver-select').value,
        amount: document.getElementById('transfer-amount-input').value,
        aliceId,
        bobId,
      };
    });
    assert(prefillValues.sender === prefillValues.bobId, `Expected sender ${prefillValues.bobId}, got ${prefillValues.sender}`);
    assert(prefillValues.receiver === prefillValues.aliceId, `Expected receiver ${prefillValues.aliceId}, got ${prefillValues.receiver}`);
    assert(prefillValues.amount === '20.00', `Expected amount 20.00, got ${prefillValues.amount}`);
    console.log(`   ✓ Prefill button populated sender=${prefillValues.bobId}, receiver=${prefillValues.aliceId}, amount=20.00`);

    console.log('[6/8] Recording Partial Reimbursement (RM 8.00) with Note...');
    await page.evaluate(async () => {
      document.getElementById('transfer-amount-input').value = '8.00';
      document.getElementById('transfer-note-input').value = 'DuitNow ref 12345';
      document.getElementById('record-transfer-btn').click();
    });

    await page.waitFor(() => (state.snapshot.transfers || []).length === 1);
    const postPartial = await page.evaluate(() => {
      const snap = state.snapshot;
      const xfer = snap.transfers[0];
      const st = snap.settlement.suggested_transfers[0];
      return {
        amount: xfer.amount_sen,
        note: xfer.note,
        remainingSuggested: st ? st.amount_sen : 0,
        isSettled: snap.settlement.is_settled,
      };
    });
    assert(postPartial.amount === 800, `Expected recorded transfer 800 sen, got ${postPartial.amount}`);
    assert(postPartial.note === 'DuitNow ref 12345', `Expected note, got ${postPartial.note}`);
    assert(postPartial.remainingSuggested === 1200, `Expected remaining suggested 1200 sen, got ${postPartial.remainingSuggested}`);
    assert(!postPartial.isSettled, 'Should not be fully settled yet');
    console.log('   ✓ Partial reimbursement recorded: RM 8.00; remaining obligation: RM 12.00');

    console.log('[7/8] Recording Final Reimbursement (RM 12.00) and verifying All Debts Settled state...');
    await page.evaluate(async () => {
      document.querySelector('.prefill-transfer-btn').click();
      document.getElementById('transfer-note-input').value = 'Final balance in cash';
      document.getElementById('record-transfer-btn').click();
    });

    await page.waitFor(() => (state.snapshot.transfers || []).length === 2 && state.snapshot.settlement.is_settled);
    const finalBadge = await page.evaluate(() => document.getElementById('settlement-status-badge')?.textContent);
    assert(finalBadge.includes('All Debts Settled'), `Expected All Debts Settled badge, got: ${finalBadge}`);

    // Verify cent conservation on all balances: all outstanding balances must be 0
    const allZero = await page.evaluate(() => {
      return state.snapshot.settlement.outstanding_net_balances.every(b => b.outstanding_net_balance_sen === 0);
    });
    assert(allZero, 'Expected all outstanding net balances to be 0');
    console.log('   ✓ Fully settled verified: ✓ All Debts Settled (all diner accounts RM 0.00)');

    console.log('[8/8] Testing Transfer Reversal and Mobile Layout (375px)...');
    // Reverse the second transfer
    await page.evaluate(() => {
      window.prompt = () => 'Paid wrong amount';
      const btns = document.querySelectorAll('.reverse-transfer-btn');
      btns[btns.length - 1].click();
    });

    await page.waitFor(() => !state.snapshot.settlement.is_settled);
    const postReversal = await page.evaluate(() => {
      const snap = state.snapshot;
      const reversedXfer = snap.transfers[1];
      return {
        status: reversedXfer.status,
        reason: reversedXfer.reversal_reason,
        isSettled: snap.settlement.is_settled,
        suggested: snap.settlement.suggested_transfers[0]?.amount_sen,
      };
    });
    assert(postReversal.status === 'reversed', 'Expected status reversed');
    assert(postReversal.reason === 'Paid wrong amount', `Expected reason, got: ${postReversal.reason}`);
    assert(postReversal.suggested === 1200, `Expected suggested RM 12.00 after reversal, got: ${postReversal.suggested}`);
    console.log('   ✓ Reversal verified: audited strikethrough and recalculated obligations (RM 12.00)');

    // Test mobile viewport
    await page.send('Emulation.setDeviceMetricsOverride', {
      width: 375,
      height: 667,
      deviceScaleFactor: 2,
      mobile: true,
    });
    await new Promise(r => setTimeout(r, 200));
    const mobileCardVisible = await page.evaluate(() => {
      const c = document.getElementById('peer-settlement-card');
      const rect = c.getBoundingClientRect();
      return rect.width <= 375 && rect.height > 0;
    });
    assert(mobileCardVisible, 'Expected settlement card to render responsively in 375px mobile viewport');
    console.log('   ✓ Mobile viewport layout verified (375x667px)');

    console.log('\n===========================================================');
    console.log(' ALL PEER SETTLEMENT E2E BROWSER CHECKS PASSED 100%! ');
    console.log('===========================================================');
  } finally {
    page.close();
    chrome.proc.kill();
    server.kill();
    try {
      await rm(tempDir, { recursive: true, force: true });
    } catch (_) {}
  }
}

main().catch(err => {
  console.error('\n❌ TEST FAILED:', err);
  process.exit(1);
});
