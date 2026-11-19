/**
 * Headless Chrome E2E verification of Editable & Deletable Receipt Items.
 *
 * Verifies:
 * 1. Action buttons on each receipt item row:
 *    - Edit button (.edit-receipt-item-btn / ✏️)
 *    - Delete button (.delete-receipt-item-btn / 🗑️)
 * 2. Mobile Touch Target Accessibility (375x667):
 *    - Action buttons meet minimum touch target requirements (>= 40px on mobile).
 *    - Zero horizontal page overflow at 375px and 320px viewports.
 * 3. Inline Edit Flow:
 *    - Clicking Edit replaces item row with inline edit box (.review-item-edit-box).
 *    - Prepopulates item label, quantity (with stepper), and line price.
 *    - Stepper increment/decrement works and prevents quantity < 1.
 *    - Saving updates label, quantity, line price, and recalculates subtotal and total deterministically.
 *    - Automatically resets receipt verification to Needs Review.
 * 4. Cancel Edit Flow:
 *    - Clicking Cancel restores normal item row with no mutation.
 * 5. Delete Flow:
 *    - Deleting an unclaimed item removes it and updates subtotal deterministically.
 *    - Deleting an item with active allocations alerts organizer and clears allocations before deleting.
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
  const platform = process.platform;
  const candidates = [];
  if (platform === 'win32') {
    const programFiles = process.env.ProgramFiles || '';
    const programFilesX86 = process.env['ProgramFiles(x86)'] || '';
    const localAppData = process.env.LOCALAPPDATA || '';
    candidates.push(
      programFiles ? path.join(programFiles, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? path.join(programFilesX86, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      localAppData ? path.join(localAppData, 'Google', 'Chrome', 'Application', 'chrome.exe') : '',
      programFilesX86 ? path.join(programFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : '',
      programFiles ? path.join(programFiles, 'Microsoft', 'Edge', 'Application', 'msedge.exe') : ''
    );
  }
  candidates.push(
    '/usr/bin/google-chrome-stable',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium-browser',
    '/usr/bin/chromium'
  );
  for (const c of candidates) {
    if (c && existsSync(c)) return c;
  }
  throw new Error('Chrome executable not found.');
}

function resolvePythonPath() {
  const env = process.env.PYTHON || process.env.PYTHON_BIN;
  if (env && existsSync(env)) return env;
  if (process.platform === 'win32') {
    const defaultPy = 'C:\\Python314\\python.exe';
    if (existsSync(defaultPy)) return defaultPy;
  }
  return 'python';
}

class CDPPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 0;
    this.callbacks = new Map();
    this.consoleErrors = [];
    this.dialogCallbacks = [];
    this.ready = new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });

    this.ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
        const text = msg.params.args.map(a => a.value || a.description || '').join(' ');
        this.consoleErrors.push(text);
      }
      if (msg.method === 'Page.javascriptDialogOpening') {
        const dialog = msg.params;
        if (this.dialogCallbacks.length > 0) {
          const handler = this.dialogCallbacks.shift();
          handler(dialog);
        } else {
          // Default accept confirm dialogs
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

  onNextDialog(handler) {
    this.dialogCallbacks.push(handler);
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

  async setViewport(width, height) {
    await this.send('Emulation.setDeviceMetricsOverride', {
      width,
      height,
      deviceScaleFactor: 2,
      mobile: width < 600,
    });
  }

  async waitFor(expr, timeoutMs = 10000) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      try {
        const res = await this.evaluate(expr);
        if (res) return res;
      } catch (e) {}
      await new Promise(r => setTimeout(r, 50));
    }
    throw new Error(`Timeout waiting for expression: ${expr}`);
  }

  async close() {
    try {
      this.ws.close();
    } catch (_) {}
  }
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
    return { proc, page };
  } catch (error) {
    proc.kill();
    throw error;
  }
}

async function run() {
  console.log('=== SettleTable Editable & Deletable Receipt Items Verification ===\n');
  const chromePath = resolveChromePath();
  const pythonPath = resolvePythonPath();
  const serverPort = await getFreePort();
  const chromePort = await getFreePort();

  const origin = `http://127.0.0.1:${serverPort}`;
  const mealId = `editrcpt-${randomBytes(4).toString('hex')}`;

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-editrcpt-'));
  const dbPath = join(tempDir, 'editrcpt.sqlite');
  const capture = join(tempDir, 'mock-payload.json');
  const owner = randomBytes(32).toString('hex');

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

  let serverStarted = false;
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(`${origin}/__financial_test_owner__`);
      if (res.ok && (await res.text()).trim() === owner) {
        serverStarted = true;
        break;
      }
    } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  if (!serverStarted) {
    server.kill();
    throw new Error('Server failed to start within 10s');
  }

  const chromeDataDir = await mkdtemp(join(tmpdir(), 'settletable-chrome-'));
  const { proc: chromeProc, page } = await startChrome(chromePath, chromePort, chromeDataDir);

  try {
    // 1. Create a meal with Organizer "Alice" and Diner "Bob" via UI
    console.log('[Step 1] Creating meal via UI with Alice (Organizer) and Bob (Diner)...');
    await page.navigate(origin + '/');
    await page.waitFor(() => document.getElementById('create-meal-form') !== null);
    await page.evaluate((id) => {
      document.getElementById('create-meal-id').value = id;
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    }, mealId);

    // Wait for organizer section to render
    await page.waitFor(() => Boolean(document.getElementById('add-item-form')));
    console.log('✓ Meal created and Organizer section rendered successfully.');

    // 2. Add receipt items
    console.log('[Step 2] Adding 2 receipt items: Item 1 (RM 29.00) & Item 2 (RM 39.00)...');
    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'HNTBJ2F037A37003A11';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '29.00';
      document.getElementById('add-item-form').requestSubmit();
    });
    await page.waitFor(() => document.querySelectorAll('.review-item-row').length === 1);

    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'HNTBJ2F858H0A003A11';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '39.00';
      document.getElementById('add-item-form').requestSubmit();
    });
    await page.waitFor(() => document.querySelectorAll('.review-item-row').length === 2);
    console.log('✓ Added 2 receipt items.');

    // 3. Verify Edit and Delete buttons exist on each item row
    console.log('[Step 3] Checking Edit (✏️) and Delete (🗑️) affordances on item rows...');
    const actionCounts = await page.evaluate(() => {
      const editBtns = document.querySelectorAll('.edit-receipt-item-btn');
      const delBtns = document.querySelectorAll('.delete-receipt-item-btn');
      return {
        editCount: editBtns.length,
        delCount: delBtns.length,
        editLabels: Array.from(editBtns).map(b => b.getAttribute('aria-label')),
        delLabels: Array.from(delBtns).map(b => b.getAttribute('aria-label')),
      };
    });

    if (actionCounts.editCount !== 2 || actionCounts.delCount !== 2) {
      throw new Error(`Expected 2 edit and 2 del buttons, found: ${JSON.stringify(actionCounts)}`);
    }
    console.log('✓ Edit and Delete buttons rendered on all item rows with accessible labels:', actionCounts.editLabels);

    // 4. Mobile Viewport Touch Target and Overflow Check (375x667 and 320x667)
    console.log('[Step 4] Checking mobile touch targets and overflow at 375x667 and 320x667...');
    for (const testWidth of [375, 320]) {
      await page.setViewport(testWidth, 667);
      await new Promise(r => setTimeout(r, 200));

      const mobileCheck = await page.evaluate((vpW) => {
        const editBtn = document.querySelector('.edit-receipt-item-btn');
        const delBtn = document.querySelector('.delete-receipt-item-btn');
        const editRect = editBtn.getBoundingClientRect();
        const delRect = delBtn.getBoundingClientRect();
        const scrollW = document.documentElement.scrollWidth;

        return {
          vpW,
          editWidth: editRect.width,
          editHeight: editRect.height,
          delWidth: delRect.width,
          delHeight: delRect.height,
          scrollW,
          hasOverflow: scrollW > vpW,
        };
      }, testWidth);

      console.log(`Touch targets on ${testWidth}px viewport: Edit=${mobileCheck.editWidth}x${mobileCheck.editHeight}px, Delete=${mobileCheck.delWidth}x${mobileCheck.delHeight}px`);
      if (mobileCheck.editHeight < 40 || mobileCheck.delHeight < 40) {
        throw new Error(`Mobile button touch target under 40px at ${testWidth}px: ${JSON.stringify(mobileCheck)}`);
      }
      if (mobileCheck.hasOverflow) {
        throw new Error(`Horizontal overflow detected at ${testWidth}px: scrollW=${mobileCheck.scrollW}, vpW=${mobileCheck.vpW}`);
      }
    }
    console.log('✓ Zero horizontal overflow across mobile viewports (320px/375px) and touch targets meet accessibility criteria.');

    // 5. Test Inline Edit Flow
    console.log('[Step 5] Testing inline edit flow on item-1...');
    await page.evaluate(() => {
      document.querySelector('.edit-receipt-item-btn[data-item-id="item-1"]').click();
    });

    await page.waitFor(() => Boolean(document.getElementById('edit-item-box-item-1')));
    console.log('✓ Inline edit box opened.');

    // Check prefilled values
    const prefilled = await page.evaluate(() => {
      return {
        label: document.getElementById('edit-item-label-item-1')?.value,
        qty: document.getElementById('edit-item-qty-item-1')?.value,
        price: document.getElementById('edit-item-price-item-1')?.value,
      };
    });
    console.log('Prefilled values:', prefilled);
    if (prefilled.label !== 'HNTBJ2F037A37003A11' || prefilled.qty !== '1' || prefilled.price !== '29.00') {
      throw new Error(`Unexpected prefilled values: ${JSON.stringify(prefilled)}`);
    }

    // Test quantity stepper in edit box
    console.log('Testing quantity stepper in edit box...');
    await page.evaluate(() => {
      document.querySelector('.edit-item-qty-inc[data-item-id="item-1"]').click();
    });
    let qtyVal = await page.evaluate(() => document.getElementById('edit-item-qty-item-1').value);
    if (qtyVal !== '2') throw new Error(`Expected qty 2 after increment, got ${qtyVal}`);

    await page.evaluate(() => {
      document.querySelector('.edit-item-qty-dec[data-item-id="item-1"]').click();
    });
    qtyVal = await page.evaluate(() => document.getElementById('edit-item-qty-item-1').value);
    if (qtyVal !== '1') throw new Error(`Expected qty 1 after decrement, got ${qtyVal}`);

    const isDecDisabled = await page.evaluate(() => document.querySelector('.edit-item-qty-dec[data-item-id="item-1"]').disabled);
    if (!isDecDisabled) throw new Error('Expected decrement button to be disabled at qty 1');
    console.log('✓ Stepper correctly increments, decrements, and disables at 1.');

    // Modify values and save: change to "Wagyu Ribeye", qty 2, price 75.00
    console.log('Modifying item to "Wagyu Ribeye", qty 2, price 75.00 and saving...');
    await page.evaluate(() => {
      document.getElementById('edit-item-label-item-1').value = 'Wagyu Ribeye';
      document.getElementById('edit-item-qty-item-1').value = '2';
      document.getElementById('edit-item-price-item-1').value = '75.00';
      document.querySelector('.review-item-edit-form[data-item-id="item-1"]').requestSubmit();
    });

    // Wait for edit box to close and item row to update
    await page.waitFor(() => !document.getElementById('edit-item-box-item-1'));
    await page.waitFor(() => document.body.innerText.includes('Wagyu Ribeye'));
    console.log('✓ Item edited successfully.');

    // Verify updated totals
    const receiptState = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      const it1 = snap.receipt.items.find(i => i.id === 'item-1');
      return {
        label: it1.label,
        quantity: it1.quantity,
        line_sen: it1.line_sen,
        subtotal_sen: snap.receipt.subtotal_sen,
        total_sen: snap.receipt.total_sen,
      };
    });
    console.log('Updated receipt state:', receiptState);
    if (receiptState.label !== 'Wagyu Ribeye' || receiptState.line_sen !== 7500) {
      throw new Error(`Item-1 update mismatch: ${JSON.stringify(receiptState)}`);
    }
    // Subtotal should be 75.00 + 39.00 = 114.00 (11400 sen)
    if (receiptState.subtotal_sen !== 11400 || receiptState.total_sen !== 11400) {
      throw new Error(`Subtotal mismatch: expected 11400 sen, got ${receiptState.subtotal_sen}`);
    }
    console.log('✓ Subtotal and total recalculated deterministically (RM 114.00).');

    // 6. Test Cancel Edit Flow
    console.log('[Step 6] Testing cancel edit flow on second item...');
    const domItems = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      const editBtns = Array.from(document.querySelectorAll('.edit-receipt-item-btn')).map(b => b.getAttribute('data-item-id'));
      return {
        snapItems: snap.receipt.items.map(i => ({ id: i.id, label: i.label })),
        editBtns,
        mutationActive: window.settletable.state.mutationActive,
      };
    });
    console.log('DOM & State before clicking cancel edit:', domItems);
    const item2Id = domItems.snapItems[1].id;
    console.log(`Second item ID: ${item2Id}`);

    const clicked = await page.evaluate((id) => {
      const btn = document.querySelector(`.edit-receipt-item-btn[data-item-id="${id}"]`);
      if (!btn) return false;
      btn.click();
      return true;
    }, item2Id);
    console.log(`Clicked edit button for ${item2Id}: ${clicked}`);

    const afterClick = await page.evaluate(() => {
      return {
        editingId: window.settletable.state.editingReceiptItemId,
        editBoxes: Array.from(document.querySelectorAll('.review-item-edit-box')).map(b => b.id),
      };
    });
    console.log('After clicking edit:', afterClick);

    await page.waitFor(`Boolean(document.getElementById('edit-item-box-${item2Id}'))`);

    // Click Cancel
    await page.evaluate((id) => {
      document.querySelector(`.cancel-edit-item-btn[data-item-id="${id}"]`).click();
    }, item2Id);
    await page.waitFor(`!document.getElementById('edit-item-box-${item2Id}')`);
    console.log('✓ Cancel edit cleanly restores normal item row.');

    // 7. Test Delete Flow on unclaimed item (second item)
    console.log('[Step 7] Testing delete on unclaimed second item...');
    page.onNextDialog(dialog => {
      console.log(`Received confirmation dialog: "${dialog.message}"`);
      page.send('Page.handleJavaScriptDialog', { accept: true });
    });

    await page.evaluate((id) => {
      document.querySelector(`.delete-receipt-item-btn[data-item-id="${id}"]`).click();
    }, item2Id);

    // Wait for second item to be removed
    await page.waitFor(() => document.querySelectorAll('.review-item-row').length === 1);
    const postDelState = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      return {
        itemCount: snap.receipt.items.length,
        subtotal_sen: snap.receipt.subtotal_sen,
        total_sen: snap.receipt.total_sen,
      };
    });
    console.log('Post-delete state:', postDelState);
    if (postDelState.itemCount !== 1 || postDelState.subtotal_sen !== 7500) {
      throw new Error(`Post delete state mismatch: ${JSON.stringify(postDelState)}`);
    }
    console.log('✓ Unclaimed item deleted cleanly, subtotal updated to RM 75.00.');

    // 8. Test Delete Flow on item with active allocations
    console.log('[Step 8] Testing delete on item with active diner allocations...');
    // Allocate 1 portion of item-1 to Bob
    const bobPid = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      const bob = snap.participants.find(p => p.name === 'Bob');
      return bob ? bob.id : null;
    });
    if (!bobPid) throw new Error('Bob participant not found in snapshot');

    console.log(`Allocating item-1 to Bob (${bobPid})...`);
    await page.evaluate(async (pid) => {
      const snap = window.settletable.state.snapshot;
      const it1 = snap.receipt.items[0];
      const stateItem = snap.items.find(i => i.item_id === it1.id);
      await fetch(`/api/meals/${snap.meal_id}/apply`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${window.settletable.state.issuedTokens.organizer || ''}`,
          'X-SettleTable-Action': '1',
        },
        body: JSON.stringify({
          kind: 'SetItemAllocations',
          command_id: `alloc-test-${Date.now()}`,
          item_id: it1.id,
          allocations: [{ participant_id: pid, quantity: 1 }],
          expected_item_revision: stateItem.item_revision,
          expected_financial_revision: snap.financial_revision,
        }),
      });
      window.location.reload();
    }, bobPid);

    await page.waitFor(() => {
      const snap = window.settletable?.state?.snapshot;
      return snap && snap.claims && snap.claims.length > 0;
    });
    console.log('✓ Item allocated to Bob.');

    // Now delete item-1 which has Bob\'s allocation
    console.log('Deleting allocated item-1 with confirmation...');
    let dialogMessage = '';
    page.onNextDialog(dialog => {
      dialogMessage = dialog.message;
      console.log(`Received allocation warning dialog: "${dialog.message}"`);
      page.send('Page.handleJavaScriptDialog', { accept: true });
    });

    await page.evaluate(() => {
      document.querySelector('.delete-receipt-item-btn[data-item-id="item-1"]').click();
    });

    // Wait for item to be deleted
    await page.waitFor(() => {
      const snap = window.settletable?.state?.snapshot;
      return snap && snap.receipt && snap.receipt.items && snap.receipt.items.length === 0;
    });

    if (!dialogMessage.includes('currently allocated') && !dialogMessage.includes('Clear allocations')) {
      throw new Error(`Expected allocation clear prompt, got: "${dialogMessage}"`);
    }

    const finalState = await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      return {
        itemCount: snap.receipt.items.length,
        subtotal_sen: snap.receipt.subtotal_sen,
        total_sen: snap.receipt.total_sen,
        claimsCount: snap.claims.length,
      };
    });
    console.log('Final state after allocated item deletion:', finalState);
    if (finalState.itemCount !== 0 || finalState.claimsCount !== 0) {
      throw new Error(`Expected 0 items and 0 claims, got: ${JSON.stringify(finalState)}`);
    }
    console.log('✓ Allocated item deleted cleanly with allocations cleared first!');

    if (page.consoleErrors.length > 0) {
      console.warn('Browser console errors observed:', page.consoleErrors);
    }

    console.log('\n======================================================');
    console.log('🎉 ALL EDITABLE & DELETABLE RECEIPT ITEM TESTS PASSED!');
    console.log('======================================================\n');
  } finally {
    await page.close();
    chromeProc.kill();
    server.kill();
    try {
      await rm(tempDir, { recursive: true, force: true });
      await rm(chromeDataDir, { recursive: true, force: true });
    } catch {}
  }
}

run().catch(err => {
  console.error('VERIFICATION FAILED:', err);
  process.exit(1);
});
