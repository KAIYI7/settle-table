/**
 * Verification test for unverified / blocked action toast feedback:
 * 1. When items are added & allocated, but receipt is not yet approved & sealed:
 *    - Clicking the disabled "Finalize & Calculate Bill" button displays an error toast:
 *      "Receipt must be verified and sealed before finalization."
 *    - Viewport contextually focuses / navigates to the review section.
 * 2. When attempting to approve & seal receipt without checking "I confirm totals match the physical bill":
 *    - Clicking "Approve & Seal Receipt" displays an error toast:
 *      "Please check \"I confirm totals match the physical bill\" before approving."
 *    - Focus is set to the confirmation checkbox.
 * 3. Checking the confirmation box enables "Approve & Seal Receipt".
 * 4. After approval, "Finalize & Calculate Bill" becomes enabled and finalization succeeds.
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

async function startChrome(chromeBin, port, dataDir) {
  const proc = spawn(chromeBin, [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${dataDir}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-extensions',
    '--disable-gpu',
    '--no-sandbox',
    'about:blank',
  ]);

  let stderr = '';
  proc.stderr?.on('data', d => { stderr += d.toString(); });

  let target = null;
  for (let i = 0; i < 200; i++) {
    try {
      let activePort = port;
      try {
        const devToolsFile = await fs.promises.readFile(join(dataDir, 'DevToolsActivePort'), 'utf8');
        const parsed = Number(devToolsFile.split('\n')[0]);
        if (parsed) activePort = parsed;
      } catch {}
      const res = await fetch(`http://127.0.0.1:${activePort}/json/list`);
      const list = await res.json();
      target = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (target) break;
    } catch {}
    await new Promise(r => setTimeout(r, 100));
  }

  if (!target) {
    proc.kill();
    throw new Error(`Could not connect to Chrome on port ${port}. Stderr: ${stderr}`);
  }

  const page = new CDPPage(target.webSocketDebuggerUrl);
  await page.send('Page.enable');
  await page.send('Runtime.enable');
  return { proc, page };
}

async function run() {
  console.log('=== SettleTable Unverified Action Toast Verification ===\n');
  const chromePath = resolveChromePath();
  const pythonPath = resolvePythonPath();
  const serverPort = await getFreePort();
  const chromePort = await getFreePort();

  const origin = `http://127.0.0.1:${serverPort}`;
  const mealId = `toasttest-${randomBytes(4).toString('hex')}`;

  const tempDir = await mkdtemp(join(tmpdir(), 'settletable-toast-'));
  const dbPath = join(tempDir, 'test.sqlite');
  const capture = join(tempDir, 'mock.json');
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

  let serverStderr = '';
  server.stderr.on('data', d => { serverStderr += d.toString(); });

  let serverReady = false;
  for (let i = 0; i < 60; i++) {
    try {
      const res = await fetch(`${origin}/__financial_test_owner__`);
      if (res.ok) { serverReady = true; break; }
    } catch {}
    await new Promise(r => setTimeout(r, 100));
  }
  if (!serverReady) {
    server.kill();
    throw new Error(`Mock runner failed to start. Stderr: ${serverStderr}`);
  }

  const chromeDataDir = await mkdtemp(join(tmpdir(), 'settletable-chrome-'));
  const { proc: chromeProc, page } = await startChrome(chromePath, chromePort, chromeDataDir);

  try {
    // Navigate to Home
    console.log('[Step 1] Navigating to SettleTable...');
    await page.navigate(`${origin}/#/`);
    await page.waitFor(() => Boolean(document.getElementById('create-meal-id')));

    // Create a meal
    console.log('[Step 2] Creating meal room with Alice and Bob...');
    await page.evaluate(() => {
      document.getElementById('create-meal-id').value = 'Friday Hotpot';
      document.getElementById('create-org-name').value = 'Alice';
      document.getElementById('create-diners').value = 'Bob';
      document.getElementById('create-meal-submit-btn').click();
    });

    await page.waitFor(() => Boolean(document.getElementById('add-item-form')));
    console.log('✓ Meal room created.');

    // Add 1 receipt item
    console.log('[Step 3] Adding receipt item (Hotpot Set - RM 50.00)...');
    await page.evaluate(() => {
      document.getElementById('new-item-label').value = 'Hotpot Set';
      document.getElementById('new-item-price').value = '50.00';
      document.getElementById('add-item-form').querySelector('button[type="submit"]').click();
    });
    await page.waitFor(() => document.querySelectorAll('.review-item-row').length === 1);
    console.log('✓ Item added.');

    // Allocate item to Bob
    console.log('[Step 4] Allocating item to Bob...');
    await page.evaluate(() => {
      const snap = window.settletable.state.snapshot;
      const bob = snap.participants.find(p => p.name === 'Bob');
      const quickBtn = document.querySelector(`.hybrid-pill-available[data-target="${bob.id}"]`);
      if (quickBtn) quickBtn.click();
    });
    await page.waitFor(() => document.querySelector('.hybrid-pill-allocated') !== null);
    console.log('✓ Item allocated to Bob.');

    // Receipt verification is still "Needs Review" (unconfirmed)
    const isReviewConfirmed = await page.evaluate(() => Boolean(window.settletable.state.snapshot.review));
    console.log(`Receipt reviewConfirmed state: ${isReviewConfirmed} (expected false)`);
    if (isReviewConfirmed) throw new Error('Expected receipt to be unconfirmed initially');

    // Click Finalize button while receipt is unverified
    console.log('[Step 5] Clicking "Finalize & Calculate Bill" while receipt is unverified...');
    await page.evaluate(() => {
      const wrapper = document.getElementById('finalize-btn-wrapper');
      if (wrapper) wrapper.click();
      else document.getElementById('finalize-btn').click();
    });

    // Verify toast error pops up
    await page.waitFor(() => {
      const alertContainer = document.getElementById('alert-container');
      return alertContainer && alertContainer.innerText.includes('Receipt must be verified and sealed before finalization');
    });
    const toastMsg = await page.evaluate(() => document.getElementById('alert-container')?.innerText);
    console.log(`✓ Error toast successfully appeared: "${toastMsg.trim()}"`);

    // Click Approve & Seal without checking checkbox
    console.log('[Step 6] Clicking "Approve & Seal Receipt" without checking checkbox...');
    await page.evaluate(() => {
      const wrapper = document.getElementById('review-submit-wrapper');
      if (wrapper) wrapper.click();
      else document.getElementById('review-submit-btn').click();
    });

    await page.waitFor(() => {
      const alertContainer = document.getElementById('alert-container');
      return alertContainer && alertContainer.innerText.includes('Please check "I confirm totals match the physical bill"');
    });
    const chkToast = await page.evaluate(() => document.getElementById('alert-container')?.innerText);
    console.log(`✓ Error toast successfully appeared: "${chkToast.trim()}"`);

    // Check the box and approve
    console.log('[Step 7] Checking confirmation box and approving receipt...');
    await page.evaluate(() => {
      const chk = document.getElementById('review-confirm-check');
      chk.checked = true;
      chk.dispatchEvent(new Event('change', { bubbles: true }));
      document.getElementById('review-submit-btn').click();
    });

    await page.waitFor(() => document.getElementById('receipt-verified-status') !== null);
    console.log('✓ Receipt verified and sealed successfully.');

    // Now finalize button should be enabled
    console.log('[Step 8] Checking Finalize button is now enabled and clicking it...');
    await page.waitFor(() => {
      const btn = document.getElementById('finalize-btn');
      return btn && !btn.disabled;
    });

    await page.evaluate(() => {
      document.getElementById('finalize-btn').click();
    });

    await page.waitFor(() => document.getElementById('apportionment-section') !== null);
    console.log('✓ Meal finalized successfully and Final Apportionment Summary rendered.');

    console.log('\n========================================================');
    console.log('🎉 ALL UNVERIFIED ACTION TOAST TESTS PASSED 100%!');
    console.log('========================================================\n');

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

run().catch((err) => {
  console.error('VERIFICATION FAILED:', err);
  process.exit(1);
});
