/**
 * Verification test for item deletion allocation preservation and pending claim re-confirmation:
 * 1. Organizer adds 2 items: "Chicken Rice" (RM 10.00) and "Iced Tea" (RM 4.00).
 * 2. Approves & seals receipt.
 * 3. Allocates "Chicken Rice" to Organizer and "Iced Tea" to Diner B.
 * 4. Deletes "Chicken Rice" (clearing its allocations with dialog confirmation).
 * 5. Asserts that "Iced Tea" remains allocated and its allocation is preserved and confirmed.
 * 6. Organizer re-approves & seals receipt for remaining item.
 * 7. "Finalize & Calculate Bill" becomes enabled and meal finalizes cleanly without pending_claim or incomplete_quantity errors!
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
  if (process.platform === 'win32') {
    const programFiles = process.env.ProgramFiles || '';
    const programFilesX86 = process.env['ProgramFiles(x86)'] || '';
    const localAppData = process.env.LOCALAPPDATA || '';
    const candidates = [
      programFiles ? path.join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? path.join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      localAppData ? path.join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFiles ? path.join(programFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
    ];
    for (const c of candidates) {
      if (c && existsSync(c)) return c;
    }
  }
  return 'google-chrome';
}

function resolvePythonPath() {
  if (process.platform === 'win32' && existsSync('C:\\Python314\\python.exe')) {
    return 'C:\\Python314\\python.exe';
  }
  return 'python';
}

async function getFreePort() {
  return new Promise((res, rej) => {
    const s = createServer();
    s.listen(0, '127.0.0.1', () => {
      const port = s.address().port;
      s.close(() => res(port));
    });
    s.on('error', rej);
  });
}

class CDPPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.callbacks = new Map();
    this.dialogCallbacks = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });

    this.ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.method === 'Runtime.consoleAPICalled') {
        const text = msg.params.args.map(a => a.value || a.description || JSON.stringify(a)).join(' ');
        console.log(`[Browser Console ${msg.params.type}] ${text}`);
      }
      if (msg.method === 'Page.javascriptDialogOpening') {
        const dialog = msg.params;
        if (this.dialogCallbacks.length > 0) {
          const handler = this.dialogCallbacks.shift();
          handler(dialog);
        } else {
          this.send('Page.handleJavaScriptDialog', { accept: true });
        }
      }
      if (msg.id && this.callbacks.has(msg.id)) {
        const cb = this.callbacks.get(msg.id);
        this.callbacks.delete(msg.id);
        if (msg.error) cb.reject(new Error(msg.error.message));
        else cb.resolve(msg.result);
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

  onNextDialog(handler) {
    this.dialogCallbacks.push(handler);
  }

  async evaluate(fn, ...args) {
    const expr = `(${fn.toString()})(${args.map(a => JSON.stringify(a)).join(',')})`;
    const res = await this.send('Runtime.evaluate', {
      expression: expr,
      returnByValue: true,
      awaitPromise: true,
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval error: ${JSON.stringify(res.exceptionDetails)}`);
    }
    return res.result ? res.result.value : undefined;
  }

  async waitFor(predicateFn, timeoutMs = 12000, pollIntervalMs = 100, ...args) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        let ok;
        if (typeof predicateFn === 'string') {
          const res = await this.send('Runtime.evaluate', {
            expression: predicateFn,
            returnByValue: true,
            awaitPromise: true,
          });
          ok = res.result && res.result.value;
        } else {
          ok = await this.evaluate(predicateFn, ...args);
        }
        if (ok) return ok;
      } catch (e) {
        // ignore and retry
      }
      await new Promise(r => setTimeout(r, pollIntervalMs));
    }
    throw new Error(`waitFor timed out after ${timeoutMs}ms for: ${predicateFn}`);
  }

  async close() {
    try {
      this.ws.close();
    } catch {}
  }
}

async function runTest() {
  const tmpDir = await mkdtemp(join(tmpdir(), 'settletable-alloc-preserve-'));
  const dbPath = join(tmpDir, 'test.db');
  const port = await getFreePort();
  const chromePort = await getFreePort();
  const chromeDir = join(tmpDir, 'chrome-user-data');

  let serverProc = null;
  let chromeProc = null;
  let page = null;

  try {
    console.log('[Test] Starting server on port', port);
    const pythonBin = resolvePythonPath();
    const env = {
      ...process.env,
      SETTLETABLE_STORAGE: dbPath,
      SETTLETABLE_SECRET: 'test-secret-alloc-preserve',
      SETTLETABLE_MOCK_CAPTURE: '1',
      SETTLETABLE_TEST_OWNER: '1',
      PYTHONUNBUFFERED: '1',
    };

    const runnerScript = join(REPO_ROOT, 'tools', 'run_demo.py');
    serverProc = spawn(pythonBin, [
      '-u', runnerScript,
      '--host', '127.0.0.1',
      '--port', String(port),
      '--db', dbPath,
      '--mock-notion',
      '--mock-ocr',
    ], {
      cwd: REPO_ROOT,
      env,
      stdio: 'inherit',
    });

    // Wait for server ready
    const serverUrl = `http://127.0.0.1:${port}`;
    let healthy = false;
    for (let i = 0; i < 40; i++) {
      try {
        const res = await fetch(`${serverUrl}/`);
        if (res.ok) {
          healthy = true;
          break;
        }
      } catch {}
      await new Promise(r => setTimeout(r, 200));
    }
    if (!healthy) throw new Error('Server failed to start');
    console.log('[Test] Server is healthy.');

    // Launch Chrome
    const chromeBin = resolveChromePath();
    chromeProc = spawn(chromeBin, [
      `--remote-debugging-port=${chromePort}`,
      `--user-data-dir=${chromeDir}`,
      '--no-first-run',
      '--no-default-browser-check',
      '--headless=new',
      '--disable-gpu',
      'about:blank',
    ], { stdio: 'ignore' });

    // Wait for Chrome remote debugging
    let wsUrl = null;
    for (let i = 0; i < 40; i++) {
      try {
        const vRes = await fetch(`http://127.0.0.1:${chromePort}/json/version`);
        if (vRes.ok) {
          const vData = await vRes.json();
          wsUrl = vData.webSocketDebuggerUrl;
          break;
        }
      } catch {}
      await new Promise(r => setTimeout(r, 200));
    }
    if (!wsUrl) throw new Error('Chrome remote debugging unavailable');

    const listRes = await fetch(`http://127.0.0.1:${chromePort}/json/list`);
    const listData = await listRes.json();
    const targetWs = listData[0]?.webSocketDebuggerUrl;
    page = new CDPPage(targetWs);
    await page.send('Page.enable');
    await page.send('Runtime.enable');

    console.log('[Test] Bootstrapping room with Alice (organizer) & Bob (diner)...');
    await page.send('Page.navigate', { url: serverUrl });
    await page.waitFor('document.readyState === "complete"');

    // 1. Create room
    await page.waitFor(() => Boolean(document.getElementById('create-meal-id')));
    await page.evaluate(() => {
      document.getElementById('create-meal-id').value = 'Test Meal Preserve';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-submit-btn').click();
    });

    await page.waitFor(() => Boolean(document.getElementById('add-item-form')));
    const mealId = await page.evaluate(() => window.settletable.state.mealId);
    console.log('Created room:', mealId);

    // 2. Add 2 items: Chicken Rice (RM 10.00) & Iced Tea (RM 4.00)
    console.log('[Test] Adding 2 items: Chicken Rice (RM 10.00) & Iced Tea (RM 4.00)...');
    await page.waitFor(() => Boolean(document.getElementById('new-item-label')));
    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Chicken Rice';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '10.00';
      document.getElementById('add-item-form').querySelector('button[type="submit"]').click();
    });
    await page.waitFor(() => (window.settletable.state.snapshot?.receipt?.items || []).length === 1);

    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Iced Tea';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '4.00';
      document.getElementById('add-item-form').querySelector('button[type="submit"]').click();
    });
    await page.waitFor(() => (window.settletable.state.snapshot?.receipt?.items || []).length === 2);
    console.log('✓ 2 items added.');

    // 3. Approve & Seal receipt
    console.log('[Test] Approving & sealing receipt...');
    await page.waitFor(() => Boolean(document.getElementById('review-confirm-check')));
    await page.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('review-submit-btn').click();
    });
    await page.waitFor(() => Boolean(window.settletable.state.snapshot?.review));
    console.log('✓ Receipt sealed.');

    // 5. Allocate Chicken Rice to Alice, Iced Tea to Bob
    console.log('[Test] Allocating Chicken Rice to Alice and Iced Tea to Bob...');
    const items = await page.evaluate(() => window.settletable.state.snapshot.receipt.items);
    const item1 = items.find(i => i.label === 'Chicken Rice');
    const item2 = items.find(i => i.label === 'Iced Tea');

    const participants = await page.evaluate(() => window.settletable.state.snapshot.participants);
    const alice = participants.find(p => p.name === 'Alice');
    const bob = participants.find(p => p.name === 'Bob');

    // Quick assign item1 to Alice
    await page.evaluate((itemId, pid) => {
      const btn = document.querySelector(`[data-action="hybrid-quick-assign"][data-item="${itemId}"][data-target="${pid}"]`);
      if (btn) btn.click();
    }, item1.id, alice.id);

    await page.waitFor((targetId) => {
      const claims = window.settletable.state.snapshot?.claims || [];
      return claims.some(c => c.item_id === targetId);
    }, 12000, 100, item1.id);

    // Quick assign item2 to Bob
    await page.evaluate((itemId, pid) => {
      const btn = document.querySelector(`[data-action="hybrid-quick-assign"][data-item="${itemId}"][data-target="${pid}"]`);
      if (btn) btn.click();
    }, item2.id, bob.id);

    await page.waitFor((targetId) => {
      const claims = window.settletable.state.snapshot?.claims || [];
      return claims.some(c => c.item_id === targetId);
    }, 12000, 100, item2.id);

    const preDeleteSnap = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      return {
        issues: snap.issues,
        claims: snap.claims.map(c => ({ id: c.item_id, p: c.participant_id, q: c.quantity, status: c.status })),
      };
    });
    console.log('Pre-delete state:', preDeleteSnap);
    if (preDeleteSnap.issues.length > 0) {
      throw new Error(`Unexpected issues before delete: ${JSON.stringify(preDeleteSnap.issues)}`);
    }
    console.log('✓ Both items fully allocated with 0 issues.');

    // 6. Delete Chicken Rice (allocated item)
    console.log('[Test] Deleting allocated item (Chicken Rice)...');
    page.onNextDialog(dialog => {
      console.log('Confirmation dialog:', dialog.message);
      page.send('Page.handleJavaScriptDialog', { accept: true });
    });

    await page.evaluate((itemId) => {
      const btn = document.querySelector(`.delete-receipt-item-btn[data-item-id="${itemId}"]`);
      if (btn) btn.click();
    }, item1.id);

    // Wait for item 1 to be removed from receipt items
    await page.waitFor((targetId) => {
      const snap = window.settletable.state.snapshot;
      return snap.receipt?.items?.length === 1 && snap.receipt.items[0].id === targetId;
    }, 12000, 100, item2.id);

    console.log('✓ Chicken Rice deleted. Checking remaining item (Iced Tea)...');

    // 7. Verify that Iced Tea's allocation is PRESERVED and CONFIRMED
    const postDeleteSnap = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      return {
        itemsCount: snap.receipt.items.length,
        claims: snap.claims.map(c => ({ id: c.item_id, p: c.participant_id, q: c.quantity, status: c.status, finRev: c.financial_revision })),
        finRev: snap.financial_revision,
        issues: snap.issues,
      };
    });
    console.log('Post-delete snapshot:', postDeleteSnap);

    if (postDeleteSnap.itemsCount !== 1) {
      throw new Error(`Expected 1 item remaining, got ${postDeleteSnap.itemsCount}`);
    }
    if (postDeleteSnap.claims.length !== 1) {
      throw new Error(`Expected 1 claim preserved on Iced Tea, got ${postDeleteSnap.claims.length}`);
    }
    const preservedClaim = postDeleteSnap.claims[0];
    if (preservedClaim.id !== item2.id || preservedClaim.p !== bob.id || preservedClaim.status !== 'confirmed') {
      throw new Error(`Preserved claim not confirmed: ${JSON.stringify(preservedClaim)}`);
    }
    console.log('✓ Iced Tea claim preserved and confirmed at new financial revision!');

    // 8. Re-approve & Seal receipt for the modified receipt (remaining item)
    console.log('[Test] Re-approving receipt for the remaining item...');
    await page.waitFor(() => Boolean(document.getElementById('review-confirm-check')));
    await page.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('review-submit-btn').click();
    });

    await page.waitFor(() => Boolean(window.settletable.state.snapshot?.review));
    console.log('✓ Receipt re-approved and sealed.');

    // 9. Check that Finalize is ENABLED and has NO claim issues
    const finalIssues = await page.evaluate(() => window.settletable.state.snapshot.issues);
    console.log('Issues after review:', finalIssues);
    if (finalIssues.length > 0) {
      throw new Error(`Final issues must be empty, got: ${JSON.stringify(finalIssues)}`);
    }

    await page.waitFor(() => {
      const btn = document.getElementById('finalize-btn');
      return btn && !btn.disabled;
    });
    console.log('✓ Finalize button is ENABLED!');

    // 10. Click Finalize & Calculate Bill
    console.log('[Test] Clicking Finalize & Calculate Bill...');
    await page.evaluate(() => {
      document.getElementById('finalize-btn').click();
    });

    await page.waitFor(() => Boolean(window.settletable.state.snapshot?.calculation));
    console.log('✓ Bill calculated and finalized successfully!');

    // ========================================================
    // Part 2: Test Pending Claim UI and 1-Click Re-confirmation Rescue Flow
    // ========================================================
    console.log('\n[Part 2] Testing pending claim UI & re-confirmation rescue flow...');
    // Create new meal
    await page.send('Page.navigate', { url: `${serverUrl}/#/` });
    await page.waitFor(() => Boolean(document.getElementById('create-meal-id')));
    await page.evaluate(() => {
      document.getElementById('create-meal-id').value = 'Pending Claim Rescue Test';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-submit-btn').click();
    });

    await page.waitFor(() => Boolean(document.getElementById('add-item-form')));
    const meal2Id = await page.evaluate(() => window.settletable.state.mealId);
    console.log('Created room 2:', meal2Id);

    // Add item: Burger (RM 20.00)
    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Burger';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '20.00';
      document.getElementById('add-item-form').querySelector('button[type="submit"]').click();
    });
    await page.waitFor(() => (window.settletable.state.snapshot?.receipt?.items || []).length === 1);

    // Approve & seal receipt
    await page.waitFor(() => Boolean(document.getElementById('review-confirm-check')));
    await page.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('review-submit-btn').click();
    });
    await page.waitFor(() => Boolean(window.settletable.state.snapshot?.review));

    // Allocate Burger to Bob
    const burgerItem = await page.evaluate(() => window.settletable.state.snapshot.receipt.items[0]);
    const bobPart = await page.evaluate(() => window.settletable.state.snapshot.participants.find(p => p.name === 'Bob'));
    await page.evaluate((itemId, pid) => {
      const btn = document.querySelector(`[data-action="hybrid-quick-assign"][data-item="${itemId}"][data-target="${pid}"]`);
      if (btn) btn.click();
    }, burgerItem.id, bobPart.id);

    await page.waitFor((targetId) => {
      const claims = window.settletable.state.snapshot?.claims || [];
      return claims.some(c => c.item_id === targetId);
    }, 12000, 100, burgerItem.id);
    console.log('✓ Burger allocated to Bob.');

    // Now artificially bump financial_revision via direct ReplaceReceipt API without recommitting
    // (Simulates receipt modification from an external or older client, producing a pending claim)
    console.log('Injecting receipt modification to induce pending_claim issue...');
    await page.evaluate(async (mId, bItem) => {
      const snap = window.settletable.state.snapshot;
      const res = await fetch(`/api/meals/${mId}/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${window.settletable.state.issuedTokens.organizer || ''}`,
          'X-SettleTable-Action': '1',
        },
        body: JSON.stringify({
          kind: 'ReplaceReceipt',
          command_id: `rcpt-test-${Date.now()}`,
          expected_revision: snap.revision,
          expected_financial_revision: snap.financial_revision,
          receipt: {
            items: [{ id: bItem.id, label: 'Burger Gourmet', quantity: 1, line_sen: 2000 }],
            subtotal_sen: 2000,
            total_sen: 2000,
            adjustments: [],
            included_tax_sen: 0,
          },
        }),
      });
      // Re-seal receipt for the new digest
      const snap2 = await (await fetch(`/api/meals/${mId}/snapshot`)).json();
      await fetch(`/api/meals/${mId}/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${window.settletable.state.issuedTokens.organizer || ''}`,
          'X-SettleTable-Action': '1',
        },
        body: JSON.stringify({
          kind: 'ReviewReceipt',
          command_id: `rev-test-${Date.now()}`,
          expected_revision: snap2.revision,
          expected_financial_revision: snap2.financial_revision,
          receipt_digest: snap2.receipt_digest,
        }),
      });
      window.location.reload();
    }, meal2Id, burgerItem);

    await page.waitFor(() => {
      const snap = window.settletable?.state?.snapshot;
      return snap && snap.issues && snap.issues.includes('pending_claim');
    });
    console.log('✓ Induced pending_claim state confirmed.');

    // Assert UI displays Re-confirmation Needed badge (NOT Fully Allocated)
    const cardBadgeText = await page.evaluate((itemId) => {
      const card = document.getElementById(`item-card-${itemId}`);
      return card ? card.innerText : '';
    }, burgerItem.id);
    console.log('Card text under pending claim:\n', cardBadgeText);
    if (!cardBadgeText.includes('Re-confirmation Needed')) {
      throw new Error(`Expected "Re-confirmation Needed" badge, got: ${cardBadgeText}`);
    }
    if (cardBadgeText.includes('✓ Fully Allocated')) {
      throw new Error(`UI should NOT display "✓ Fully Allocated" when claims are pending!`);
    }
    console.log('✓ UI accurately displays "⚠️ Re-confirmation Needed" badge.');

    // Assert Re-confirm button exists and click it
    await page.waitFor(() => Boolean(document.getElementById('reconfirm-all-btn')));
    console.log('✓ "Re-confirm Allocations" rescue button is present in warning banner.');

    await page.evaluate(() => {
      document.getElementById('reconfirm-all-btn').click();
    });

    // Wait for pending_claim to be resolved
    await page.waitFor(() => {
      const snap = window.settletable.state.snapshot;
      return snap && snap.issues && !snap.issues.includes('pending_claim') && snap.issues.length === 0;
    });
    console.log('✓ 1-click Re-confirm successfully resolved all pending claims and cleared issues!');

    // Verify Finalize button is now enabled and click it
    await page.waitFor(() => {
      const btn = document.getElementById('finalize-btn');
      return btn && !btn.disabled;
    });
    await page.evaluate(() => {
      document.getElementById('finalize-btn').click();
    });
    await page.waitFor(() => Boolean(window.settletable.state.snapshot?.calculation));
    console.log('✓ Meal finalized successfully after rescue re-confirmation!');

    console.log('\n=== ALL TESTS PASSED! Both preservation & rescue flows fully verified! ===');
  } finally {
    if (page) await page.close();
    if (chromeProc) chromeProc.kill();
    if (serverProc) serverProc.kill();
    try {
      await rm(tmpDir, { recursive: true, force: true });
    } catch {}
  }
}

runTest().catch(err => {
  console.error('\n❌ Test failed:', err);
  process.exit(1);
});
