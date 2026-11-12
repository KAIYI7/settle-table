/**
 * Headless Chrome E2E verification of Collaborative Payment Confirmation UX.
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
  const envPath = process.env.CHROME_BIN || process.env.CHROME_PATH || process.env.PUPPETEER_EXECUTABLE_PATH;
  if (envPath && existsSync(envPath)) return envPath;

  const platform = process.platform;
  const candidates = [];
  if (platform === 'win32') {
    const programFiles = process.env.ProgramFiles || '';
    const programFilesX86 = process.env['ProgramFiles(x86)'] || '';
    const localAppData = process.env.LOCALAPPDATA || '';
    candidates.push(
      programFiles ? join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      localAppData ? join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? join(programFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
      programFiles ? join(programFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : ''
    );
  } else {
    candidates.push('/usr/bin/google-chrome-stable', '/usr/bin/google-chrome', '/usr/bin/chromium');
  }

  for (const p of candidates) {
    if (p && existsSync(p)) return p;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath() {
  const envPath = process.env.PYTHON_BIN || process.env.PYTHON_PATH;
  if (envPath && existsSync(envPath)) return envPath;
  if (process.platform === 'win32') {
    const sysDrive = process.env.SystemDrive || '';
    const py314 = sysDrive ? join(sysDrive, 'Python314', 'python.exe') : '';
    const py312 = sysDrive ? join(sysDrive, 'Python312', 'python.exe') : '';
    if (py314 && existsSync(py314)) return py314;
    if (py312 && existsSync(py312)) return py312;
    return 'python';
  }
  return 'python3';
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(`Assertion failed: ${message}`);
  }
}

class CDPPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.callbacks = new Map();
    this.ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && this.callbacks.has(msg.id)) {
        const { resolve, reject } = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
      }
    };
  }

  async ready() {
    if (this.ws.readyState === WebSocket.OPEN) return;
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
  }

  async send(method, params = {}) {
    await this.ready();
    return new Promise((resolve, reject) => {
      const id = ++this.id;
      this.callbacks.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async navigate(url) {
    await this.send('Page.navigate', { url });
  }

  async evaluate(fn, ...args) {
    const expr = `(${fn.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`;
    const res = await this.send('Runtime.evaluate', {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Evaluation exception: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result?.value;
  }

  async waitFor(fn, timeoutMs = 15000, intervalMs = 100) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      const ok = await this.evaluate(fn).catch(() => false);
      if (ok) return true;
      await new Promise(r => setTimeout(r, intervalMs));
    }
    throw new Error(`Timeout waiting for condition: ${fn.toString()}`);
  }

  async getSessionCookie(origin) {
    const res = await this.send('Network.getCookies', { urls: [origin] });
    return res.cookies?.find(c => c.name === 'settletable_session')?.value || null;
  }

  async setSessionCookie(origin, value) {
    await this.send('Network.setCookie', {
      name: 'settletable_session',
      value: value,
      url: origin,
      httpOnly: true,
      sameSite: 'Strict',
    });
  }

  async close() {
    this.ws.close();
  }
}

async function startChrome(chromeBin, port, dataDir) {
  const proc = spawn(chromeBin, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    '--remote-debugging-address=127.0.0.1',
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
    await page.send('Network.enable');
    return { proc, page };
  } catch (error) {
    proc.kill();
    throw error;
  }
}

async function main() {
  console.log('--- Starting Collaborative Payment Confirmation UX E2E Verification ---');
  const serverPort = 8094;
  await new Promise((resolve, reject) => {
    const probe = createServer();
    probe.once('error', reject);
    probe.listen(serverPort, '127.0.0.1', () => probe.close(resolve));
  });

  const mealId = `collab-e2e-${randomBytes(4).toString('hex')}`;
  const dir = await mkdtemp(join(tmpdir(), 'settletable-collab-test-'));
  const capture = join(dir, 'mock-payload.json');
  const owner = randomBytes(32).toString('hex');
  const origin = `http://127.0.0.1:${serverPort}`;

  let server, chrome;

  try {
    console.log(`[1/8] Starting isolated SettleTable server on port ${serverPort}...`);
    server = spawn(resolvePythonPath(), [
      '-u', join(REPO_ROOT, 'tools', 'verify_financial_export_runner.py'),
      '--host', '127.0.0.1', '--port', String(serverPort), '--db', join(dir, 'test.sqlite'),
      '--mock-notion', '--mock-ocr',
    ], {
      cwd: REPO_ROOT,
      env: { ...process.env, SETTLETABLE_MOCK_CAPTURE: capture, SETTLETABLE_TEST_OWNER: owner }
    });

    let serverError;
    server.on('error', error => { serverError = error; });
    server.stderr.on('data', data => process.stderr.write(data));

    let ready = false;
    for (let i = 0; i < 100; i++) {
      if (serverError) throw serverError;
      if (server.exitCode !== null) throw Error('Loopback server exited');
      try {
        const response = await fetch(origin + '/__financial_test_owner__');
        if (response.ok && await response.text() === owner && server.exitCode === null) {
          ready = true;
          break;
        }
      } catch (e) {}
      await new Promise(r => setTimeout(r, 100));
    }
    assert(ready, 'Server did not report ready');
    console.log('   ✓ Server healthy and ready');

    console.log(`[2/8] Launching Headless Chrome...`);
    const chromeDir = join(dir, 'chrome');
    await fs.promises.mkdir(chromeDir);
    chrome = await startChrome(resolveChromePath(), serverPort + 10, chromeDir);
    const { page } = chrome;
    await page.send('Page.setDeviceMetricsOverride', {
      width: 1200,
      height: 900,
      deviceScaleFactor: 1,
      mobile: false,
    });

    console.log('[3/8] Creating meal room with Alice (organizer), Bob, and Charlie...');
    await page.navigate(origin + '/');
    await page.waitFor(() => document.getElementById('create-meal-form') !== null);

    // Fill create meal form
    await page.evaluate((mid) => {
      document.getElementById('create-meal-id').value = mid;
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob, Charlie';
      document.getElementById('create-meal-form').requestSubmit();
    }, mealId);

    await page.waitFor(() => document.getElementById('manual-refresh-btn') !== null);
    console.log('   ✓ Room created: Alice (Organizer), Bob, Charlie');

    console.log('[4/8] Setting receipt: Total RM 100.00 and allocating item portions...');
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
            { id: 'item-3', label: 'Platter', quantity: [1, 1], line_sen: 4000 },
          ],
          adjustments: [],
          subtotal_sen: 10000,
          total_sen: 10000,
          included_tax_sen: 0,
        }
      });
      await fetchSnapshot(true);
    }, mealId);

    // Confirm receipt
    await page.evaluate(() => {
      document.getElementById('review-confirm-check').checked = true;
      document.getElementById('review-confirm-check').dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitFor(() => !document.getElementById('review-submit-btn').disabled);
    await page.evaluate(() => document.getElementById('review-submit-btn').click());
    await page.waitFor(() => document.getElementById('receipt-verified-status') !== null);

    // Allocations:
    // Alice claims Pasta (RM 30)
    // Bob claims Pizza (RM 30)
    // Charlie claims Platter (RM 40)
    const tokens = await page.evaluate(async (mid) => {
      const snap = state.snapshot;
      const alice = snap.participants.find(p => p.name === 'Alice');
      const bob = snap.participants.find(p => p.name === 'Bob');
      const charlie = snap.participants.find(p => p.name === 'Charlie');
      const rev = snap.financial_revision;
      const item1Rev = snap.items.find(i => i.item_id === 'item-1').item_revision;
      const item2Rev = snap.items.find(i => i.item_id === 'item-2').item_revision;
      const item3Rev = snap.items.find(i => i.item_id === 'item-3').item_revision;

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
        participant_id: bob.id,
        item_id: 'item-2',
        quantity: 1,
        expected_item_revision: item2Rev,
        expected_financial_revision: rev,
      });
      await apiCall(`/api/meals/${mid}/apply`, 'POST', {
        kind: 'AssignParticipantQuantity',
        command_id: `assign-charlie-${Date.now()}`,
        participant_id: charlie.id,
        item_id: 'item-3',
        quantity: 1,
        expected_item_revision: item3Rev,
        expected_financial_revision: rev,
      });
      await fetchSnapshot(true);

      // Finalize
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
      await fetchSnapshot(true);

      // Issue invitation for Bob on finalized meal
      const invBob = await apiCall(`/api/meals/${mid}/invitations`, 'POST', { participant_id: bob.id });

      return {
        mealId: mid,
        aliceId: alice.id,
        bobId: bob.id,
        charlieId: charlie.id,
        bobInviteToken: invBob.token,
      };
    }, mealId);

    const aliceCookie = await page.getSessionCookie(origin);
    await page.waitFor(() => state.snapshot?.finalized && document.getElementById('restaurant-funding-card') !== null);
    console.log('   ✓ Receipt finalized at RM 100.00: Alice RM 30, Bob RM 30, Charlie RM 40');

    // STEP 5: Switch to Diner Bob (non-organizer). Verify diner UI and report payment.
    console.log('[5/8] Verifying Bob (non-organizer) counter payment reporting...');
    await page.evaluate(async (data) => {
      await apiCall(`/api/meals/${data.mealId}/invitations/redeem`, 'POST', { invitation_token: data.bobInviteToken });
      state.token = null;
      await fetchSnapshot(true);
    }, tokens);
    const bobCookie = await page.getSessionCookie(origin);

    // Verify Bob does not see organizer's record payment form, but sees toggle button
    const bobUiState = await page.evaluate(() => {
      const orgForm = document.getElementById('record-contribution-btn');
      const dinerToggle = document.getElementById('toggle-diner-contrib-panel-btn');
      return {
        hasOrgForm: orgForm !== null,
        hasDinerToggle: dinerToggle !== null,
      };
    });
    assert(!bobUiState.hasOrgForm, 'Bob should not see organizer record payment button');
    assert(bobUiState.hasDinerToggle, 'Bob should see "I Paid the Restaurant Counter" toggle');
    console.log('   ✓ Bob has role-appropriate UI: Organizer form hidden, Diner report button present');

    // Bob opens panel and reports RM 60.00 cash payment at counter
    await page.evaluate(async (data) => {
      const snap = state.snapshot;
      await apiCall(`/api/meals/${data.mealId}/apply`, 'POST', {
        kind: 'ReportContribution',
        command_id: `rpay-${Date.now()}`,
        expected_revision: snap.revision,
        participant_id: data.bobId,
        amount_sen: 6000,
        payment_method: 'cash',
      });
      await fetchSnapshot(true);
    }, tokens);

    await page.waitFor(() => (state.snapshot.pending_contributions || []).length > 0);

    const pendingCheckBob = await page.evaluate(() => {
      const snap = state.snapshot;
      const pc = snap.pending_contributions[0];
      const cancelBtn = document.querySelector('.cancel-pending-contrib-btn');
      const confirmBtn = document.querySelector('.confirm-pending-contrib-btn');
      return {
        amountSen: pc.amount_sen,
        status: pc.status,
        payer: pc.participant_name,
        hasCancelBtn: cancelBtn !== null,
        hasConfirmBtn: confirmBtn !== null,
      };
    });
    assert(pendingCheckBob.amountSen === 6000, 'Expected pending contribution of 6000 sen');
    assert(pendingCheckBob.status === 'pending', 'Expected status pending');
    assert(pendingCheckBob.hasCancelBtn, 'Bob should see Cancel button for his report');
    assert(!pendingCheckBob.hasConfirmBtn, 'Bob CANNOT confirm his own counter payment');
    console.log('   ✓ Bob reported RM 60.00; Bob has Cancel action but NO Confirm action');

    // STEP 6: Alice (Organizer) confirms Bob's payment and funds remaining RM 40.00
    console.log('[6/8] Alice (organizer) confirms Bob payment and finishes bill funding...');
    await page.setSessionCookie(origin, aliceCookie);
    await page.evaluate(async () => {
      state.token = null;
      await fetchSnapshot(true);
    });

    // Alice confirms Bob's reported payment
    await page.evaluate(() => {
      window.confirm = () => true;
      document.querySelector('.confirm-pending-contrib-btn').click();
    });

    await page.waitFor(() => state.snapshot.funding.total_contributed_sen === 6000);
    console.log('   ✓ Bob payment confirmed! Ledger updated to RM 60.00 contributed');

    // Verify audit attribution in recorded payments table
    const auditAttribution = await page.evaluate(() => {
      const card = document.getElementById('restaurant-funding-card');
      return card.innerText;
    });
    assert(auditAttribution.includes('Reported by Bob, confirmed by Alice'),
           `Expected attribution "Reported by Bob, confirmed by Alice", got: ${auditAttribution}`);
    console.log('   ✓ Audit ledger attribution verified: "Reported by Bob, confirmed by Alice"');

    // Alice records remaining RM 40.00 from Charlie to complete restaurant bill
    await page.evaluate((data) => {
      const select = document.getElementById('payer-participant-select');
      select.value = data.charlieId;
      document.getElementById('payer-amount-input').value = '40.00';
      document.getElementById('payer-method-select').value = 'card';
      document.getElementById('record-contribution-btn').click();
    }, tokens);

    await page.waitFor(() => state.snapshot.funding.status === 'fully_funded');
    console.log('   ✓ Bill 100% funded! Total: RM 100.00 (Bob covered 60, Charlie covered 40)');

    // Net balances:
    // Alice consumed 30, contributed 0 -> Net -30.00 (owes 30)
    // Bob consumed 30, contributed 60 -> Net +30.00 (recovers 30)
    // Charlie consumed 40, contributed 40 -> Net 0.00 (balanced)
    // Suggested transfer: Alice pays Bob RM 30.00

    // STEP 7: Alice owes Bob RM 30.00. Alice reports sent payment to Bob.
    console.log('[7/8] Testing Peer Reimbursement: Alice reports sent payment to Bob...');
    await page.evaluate(async (data) => {
      const snap = state.snapshot;
      await apiCall(`/api/meals/${data.mealId}/apply`, 'POST', {
        kind: 'ReportTransfer',
        command_id: `rxfer-${Date.now()}`,
        expected_revision: snap.revision,
        sender_id: data.aliceId,
        receiver_id: data.bobId,
        amount_sen: 3000,
        note: 'DuitNow ref 888',
      });
      await fetchSnapshot(true);
    }, tokens);

    await page.waitFor(() => (state.snapshot.pending_transfers || []).length > 0);
    console.log('   ✓ Alice reported RM 30.00 reimbursement to Bob');

    // Verify Alice cannot confirm her own sent payment
    const aliceTransferUi = await page.evaluate(() => {
      const confirmBtn = document.querySelector('.confirm-pending-transfer-btn');
      const cancelBtn = document.querySelector('.cancel-pending-transfer-btn');
      return {
        hasConfirm: confirmBtn !== null,
        hasCancel: cancelBtn !== null,
      };
    });
    assert(!aliceTransferUi.hasConfirm, 'Sender Alice CANNOT confirm her own sent payment');
    assert(aliceTransferUi.hasCancel, 'Sender Alice can cancel her pending report');
    console.log('   ✓ Anti-self-confirmation verified: Sender cannot confirm own payment');

    // STEP 8: Bob (recipient creditor) confirms reimbursement receipt!
    console.log('[8/8] Bob (recipient creditor) confirms reimbursement receipt...');
    await page.setSessionCookie(origin, bobCookie);
    await page.evaluate(async () => {
      state.token = null;
      await fetchSnapshot(true);
    });

    // Bob sees "Confirm Received" button
    const bobCanConfirm = await page.evaluate(() => {
      return document.querySelector('.confirm-pending-transfer-btn') !== null;
    });
    assert(bobCanConfirm, 'Recipient Bob must see "Confirm Received" button');

    // Bob clicks Confirm Received
    await page.evaluate(() => {
      window.confirm = () => true;
      document.querySelector('.confirm-pending-transfer-btn').click();
    });

    await page.waitFor(() => state.snapshot.settlement.is_settled);
    console.log('   ✓ Bob confirmed receipt! All debts settled (is_settled = true)');

    // Verify audit attribution in recorded peer reimbursements ledger
    const xferAuditAttribution = await page.evaluate(() => {
      const card = document.getElementById('peer-settlement-card');
      return card.innerText;
    });
    assert(xferAuditAttribution.includes('Reported by Alice, confirmed by Bob'),
           `Expected attribution "Reported by Alice, confirmed by Bob", got: ${xferAuditAttribution}`);
    console.log('   ✓ Peer transfer ledger attribution verified: "Reported by Alice, confirmed by Bob"');

    console.log('--- All 8 Collaborative Payment Verification Steps Passed Successfully! ---');
  } finally {
    if (chrome) {
      chrome.proc.kill();
    }
    if (server) {
      server.kill();
    }
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((err) => {
  console.error('Verification failed with error:', err);
  process.exit(1);
});
