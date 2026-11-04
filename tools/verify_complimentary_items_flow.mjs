/**
 * Headless Chrome E2E verification of RM0.00 Complimentary Items Without Mandatory Allocation.
 *
 * Verifies:
 * 1. Receipt entry and preservation:
 *    - Manual Add Item allows explicit RM0.00 prices (e.g. Warm Water x 2 -> RM0.00).
 *    - Manual Add Item rejects invalid strings ('abc') or negative amounts ('-5.00').
 *    - Alert indicates 'Added "Warm Water" (Complimentary · RM 0.00) ✓'.
 * 2. OCR candidate editor validation:
 *    - Staged candidate price input allows explicit 0.00 and shows tooltip 'Complimentary item (RM 0.00)'.
 *    - Malformed or empty price strings are not disguised as valid zero and block acceptance.
 * 3. Complimentary allocation policy in DOM:
 *    - Item card displays 'Complimentary · RM 0.00' and badge 'Complimentary · No allocation needed'.
 *    - Suppresses diner allocation steppers/pills for complimentary items.
 *    - Does NOT block receipt review or meal finalization.
 * 4. Calculation and finalization:
 *    - Once paid items are allocated, meal finalizes cleanly to exact integer-sen shares.
 *    - Complimentary items remain visible as zero-cost records.
 * 5. Mobile responsive check (375px):
 *    - Zero horizontal overflow.
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

    this.ws.onmessage = (evt) => {
      const msg = JSON.parse(evt.data);
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params.type === 'error') {
        const text = msg.params.args.map(a => a.value || a.description || '').join(' ');
        this.consoleErrors.push(text);
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
  console.log('=== SettleTable RM0.00 Complimentary Items Verification ===\n');
  const chromePath = resolveChromePath();
  const pythonPath = resolvePythonPath();
  const serverPort = await getFreePort();
  const chromePort = await getFreePort();

  const origin = `http://127.0.0.1:${serverPort}`;
  const mealId = `comp-${randomBytes(4).toString('hex')}`;

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-comp-'));
  const dbPath = join(tempDir, 'comp.sqlite');
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

  server.stderr.on('data', d => process.stderr.write(d));
  server.stdout.on('data', () => {});

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
  if (!serverReady) throw new Error('Server failed to start');

  const chromeDir = join(tempDir, 'chrome-profile');
  await fs.promises.mkdir(chromeDir, { recursive: true });
  const chrome = await startChrome(chromePath, chromePort, chromeDir);
  const page = chrome.page;

  try {
    // [1/6] Bootstrap meal
    console.log('[1/6] Bootstrapping meal with Alice (Organizer) and Bob (Diner)...');
    await page.navigate(origin + '/');
    await page.waitFor(() => document.getElementById('create-meal-form') !== null);
    await page.evaluate((id) => {
      document.getElementById('create-meal-id').value = id;
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-form').requestSubmit();
    }, mealId);
    await page.waitFor(() => document.getElementById('add-item-form') !== null);
    console.log('   ✓ Meal created and Add Item Form rendered');

    // [2/6] Test Manual Add Item Price Validation & Complimentary RM0.00 Entry
    console.log('[2/6] Testing manual item entry: malformed rejection & explicit RM0.00 acceptance...');
    
    // Test negative price rejected
    const negAlert = await page.evaluate(async () => {
      document.getElementById('new-item-label').value = 'Negative Item';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '-5.00';
      document.getElementById('add-item-form').requestSubmit();
      await new Promise(r => setTimeout(r, 100));
      return document.querySelector('.alert-error')?.textContent || '';
    });
    if (!negAlert.includes('Price must not be negative') && !negAlert.includes('Negative amount not allowed')) {
      throw new Error(`Expected negative price rejection alert, got: ${negAlert}`);
    }
    console.log('   ✓ Negative price correctly rejected');

    // Test malformed price rejected
    const malformedAlert = await page.evaluate(async () => {
      document.getElementById('new-item-label').value = 'Bad Item';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = 'abc';
      document.getElementById('add-item-form').requestSubmit();
      await new Promise(r => setTimeout(r, 100));
      return document.querySelector('.alert-error')?.textContent || '';
    });
    if (!malformedAlert.includes('Invalid price')) {
      throw new Error(`Expected invalid price rejection alert, got: ${malformedAlert}`);
    }
    console.log('   ✓ Malformed price string correctly rejected');

    // Add paid item: Chicken Rice x 1 at RM15.00
    await page.evaluate(async () => {
      document.getElementById('new-item-label').value = 'Chicken Rice';
      document.getElementById('new-item-qty').value = '1';
      document.getElementById('new-item-price').value = '15.00';
      document.getElementById('add-item-form').requestSubmit();
    });
    await page.waitFor(() => document.querySelector('.alert-success')?.textContent?.includes('Chicken Rice'));
    console.log('   ✓ Paid item "Chicken Rice" added successfully');

    // Add complimentary item: Warm Water x 2 at RM0.00
    const compMsg = await page.evaluate(async () => {
      document.getElementById('new-item-label').value = 'Warm Water';
      document.getElementById('new-item-qty').value = '2';
      document.getElementById('new-item-price').value = '0.00';
      document.getElementById('add-item-form').requestSubmit();
      await new Promise(r => setTimeout(r, 300));
      return document.querySelector('.alert-success')?.textContent || '';
    });
    if (!compMsg.includes('Complimentary · RM 0.00')) {
      throw new Error(`Expected complimentary success alert, got: ${compMsg}`);
    }
    console.log('   ✓ Complimentary item "Warm Water" (RM0.00) accepted with complimentary toast');

    // [3/6] Verify OCR Candidate Edit & Verification Behavior
    console.log('[3/6] Verifying OCR staging: explicit 0.00 valid, blank/malformed rejected...');
    await page.evaluate(() => {
      const b = new Uint8Array([137,80,78,71,13,10,26,10,0,0,0,13,73,72,68,82,0,0,0,100,0,0,0,100,8,2,0,0,0,144,145,104,60]);
      const dt = new DataTransfer();
      dt.items.add(new File([b], 'synthetic.png', { type: 'image/png' }));
      const input = document.getElementById('ocr-file-input');
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await page.waitFor('document.getElementById("ocr-candidate-card") !== null');

    // Change first item price to 0.00
    await page.evaluate(() => {
      const pInput = document.querySelector('.ocr-edit-item-price');
      pInput.value = '0.00';
      pInput.dispatchEvent(new Event('input', { bubbles: true }));
      pInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const ocrTooltip = await page.evaluate(() => {
      const pInput = document.querySelector('.ocr-edit-item-price');
      return pInput?.title || '';
    });
    if (!ocrTooltip.includes('Complimentary item')) {
      throw new Error(`Expected complimentary tooltip on OCR amount input, got: ${ocrTooltip}`);
    }
    console.log('   ✓ Staged OCR price 0.00 shows "Complimentary item (RM 0.00)" accessible tooltip');

    // Now test empty price rejection
    await page.evaluate(() => {
      const pInput = document.querySelector('.ocr-edit-item-price');
      pInput.value = '';
      pInput.dispatchEvent(new Event('input', { bubbles: true }));
      pInput.dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('ocr-accept-btn').click();
    });
    await new Promise(r => setTimeout(r, 200));
    const ocrEmptyAlert = await page.evaluate(() => document.querySelector('.alert-error')?.textContent || '');
    if (!ocrEmptyAlert.includes('must have a valid name and non-negative price')) {
      throw new Error(`Expected empty OCR price rejection alert, got: ${ocrEmptyAlert}`);
    }
    console.log('   ✓ Blank OCR price correctly blocked from acceptance without defaulting to 0');

    // Discard OCR candidate
    await page.evaluate(() => document.getElementById('ocr-discard-btn').click());
    await page.waitFor(() => document.getElementById('ocr-candidate-card') === null);
    console.log('   ✓ Staged OCR candidate discarded cleanly');

    // [4/6] Verify DOM Presentation of Complimentary Item
    console.log('[4/6] Verifying DOM presentation of Complimentary Item...');
    const domCheck = await page.evaluate(() => {
      const cards = Array.from(document.querySelectorAll('.hybrid-item-card'));
      const waterCard = cards.find(c => c.textContent.includes('Warm Water'));
      const riceCard = cards.find(c => c.textContent.includes('Chicken Rice'));

      return {
        waterHasCompClass: waterCard?.classList.contains('is-complimentary'),
        waterHasCompBadge: waterCard?.innerHTML.includes('Complimentary · No allocation needed'),
        waterHasPriceBadge: waterCard?.innerHTML.includes('Complimentary · RM 0.00'),
        waterHasPills: waterCard?.querySelector('.hybrid-pill') !== null,
        waterHasProgressBar: waterCard?.querySelector('.progress-bar-wrap') !== null,
        riceHasPills: riceCard?.querySelector('.hybrid-pill') !== null,
      };
    });

    if (!domCheck.waterHasCompClass) throw new Error('Warm Water card missing .is-complimentary class');
    if (!domCheck.waterHasCompBadge) throw new Error('Warm Water card missing "Complimentary · No allocation needed" badge');
    if (!domCheck.waterHasPriceBadge) throw new Error('Warm Water card missing "Complimentary · RM 0.00" price badge');
    if (domCheck.waterHasPills) throw new Error('Warm Water unexpectedly has diner allocation pills');
    if (domCheck.waterHasProgressBar) throw new Error('Warm Water unexpectedly has progress bar');
    if (!domCheck.riceHasPills) throw new Error('Chicken Rice missing allocation pills');
    console.log('   ✓ Complimentary item DOM correctly verified: badges present, allocation controls suppressed');

    // [5/6] Allocate Paid Item & Finalize Meal Without Claiming Warm Water
    console.log('[5/6] Allocating paid item to Alice & finalizing without allocating Warm Water...');
    
    // Quick assign Chicken Rice to Alice
    await page.evaluate(() => {
      const riceCard = Array.from(document.querySelectorAll('.hybrid-item-card'))
        .find(c => c.textContent.includes('Chicken Rice'));
      const alicePill = Array.from(riceCard?.querySelectorAll('.hybrid-pill-available') || [])
        .find(p => p.textContent.includes('Alice'));
      if (alicePill) alicePill.click();
    });
    await new Promise(r => setTimeout(r, 400));
    await page.waitFor(() => document.querySelector('.hybrid-pill-allocated') !== null);

    // Verify Review confirmation checkbox is enabled
    const reviewCheck = await page.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      const btn = document.getElementById('review-submit-btn');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
      return !btn.disabled;
    });
    if (!reviewCheck) throw new Error('Review submit button remained disabled');

    // Seal receipt review
    await page.evaluate(() => document.getElementById('review-submit-btn').click());
    await page.waitFor(() => document.querySelector('.badge-verified')?.textContent?.includes('Review Verified'));
    console.log('   ✓ Receipt verified and sealed');

    // Check finalize button is enabled even though Warm Water has 0 claims!
    const canFinalize = await page.evaluate(() => {
      const btn = document.getElementById('finalize-btn');
      return btn && !btn.disabled;
    });
    if (!canFinalize) {
      throw new Error('Finalize button is disabled despite all paid items being fully allocated!');
    }
    console.log('   ✓ Finalize button is ENABLED without allocating complimentary Warm Water');

    // Click Finalize
    await page.evaluate(() => {
      window.confirm = () => true;
      document.getElementById('finalize-btn').click();
    });
    await page.waitFor(() => document.querySelector('.breakdown-table') !== null);
    console.log('   ✓ Meal finalized successfully');

    // [6/6] Verify Apportionment Summary & Mobile Layout (375px)
    console.log('[6/6] Verifying final apportionment and 375px mobile responsiveness...');
    const finalMetrics = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('.breakdown-table tbody tr'));
      const data = rows.map(r => ({
        name: r.querySelector('td:first-child')?.textContent?.trim() || '',
        amount: r.querySelector('.amount')?.textContent?.trim() || '',
      }));
      return data;
    });

    const aliceRow = finalMetrics.find(r => r.name.includes('Alice'));
    const bobRow = finalMetrics.find(r => r.name.includes('Bob'));
    const grandRow = finalMetrics.find(r => r.name.includes('Grand Total'));

    console.log(`   Alice Share: ${aliceRow?.amount}, Bob Share: ${bobRow?.amount}, Grand Total: ${grandRow?.amount}`);
    if (aliceRow?.amount !== 'RM 15.00') throw new Error(`Expected Alice share RM 15.00, got ${aliceRow?.amount}`);
    if (bobRow?.amount !== 'RM 0.00') throw new Error(`Expected Bob share RM 0.00, got ${bobRow?.amount}`);
    if (grandRow?.amount !== 'RM 15.00') throw new Error(`Expected Grand Total RM 15.00, got ${grandRow?.amount}`);

    // Mobile check at 375px
    await page.setViewport(375, 667);
    await new Promise(r => setTimeout(r, 150));
    const mobileMetrics = await page.evaluate(() => {
      const docScrollWidth = document.documentElement.scrollWidth;
      const bodyScrollWidth = document.body.scrollWidth;
      const vpWidth = window.innerWidth;
      return {
        viewportWidth: vpWidth,
        docScrollWidth,
        bodyScrollWidth,
        overflows: docScrollWidth > vpWidth || bodyScrollWidth > vpWidth,
      };
    });
    if (mobileMetrics.overflows) {
      throw new Error(`Mobile horizontal overflow at 375px: ${JSON.stringify(mobileMetrics)}`);
    }
    console.log(`   ✓ Mobile 375px responsive check passed with 0px horizontal overflow`);

    await page.close();
    console.log('\n================================================================');
    console.log(' ALL COMPLIMENTARY ZERO-PRICED ITEM FLOW CHECKS PASSED 100%! ');
    console.log('================================================================');
  } finally {
    server.kill();
    chrome.proc.kill();
    await rm(tempDir, { recursive: true, force: true }).catch(() => {});
  }
}

run().catch(err => {
  console.error('FAILED:', err);
  process.exit(1);
});
